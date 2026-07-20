"""
ÉTAPE 1/2 — Génération des réponses du système RAG
Génère les réponses pour le jeu de test et les SAUVEGARDE dans un fichier JSON.
À lancer UNE SEULE FOIS. Le fichier produit sera ensuite évalué par 2_evaluer_ragas.py


"""

import os
import json
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Désactiver le web search + mode ancré pour maximiser faithfulness / relevancy RAGAS
os.environ["DESACTIVER_WEB_SEARCH"] = "true"
os.environ["MODE_RAGAS_EVAL"] = "true"
# Modèle plus léger = moins de tokens / meilleurs rate-limits sur compte gratuit Groq
os.environ["LLM_MODEL"] = os.getenv("RAGAS_LLM_MODEL", "llama-3.1-8b-instant")

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retrieval.retrieval_hybride import RetrievalHybride
from generation.generateur_reponse import GenerateurReponse


# ── Jeu de test : 5 questions (économie de quota) ──
DATASET_TEST = [
    {"question": "Comment créer une API REST avec Flask en Python ?",
     "reponse_ideale": "Flask est un micro-framework Python. On crée une API REST en définissant des routes avec les décorateurs @app.route() et en retournant des données au format JSON via jsonify()."},
    {"question": "Comment gérer l'authentification JWT dans une application web ?",
     "reponse_ideale": "JWT (JSON Web Token) est utilisé pour l'authentification. On génère un token signé avec une clé secrète lors de la connexion, puis on le vérifie à chaque requête protégée."},
    {"question": "Comment créer une API avec FastAPI en Python ?",
     "reponse_ideale": "FastAPI est un framework Python moderne pour créer des API. On définit des routes avec des décorateurs comme @app.get() et @app.post(), avec validation automatique via des modèles Pydantic."},
    {"question": "Comment utiliser les hooks dans React ?",
     "reponse_ideale": "Les hooks React comme useState et useEffect permettent d'utiliser l'état local et les effets de bord dans les composants fonctionnels, sans recourir aux classes."},
    {"question": "Comment valider un payload avec Pydantic dans FastAPI ?",
     "reponse_ideale": "Dans FastAPI, on définit un modèle Pydantic (BaseModel) avec les champs attendus ; FastAPI valide automatiquement le payload de la requête grâce à ce modèle."},
]


def main():
    base_dir = Path(__file__).resolve().parent.parent.parent
    dossier  = base_dir / "resultats" / "generation"
    dossier.mkdir(parents=True, exist_ok=True)
    fichier_sortie = dossier / "reponses_generees.json"

    print("="*60)
    print("ÉTAPE 1/2 — GÉNÉRATION DES RÉPONSES")
    print("="*60)

    moteur     = RetrievalHybride()
    generateur = GenerateurReponse()

    donnees = []
    total   = len(DATASET_TEST)

    print(f"\n🔄 Génération de {total} réponses...\n")

    for i, exemple in enumerate(DATASET_TEST, 1):
        question = exemple["question"]
        print(f"[{i}/{total}] {question}")

        # Mesure de la latence (utile pour le Chapitre 4)
        t0   = time.time()
        docs = moteur.rechercher(question, top_k_retrieval=30, top_k_final=5)
        resultat = generateur.generer(question, docs)
        latence  = round(time.time() - t0, 2)

        # Contextes un peu plus longs pour Context Recall / Precision
        contextes = [d.get("texte", "")[:1200] for d in docs if d.get("texte")]

        donnees.append({
            "question"       : question,
            "reponse_ideale" : exemple["reponse_ideale"],
            "reponse_generee": resultat["reponse_seule"],
            "contextes"      : contextes,
            "nb_documents"   : len(docs),
            "latence_sec"    : latence,
            "tokens"         : resultat.get("tokens_utilises", 0),
        })

        print(f"        ✅ {resultat.get('tokens_utilises',0)} tokens | {latence}s\n")

        if resultat.get("tokens_utilises", 0) == 0 or str(resultat.get("reponse_seule", "")).startswith("❌"):
            print("❌ Génération échouée (quota Groq). Arrêt pour ne pas écraser de bonnes réponses.")
            print("   Réessaie plus tard : python src/evaluation/1_generer_reponses.py")
            return

        # Pause anti rate-limit (10s entre chaque génération)
        if i < total:
            time.sleep(10)

    # ── Sauvegarde (uniquement si toutes les réponses OK) ──
    paquet = {
        "date_generation" : datetime.now().isoformat(),
        "nb_exemples"     : len(donnees),
        "latence_moyenne" : round(sum(d["latence_sec"] for d in donnees) / len(donnees), 2),
        "tokens_total"    : sum(d["tokens"] for d in donnees),
        "donnees"         : donnees,
    }

    with open(fichier_sortie, "w", encoding="utf-8") as f:
        json.dump(paquet, f, ensure_ascii=False, indent=2)

    print("="*60)
    print(f"✅ {len(donnees)} réponses générées et sauvegardées")
    print(f"💾 Fichier : {fichier_sortie}")
    print(f"⏱  Latence moyenne : {paquet['latence_moyenne']}s")
    print(f"🔢 Tokens consommés : {paquet['tokens_total']}")
    print("="*60)
    print("\n👉 Étape suivante : python src/evaluation/2_evaluer_ragas.py")


if __name__ == "__main__":
    main()