"""
Évaluation RAGAS adaptée au compte GRATUIT Groq.

Causes des scores à 0 avec l'ancienne version :
  - Régénération + juge llama-3.3-70b → saturation TPD (100k/jour)
  - evaluate() en parallèle → rate-limit massif
  - AnswerRelevancy(n=3) → Groq refuse n>1

Stratégie correcte :
  - Réutilise resultats/generation/reponses_generees.json (pas de regen)
  - Juge léger : llama-3.1-8b-instant
  - Évaluation SÉQUENTIELLE, métrique par métrique
  - AnswerRelevancy(strictness=1)
  - Pause + retry sur 429
"""

import os
import re
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from dotenv import load_dotenv

# Windows cp1252 ne gère pas les emojis du rapport
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

PAUSE_ENTRE_APPELS = float(os.getenv("RAGAS_PAUSE", "8"))
MAX_CHARS_REPONSE = int(os.getenv("RAGAS_MAX_CHARS_REPONSE", "900"))
MAX_CHARS_CONTEXTE = int(os.getenv("RAGAS_MAX_CHARS_CONTEXTE", "500"))
MAX_CONTEXTES = int(os.getenv("RAGAS_MAX_CONTEXTES", "3"))


class EvaluateurRAGAS:
    """Évalue Faithfulness, Answer Relevancy, Context Recall, Context Precision."""

    def __init__(self):
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.modele = os.getenv("RAGAS_LLM_MODEL", "llama-3.1-8b-instant")
        self.base_dir = Path(__file__).resolve().parent.parent.parent
        self.dossier_resultats = self.base_dir / "resultats" / "metrics"
        self.dossier_resultats.mkdir(parents=True, exist_ok=True)

        if not self.groq_api_key:
            raise ValueError("❌ GROQ_API_KEY manquante dans le fichier .env")

        self._initialiser()

    def _initialiser(self):
        from ragas.metrics import Faithfulness, AnswerRelevancy, ContextRecall, ContextPrecision
        from ragas.llms import LangchainLLMWrapper
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from langchain_groq import ChatGroq
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
        except ImportError:
            from langchain_community.embeddings import HuggingFaceEmbeddings

        llm_groq = ChatGroq(
            api_key=self.groq_api_key,
            model=self.modele,
            temperature=0.0,
            max_tokens=int(os.getenv("RAGAS_MAX_TOKENS", "4096")),
        )
        self.llm_juge = LangchainLLMWrapper(llm_groq)

        cache_folder = str(self.base_dir / "models_cache")
        emb = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2", cache_folder=cache_folder)
        self.embeddings_ragas = LangchainEmbeddingsWrapper(emb)

        self.metriques = {
            "faithfulness": Faithfulness(llm=self.llm_juge),
            "answer_relevancy": AnswerRelevancy(
                llm=self.llm_juge,
                embeddings=self.embeddings_ragas,
                strictness=1,
            ),
            "context_precision": ContextPrecision(llm=self.llm_juge),
            "context_recall": ContextRecall(llm=self.llm_juge),
        }
        print(f"✅ RAGAS prêt — juge={self.modele} | strictness=1 | pause={PAUSE_ENTRE_APPELS}s")

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        try:
            f = float(val)
            if f != f:  # NaN
                return None
            return round(max(0.0, min(f, 1.0)), 4)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _preparer_sample(d: Dict):
        from ragas.dataset_schema import SingleTurnSample

        reponse = (d.get("reponse_generee") or d.get("reponse") or "")[:MAX_CHARS_REPONSE]
        if reponse.startswith("❌") or "Rate limit" in reponse:
            reponse = ""

        contextes_bruts = d.get("contextes") or []
        if not contextes_bruts and d.get("documents"):
            contextes_bruts = [
                doc.get("texte", doc.get("text", "")) for doc in d["documents"]
            ]

        contextes = [
            (c or "")[:MAX_CHARS_CONTEXTE]
            for c in contextes_bruts[:MAX_CONTEXTES]
            if (c or "").strip()
        ]
        if not contextes:
            contextes = ["(aucun contexte)"]

        return SingleTurnSample(
            user_input=d["question"],
            response=reponse or "(réponse indisponible)",
            retrieved_contexts=contextes,
            reference=d.get("reponse_ideale") or "",
        )

    def _evaluer_une_metrique(self, metrique, sample) -> Optional[float]:
        for _ in range(5):
            try:
                score = metrique.single_turn_score(sample)
                return self._safe_float(score)
            except Exception as e:
                msg = str(e)
                if "429" in msg or "rate_limit" in msg.lower():
                    m = re.search(r"try again in (?:([\d.]+)m)?([\d.]+)s", msg, re.I)
                    if m:
                        attente = float(m.group(1) or 0) * 60 + float(m.group(2) or 0) + 3
                    else:
                        attente = 45
                    attente = min(max(attente, 15), 300)
                    print(f"        ⏳ Rate-limit, pause {attente:.0f}s...")
                    time.sleep(attente)
                elif "'n'" in msg or "must be at most 1" in msg:
                    print(f"        ⚠️  Groq n>1 : {msg[:80]}")
                    return None
                else:
                    print(f"        ⚠️  Erreur : {msg[:120]}")
                    return None
        return None

    def charger_dataset_test(self) -> List[Dict]:
        """5 questions (aligné sur 1_generer_reponses.py)."""
        return [
            {
                "question": "Comment créer une API REST avec Flask en Python ?",
                "reponse_ideale": (
                    "Flask est un micro-framework Python. On crée une API REST en définissant "
                    "des routes avec les décorateurs @app.route() et en retournant des données "
                    "au format JSON via jsonify()."
                ),
            },
            {
                "question": "Comment gérer l'authentification JWT dans une application web ?",
                "reponse_ideale": (
                    "JWT (JSON Web Token) est utilisé pour l'authentification. On génère un token "
                    "signé avec une clé secrète lors de la connexion, puis on le vérifie à chaque "
                    "requête protégée."
                ),
            },
            {
                "question": "Comment créer une API avec FastAPI en Python ?",
                "reponse_ideale": (
                    "FastAPI est un framework Python moderne pour créer des API. On définit des "
                    "routes avec des décorateurs comme @app.get() et @app.post(), avec validation "
                    "automatique via des modèles Pydantic."
                ),
            },
            {
                "question": "Comment utiliser les hooks dans React ?",
                "reponse_ideale": (
                    "Les hooks React comme useState et useEffect permettent d'utiliser l'état "
                    "local et les effets de bord dans les composants fonctionnels, sans recourir "
                    "aux classes."
                ),
            },
            {
                "question": "Comment valider un payload avec Pydantic dans FastAPI ?",
                "reponse_ideale": (
                    "Dans FastAPI, on définit un modèle Pydantic (BaseModel) avec les champs "
                    "attendus ; FastAPI valide automatiquement le payload de la requête grâce "
                    "à ce modèle."
                ),
            },
        ]

    def evaluer_depuis_fichier(self, fichier: Path) -> Dict:
        with open(fichier, "r", encoding="utf-8") as f:
            paquet = json.load(f)

        donnees = paquet["donnees"]
        # Filtrer les réponses en erreur (rate-limit) pour ne pas polluer les scores
        valides = [
            d for d in donnees
            if d.get("reponse_generee")
            and not str(d["reponse_generee"]).startswith("❌")
            and "Rate limit" not in str(d["reponse_generee"])
        ]
        if len(valides) < len(donnees):
            print(f"⚠️  {len(donnees) - len(valides)} réponse(s) en erreur ignorée(s)")
        if not valides:
            raise ValueError(
                "Aucune réponse valide à évaluer. Relance : python src/evaluation/1_generer_reponses.py"
            )

        print(f"\n📂 {len(valides)} réponses valides depuis {fichier.name}")
        print(f"   Évaluation séquentielle (pause {PAUSE_ENTRE_APPELS}s)")
        print(f"   ⏳ Temps estimé : ~{len(valides) * 4 * PAUSE_ENTRE_APPELS / 60:.0f} min\n")

        detail = []
        fichier_partiel = self.dossier_resultats / "ragas_partiel.json"

        for i, d in enumerate(valides, 1):
            print(f"[{i}/{len(valides)}] {d['question'][:55]}")
            sample = self._preparer_sample(d)
            scores = {"question": d["question"], "latence_sec": d.get("latence_sec")}

            for nom, metrique in self.metriques.items():
                score = self._evaluer_une_metrique(metrique, sample)
                scores[nom] = score
                etiquette = f"{score:.3f}" if score is not None else "—"
                print(f"        {nom:20s} = {etiquette}")
                time.sleep(PAUSE_ENTRE_APPELS)

            detail.append(scores)
            with open(fichier_partiel, "w", encoding="utf-8") as f:
                json.dump(detail, f, ensure_ascii=False, indent=2)
            print("         sauvegarde partielle OK\n")

        return self._finaliser(detail, paquet)

    def evaluer_dataset(
        self,
        questions: List[str],
        reponses: List[str],
        documents_listes: List[List[Dict]],
        reponses_ideales: Optional[List[str]] = None,
        sauvegarder: bool = True,
    ) -> Dict:
        """API compat : convertit en échantillons et évalue séquentiellement."""
        donnees = []
        for i, q in enumerate(questions):
            docs = documents_listes[i] if i < len(documents_listes) else []
            donnees.append({
                "question": q,
                "reponse_generee": reponses[i] if i < len(reponses) else "",
                "reponse_ideale": (reponses_ideales or [""])[i] if reponses_ideales else "",
                "contextes": [d.get("texte", d.get("text", "")) for d in docs],
            })
        paquet = {"donnees": donnees, "latence_moyenne": None}
        tmp = self.dossier_resultats / "_tmp_eval_dataset.json"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(paquet, f, ensure_ascii=False)
        rapport = self.evaluer_depuis_fichier(tmp)
        tmp.unlink(missing_ok=True)
        if not sauvegarder:
            return rapport
        return rapport

    def _finaliser(self, detail: List[Dict], paquet: Dict) -> Dict:
        def moyenne(cle):
            vals = [d[cle] for d in detail if d.get(cle) is not None]
            return round(sum(vals) / len(vals), 4) if vals else 0.0

        def taux_succes(cle):
            total = len(detail)
            ok = sum(1 for d in detail if d.get(cle) is not None)
            return round(ok / total, 2) if total else 0.0

        rapport = {
            "nb_exemples": len(detail),
            "faithfulness_moy": moyenne("faithfulness"),
            "relevancy_moy": moyenne("answer_relevancy"),
            "precision_moy": moyenne("context_precision"),
            "recall_moy": moyenne("context_recall"),
            "latence_moyenne": paquet.get("latence_moyenne"),
            "taux_mesure": {
                "faithfulness": taux_succes("faithfulness"),
                "answer_relevancy": taux_succes("answer_relevancy"),
                "context_precision": taux_succes("context_precision"),
                "context_recall": taux_succes("context_recall"),
            },
            "resultats_detail": detail,
            "timestamp": datetime.now().isoformat(),
        }
        rapport["score_global"] = round(
            (
                rapport["faithfulness_moy"]
                + rapport["relevancy_moy"]
                + rapport["precision_moy"]
                + rapport["recall_moy"]
            )
            / 4,
            4,
        )

        self._sauvegarder_rapport(rapport)
        self.afficher_rapport(rapport)
        return rapport

    def _sauvegarder_rapport(self, rapport: Dict) -> None:
        horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
        fichier = self.dossier_resultats / f"evaluation_{horodatage}.json"
        with open(fichier, "w", encoding="utf-8") as f:
            json.dump(rapport, f, ensure_ascii=False, indent=2)
        # Alias stable pour le pipeline 2 étapes
        alias = self.dossier_resultats / f"ragas_final_{horodatage}.json"
        with open(alias, "w", encoding="utf-8") as f:
            json.dump(rapport, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Rapport : {fichier}")

    def afficher_rapport(self, rapport: Dict) -> None:
        print("\n" + "═" * 60)
        print("📊 RAPPORT D'ÉVALUATION RAGAS")
        print("═" * 60)
        print(f"  Exemples évalués   : {rapport['nb_exemples']}")
        print(f"  Faithfulness       : {rapport['faithfulness_moy']:.4f}  (cible > 0.90)")
        print(f"  Answer Relevancy   : {rapport['relevancy_moy']:.4f}  (cible > 0.80)")
        print(f"  Context Precision  : {rapport['precision_moy']:.4f}  (cible > 0.80)")
        print(f"  Context Recall     : {rapport['recall_moy']:.4f}  (cible > 0.75)")
        if rapport.get("latence_moyenne"):
            print(f"  Latence moyenne    : {rapport['latence_moyenne']:.2f}s")
        print("  ─────────────────────────────────────────────")
        print(f"  Score global       : {rapport['score_global']:.4f}")
        score = rapport["score_global"]
        if score >= 0.90:
            niveau = "🟢 Excellent"
        elif score >= 0.75:
            niveau = "🟡 Bon"
        elif score >= 0.60:
            niveau = "🟠 Acceptable"
        else:
            niveau = "🔴 À améliorer"
        print(f"  Niveau             : {niveau}")
        print("═" * 60 + "\n")


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent.parent.parent
    fichier = base_dir / "resultats" / "generation" / "reponses_generees.json"

    if not fichier.exists():
        print(f"❌ Fichier introuvable : {fichier}")
        print("   Lance d'abord : python src/evaluation/1_generer_reponses.py")
    else:
        EvaluateurRAGAS().evaluer_depuis_fichier(fichier)
