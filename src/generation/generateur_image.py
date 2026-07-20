"""Génération d'images (Pollinations gratuit, ou OpenAI si clé présente)."""

from __future__ import annotations

import base64
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests

_TIMEOUT = 90
_DEFAULT_SIZE = 1024


def _provider() -> str:
    return (os.getenv("IMAGE_GEN_PROVIDER") or "auto").strip().lower()


def disponible() -> bool:
    """Toujours vrai pour Pollinations ; OpenAI si clé."""
    p = _provider()
    if p == "openai":
        return bool(os.getenv("OPENAI_API_KEY"))
    if p == "off":
        return False
    return True


def raffiner_prompt_image(question: str, llm_client=None) -> str:
    """Transforme la demande utilisateur en prompt court (anglais), prêt pour le modèle image."""
    q = (question or "").strip()
    if not q:
        return "a clear technical illustration, clean style"

    if llm_client is not None:
        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Tu convertis une demande en UN prompt d'image court en anglais "
                        "(max 40 mots). Pas de guillemets, pas d'explication. "
                        "Style clair, utile pour documentation / illustration technique."
                    ),
                },
                {"role": "user", "content": q},
            ]
            out, _ = llm_client.invoke(messages)
            prompt = (out or "").strip().strip('"').strip("'")
            prompt = re.sub(r"\s+", " ", prompt)
            if 8 <= len(prompt) <= 400:
                return prompt
        except Exception:
            pass

    # Fallback heuristique : retirer les verbes de commande FR/EN
    nettoye = re.sub(
        r"(?i)^(génère|genere|crée|cree|dessine|fais|fait|illustre|generate|draw|create|make)\s+"
        r"(moi\s+)?(une?\s+)?(image|illustration|dessin|picture|photo)\s*(de|d'|of|:)?\s*",
        "",
        q,
    ).strip()
    return nettoye or q


def _generer_pollinations(prompt: str, width: int, height: int) -> Tuple[Optional[bytes], str]:
    encoded = quote(prompt[:500], safe="")
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={width}&height={height}&nologo=true&model=flux&enhance=true"
    )
    try:
        r = requests.get(url, timeout=_TIMEOUT)
        r.raise_for_status()
        ctype = (r.headers.get("content-type") or "").lower()
        if "image" not in ctype and len(r.content) < 1000:
            return None, f"Réponse non-image ({ctype or 'inconnu'})"
        return r.content, ""
    except Exception as exc:
        return None, str(exc)


def _generer_openai(prompt: str, size: str = "1024x1024") -> Tuple[Optional[bytes], str]:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None, "OPENAI_API_KEY manquante"
    try:
        from openai import OpenAI

        client = OpenAI(api_key=key)
        model = os.getenv("OPENAI_IMAGE_MODEL") or "dall-e-3"
        resp = client.images.generate(
            model=model,
            prompt=prompt[:1000],
            size=size,
            n=1,
            response_format="b64_json",
        )
        b64 = resp.data[0].b64_json
        if not b64:
            return None, "Réponse OpenAI vide"
        return base64.b64decode(b64), ""
    except Exception as exc:
        return None, str(exc)


def generer_image(
    prompt: str,
    *,
    width: int = _DEFAULT_SIZE,
    height: int = _DEFAULT_SIZE,
) -> Dict[str, Any]:
    """
    Génère une image. Retour :
      {ok, prompt, bytes, b64, media_type, provider, erreur}
    """
    prompt = (prompt or "").strip() or "simple clear illustration"
    provider = _provider()
    erreur = ""
    data: Optional[bytes] = None
    used = ""

    order: List[str]
    if provider == "openai":
        order = ["openai"]
    elif provider == "pollinations":
        order = ["pollinations"]
    elif provider == "off":
        return {
            "ok": False,
            "prompt": prompt,
            "bytes": None,
            "b64": None,
            "media_type": "image/png",
            "provider": "off",
            "erreur": "Génération d'images désactivée (IMAGE_GEN_PROVIDER=off).",
        }
    else:
        # auto : OpenAI si clé, sinon Pollinations
        order = ["openai", "pollinations"] if os.getenv("OPENAI_API_KEY") else ["pollinations"]

    for name in order:
        if name == "openai":
            data, erreur = _generer_openai(prompt, size=f"{width}x{height}")
        else:
            data, erreur = _generer_pollinations(prompt, width, height)
        if data:
            used = name
            break

    if not data:
        return {
            "ok": False,
            "prompt": prompt,
            "bytes": None,
            "b64": None,
            "media_type": "image/png",
            "provider": used or (order[0] if order else ""),
            "erreur": erreur or "Échec génération",
        }

    return {
        "ok": True,
        "prompt": prompt,
        "bytes": data,
        "b64": base64.b64encode(data).decode("ascii"),
        "media_type": "image/png",
        "provider": used,
        "erreur": "",
    }
