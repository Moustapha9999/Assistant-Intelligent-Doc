"""Client LLM unifié pour Groq (params, retries, streaming, troncature)."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from dotenv import load_dotenv
from groq import Groq

# Toujours relire le .env du projet (évite un vieux LLM_MODEL en mémoire / CWD)
_ENV = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_ENV, override=True)


def _attendre_rate_limit(message: str, tentative: int) -> float:
    """Parse le délai Groq ('try again in 7m59.52s') et borne l'attente."""
    m = re.search(r"try again in (?:([\d.]+)m)?([\d.]+)s", message, re.I)
    if m:
        minutes = float(m.group(1) or 0)
        secondes = float(m.group(2) or 0)
        attente = minutes * 60 + secondes + 5
    else:
        attente = min(60, 10 * (tentative + 1))
    return min(attente, 120)


MODELE_VISION_DEFAUT = "qwen/qwen3.8-27b"
# Essayés dans l'ordre si le modèle configuré est retiré ou n'accepte pas les images
MODELES_VISION_REPLI = ("qwen/qwen3.8-27b",)


def _erreur_vision_utilisateur(exc: Exception) -> Optional[str]:
    """None si l'erreur justifie d'essayer un autre modèle ; sinon message utilisateur."""
    msg = str(exc).lower()
    if (
        "does not exist" in msg or "model_not_found" in msg or "decommissioned" in msg
        or "must be a string" in msg or "does not support" in msg or "404" in msg
    ):
        return None
    if "429" in msg or "rate_limit" in msg:
        return "le service de vision est momentanément saturé ; réessayez dans une minute."
    if "timeout" in msg or "timed out" in msg:
        return "l'analyse a dépassé le délai autorisé ; réessayez avec une image plus légère."
    if "413" in msg or "too large" in msg:
        return "l'image est trop volumineuse pour le service de vision."
    return "le service d'analyse d'images est indisponible pour le moment."


def _erreur_llm_utilisateur(exc: object) -> str:
    """Message affichable (préfixe « ❌ Erreur » attendu par l'orchestrateur), sans détail brut."""
    nom = type(exc).__name__.lower()
    msg = str(exc).lower()
    if "connection" in nom or "connection error" in msg or "getaddrinfo" in msg:
        cause = "le service d'IA est injoignable (connexion réseau). Réessayez dans un instant."
    elif "timeout" in nom or "timed out" in msg:
        cause = "le service d'IA a mis trop de temps à répondre. Réessayez dans un instant."
    elif "401" in msg or "authentication" in nom or "invalid api key" in msg:
        cause = "la clé d'accès au service d'IA est refusée. Contactez l'administrateur."
    elif "429" in msg or "rate_limit" in msg:
        cause = "la limite de requêtes du service d'IA est atteinte. Réessayez dans une minute."
    elif "413" in msg or "too large" in msg:
        cause = "la demande est trop volumineuse. Réduisez les pièces jointes ou la question."
    else:
        cause = "le service d'IA n'a pas pu traiter la demande. Réessayez dans un instant."
    return f"❌ Erreur : {cause}"


def _sans_reflexion(texte: str) -> str:
    return re.sub(r"<think>.*?</think>", "", texte or "", flags=re.S).strip()


def tronquer_messages(messages: List[Dict], facteur: float = 0.6) -> List[Dict]:
    """Réduit le dernier message user (contexte) en cas de requête trop grosse."""
    out = [dict(m) for m in messages]
    for i in range(len(out) - 1, -1, -1):
        if out[i].get("role") == "user":
            contenu = out[i].get("content") or ""
            limite = max(800, int(len(contenu) * facteur))
            out[i]["content"] = contenu[:limite] + "\n\n[contexte tronqué pour respecter la limite Groq]"
            break
    return out


class LLMClient:
    """Point unique d'accès Groq pour l'orchestrateur et le générateur legacy."""

    def __init__(
        self,
        modele: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        presence_penalty: Optional[float] = None,
        frequency_penalty: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY manquante")

        self.client = Groq(api_key=self.api_key)
        # runtime_ia.json (Admin) > .env > défaut
        try:
            from app.runtime_config import charger as _rt

            rt = _rt()
        except Exception:
            rt = {}

        def _rt_get(key: str, fallback: str) -> str:
            return str(rt.get(key) if rt.get(key) is not None else os.getenv(key, fallback))

        self.modele = modele or _rt_get("LLM_MODEL", "openai/gpt-oss-120b")
        # Auto-migration si un ancien modèle Groq retiré est encore configuré
        _obsoletes = ("llama-3.3-70b-versatile", "llama-3.1-8b-instant")
        if any(x in self.modele for x in _obsoletes):
            self.modele = "openai/gpt-oss-120b"
            print(f"   ⚠️  Modèle Groq obsolète détecté → bascule sur {self.modele}")
        print(f"   ✅ LLM Groq : {self.modele}")
        self.temperature = float(
            temperature
            if temperature is not None
            else _rt_get("LLM_TEMPERATURE", "0.3")
        )
        self.top_p = float(
            top_p if top_p is not None else _rt_get("LLM_TOP_P", "0.95")
        )
        self.presence_penalty = float(
            presence_penalty
            if presence_penalty is not None
            else _rt_get("LLM_PRESENCE_PENALTY", "0.0")
        )
        self.frequency_penalty = float(
            frequency_penalty
            if frequency_penalty is not None
            else _rt_get("LLM_FREQUENCY_PENALTY", "0.2")
        )
        self.max_tokens = int(
            max_tokens if max_tokens is not None else _rt_get("MAX_TOKENS", "3000")
        )

        self.modele_leger = any(
            x in self.modele.lower() for x in ("8b", "instant", "3.1-8b", "llama-3.1")
        )
        if self.modele_leger:
            self.max_tokens = min(self.max_tokens, int(os.getenv("MAX_TOKENS_LEGER", "1200")))

        self.modele_vision = _rt_get("GROQ_VISION_MODEL", MODELE_VISION_DEFAUT)
        self.derniere_erreur_vision: Optional[str] = None

        if os.getenv("MODE_RAGAS_EVAL", "false").lower() == "true":
            self.appliquer_mode_ragas()

    def appliquer_mode_ragas(self) -> None:
        """Réduit température / tokens pour une évaluation faithfulness plus stable."""
        self.max_tokens = min(self.max_tokens, 1200)
        self.temperature = min(self.temperature, 0.1)

    def _kwargs(self, messages: List[Dict], stream: bool = False) -> Dict:
        data = {
            "model": self.modele,
            "messages": messages,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "presence_penalty": self.presence_penalty,
            "frequency_penalty": self.frequency_penalty,
            "max_tokens": self.max_tokens,
        }
        if stream:
            data["stream"] = True
        return data

    def invoke(self, messages: List[Dict], max_retries: int = 5) -> Tuple[str, int]:
        """Appel synchrone avec retries 429 / 413."""
        derniere_erreur = None
        msgs = messages
        for tentative in range(max_retries):
            try:
                completion = self.client.chat.completions.create(**self._kwargs(msgs))
                contenu = completion.choices[0].message.content or ""
                tokens = int(getattr(completion.usage, "total_tokens", 0) or 0)
                return contenu, tokens
            except Exception as exc:
                derniere_erreur = exc
                msg = str(exc)
                low = msg.lower()
                if "413" in msg or "too large" in low or "request too large" in low:
                    print(
                        f"   ⚠️  Requête trop grosse, troncature contexte "
                        f"(tentative {tentative + 1}/{max_retries})..."
                    )
                    msgs = tronquer_messages(msgs, facteur=0.55)
                    self.max_tokens = max(400, int(self.max_tokens * 0.7))
                    continue
                if "429" in msg or "rate_limit" in low:
                    attente = _attendre_rate_limit(msg, tentative)
                    print(
                        f"   ⏳ Rate-limit Groq, pause {attente:.0f}s "
                        f"(tentative {tentative + 1}/{max_retries})..."
                    )
                    time.sleep(attente)
                    continue
                print(f"   ❌ LLM : {type(exc).__name__}")
                return _erreur_llm_utilisateur(exc), 0
        return _erreur_llm_utilisateur(derniere_erreur), 0

    def analyser_image(
        self,
        image_b64: str,
        media_type: str = "image/png",
        question: str = "Décris cette image en détail (texte visible, UI, schéma, code).",
        max_tokens: int = 1200,
    ) -> Tuple[str, int]:
        """Analyse visuelle réelle via modèle multimodal Groq (base64).

        Retourne ("", 0) en cas d'échec ; `self.derniere_erreur_vision` explique la cause
        en termes compréhensibles (jamais de trace ni de clé).
        """
        self.derniere_erreur_vision = None
        if not image_b64:
            return "", 0
        data_url = f"data:{media_type or 'image/png'};base64,{image_b64}"
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            (question or "").strip()
                            or "Décris cette image en détail (texte visible, UI, schéma, code)."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": data_url},
                    },
                ],
            }
        ]
        candidats = list(dict.fromkeys([self.modele_vision, *MODELES_VISION_REPLI]))
        client = self.client.with_options(timeout=90.0, max_retries=1)
        for modele in candidats:
            completion = None
            for tentative in range(3):
                try:
                    completion = client.chat.completions.create(
                        model=modele,
                        messages=messages,
                        temperature=0.2,
                        max_tokens=max_tokens,
                    )
                    break
                except Exception as exc:
                    raison = _erreur_vision_utilisateur(exc)
                    print(f"   ⚠️  Vision ({modele}) : {type(exc).__name__}")
                    low = str(exc).lower()
                    if ("429" in low or "rate_limit" in low) and tentative < 2:
                        attente = _attendre_rate_limit(str(exc), tentative)
                        if attente <= 45:
                            time.sleep(attente)
                            continue
                    if raison is None:
                        break
                    self.derniere_erreur_vision = raison
                    return "", 0
            if completion is None:
                continue
            contenu = _sans_reflexion(completion.choices[0].message.content or "")
            if not contenu:
                self.derniere_erreur_vision = "le modèle de vision n'a renvoyé aucune description."
                return "", 0
            if modele != self.modele_vision:
                print(f"   ℹ️  Modèle de vision {self.modele_vision} indisponible → {modele}")
                self.modele_vision = modele
            tokens = int(getattr(completion.usage, "total_tokens", 0) or 0)
            return contenu, tokens
        self.derniere_erreur_vision = (
            "aucun modèle de vision n'est accessible avec ce compte Groq "
            "(vérifiez GROQ_VISION_MODEL)."
        )
        return "", 0

    def stream(
        self,
        messages: List[Dict],
        usage_holder: Optional[Dict] = None,
        max_retries: int = 4,
    ) -> Iterable[str]:
        """Streaming avec retry initial sur rate-limit / payload trop gros."""
        msgs = messages
        derniere_erreur = None

        for tentative in range(max_retries):
            try:
                kwargs = self._kwargs(msgs, stream=True)
                try:
                    flux = self.client.chat.completions.create(
                        **kwargs, stream_options={"include_usage": True}
                    )
                except TypeError:
                    flux = self.client.chat.completions.create(**kwargs)

                morceaux: List[str] = []
                for chunk in flux:
                    usage = getattr(chunk, "usage", None)
                    if usage_holder is not None and usage is not None:
                        total = getattr(usage, "total_tokens", None)
                        if total is None:
                            total = (getattr(usage, "prompt_tokens", 0) or 0) + (
                                getattr(usage, "completion_tokens", 0) or 0
                            )
                        usage_holder["tokens_utilises"] = int(total or 0)
                    try:
                        if not chunk.choices:
                            continue
                        delta = chunk.choices[0].delta.content
                    except (AttributeError, IndexError):
                        delta = None
                    if delta:
                        morceaux.append(delta)
                        yield delta

                if usage_holder is not None and not usage_holder.get("tokens_utilises"):
                    n = sum(len(x) for x in morceaux)
                    usage_holder["tokens_utilises"] = max(1, n // 4) if n else 0
                return

            except Exception as exc:
                derniere_erreur = exc
                msg = str(exc)
                low = msg.lower()
                if "413" in msg or "too large" in low or "request too large" in low:
                    print(
                        f"   ⚠️  Stream trop gros, troncature "
                        f"(tentative {tentative + 1}/{max_retries})..."
                    )
                    msgs = tronquer_messages(msgs, facteur=0.55)
                    self.max_tokens = max(400, int(self.max_tokens * 0.7))
                    continue
                if "429" in msg or "rate_limit" in low:
                    attente = _attendre_rate_limit(msg, tentative)
                    print(
                        f"   ⏳ Rate-limit stream, pause {attente:.0f}s "
                        f"(tentative {tentative + 1}/{max_retries})..."
                    )
                    time.sleep(attente)
                    continue
                print(f"   ❌ LLM (stream) : {type(exc).__name__}")
                yield _erreur_llm_utilisateur(exc)
                return

        yield _erreur_llm_utilisateur(derniere_erreur)
