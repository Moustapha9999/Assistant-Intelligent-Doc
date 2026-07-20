"""
ÉTAPE 2/2 — Évaluation RAGAS des réponses déjà générées.
Délègue à evaluateur_ragas.py (séquentiel, compatible Groq gratuit).
"""

from pathlib import Path
from evaluateur_ragas import EvaluateurRAGAS

if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent.parent.parent
    fichier = base_dir / "resultats" / "generation" / "reponses_generees.json"

    if not fichier.exists():
        print(f"❌ Fichier introuvable : {fichier}")
        print("   Lance d'abord : python src/evaluation/1_generer_reponses.py")
    else:
        EvaluateurRAGAS().evaluer_depuis_fichier(fichier)
