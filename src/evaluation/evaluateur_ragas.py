"""
Module d'évaluation RAGAS du système RAG
Métriques : Faithfulness, Answer Relevancy, Context Recall, Context Precision
"""

import os
import json
import yaml
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()


class EvaluateurRAGAS:
    """
    Évalue la qualité du système RAG via les métriques RAGAS :
    - Faithfulness       : La réponse est-elle fidèle aux sources ?
    - Answer Relevancy   : La réponse répond-elle à la question ?
    - Context Recall     : Les documents récupérés couvrent-ils la réponse idéale ?
    - Context Precision  : Les documents récupérés sont-ils tous pertinents ?
    """

    def __init__(self):
        """Initialise l'évaluateur RAGAS avec le LLM Groq"""

        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.modele       = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
        self.base_dir     = Path(__file__).resolve().parent.parent.parent
        self.dossier_resultats = self.base_dir / "resultats" / "metrics"
        self.dossier_resultats.mkdir(parents=True, exist_ok=True)

        if not self.groq_api_key:
            raise ValueError("❌ GROQ_API_KEY manquante dans le fichier .env")

        self._initialiser_ragas()

    # ────────────────────────────────────────────────────────────────
    # INITIALISATION RAGAS
    # ────────────────────────────────────────────────────────────────

    def _initialiser_ragas(self):
        """Initialise les métriques et le LLM RAGAS via Groq"""
        try:
            from ragas import evaluate
            from ragas.metrics import (
                faithfulness,
                answer_relevancy,
                context_recall,
                context_precision,
            )
            from langchain_groq import ChatGroq
            from langchain_community.embeddings import HuggingFaceEmbeddings

            # LLM juge (Groq)
            self.llm_juge = ChatGroq(
                api_key    =self.groq_api_key,
                model_name =self.modele,
                temperature=0.0,
            )

            # Embeddings pour Answer Relevancy
            cache_folder = str(self.base_dir / "models_cache")
            self.embeddings_ragas = HuggingFaceEmbeddings(
                model_name   ="all-MiniLM-L6-v2",
                cache_folder =cache_folder,
            )

            # Métriques RAGAS
            self.metriques = [
                faithfulness,
                answer_relevancy,
                context_recall,
                context_precision,
            ]

            self.evaluate_fn = evaluate
            print("✅ RAGAS initialisé avec succès")

        except ImportError as e:
            print(f"⚠️  RAGAS non disponible : {e}")
            print("   Installez : pip install ragas langchain-groq langchain-community")
            self.evaluate_fn = None
            self.metriques   = []

    # ────────────────────────────────────────────────────────────────
    # ÉVALUATION D'UN SEUL EXEMPLE
    # ────────────────────────────────────────────────────────────────

    def evaluer_exemple(
        self,
        question          : str,
        reponse_generee   : str,
        documents_contexte: List[Dict],
        reponse_ideale    : Optional[str] = None,
    ) -> Dict:
        """
        Évalue un seul exemple (question → réponse → contexte).

        Args:
            question           : Question posée par l'utilisateur
            reponse_generee    : Réponse produite par le système RAG
            documents_contexte : Documents récupérés par le retrieval
            reponse_ideale     : Réponse de référence (optionnel, pour Context Recall)

        Returns:
            Dict avec les scores RAGAS et les métadonnées
        """
        if self.evaluate_fn is None:
            return self._evaluer_heuristique(
                question, reponse_generee, documents_contexte
            )

        try:
            from datasets import Dataset

            # Préparation du dataset RAGAS
            contextes = [doc.get("texte", "")[:800] for doc in documents_contexte]

            sample = {
                "question"  : [question],
                "answer"    : [reponse_generee],
                "contexts"  : [contextes],
            }
            if reponse_ideale:
                sample["ground_truth"] = [reponse_ideale]

            dataset = Dataset.from_dict(sample)

            # Sélection des métriques selon disponibilité de ground_truth
            metriques_actives = (
                self.metriques
                if reponse_ideale
                else [m for m in self.metriques if m.name not in
                      ("context_recall", "context_precision")]
            )

            # Évaluation RAGAS
            resultats = self.evaluate_fn(
                dataset   =dataset,
                metrics   =metriques_actives,
                llm       =self.llm_juge,
                embeddings=self.embeddings_ragas,
            )

            scores = resultats.to_pandas().iloc[0].to_dict()

            return {
                "question"          : question,
                "reponse"           : reponse_generee,
                "nb_documents"      : len(documents_contexte),
                "faithfulness"      : round(float(scores.get("faithfulness",      0)), 4),
                "answer_relevancy"  : round(float(scores.get("answer_relevancy",  0)), 4),
                "context_recall"    : round(float(scores.get("context_recall",    0)), 4),
                "context_precision" : round(float(scores.get("context_precision", 0)), 4),
                "methode"           : "ragas",
                "timestamp"         : datetime.now().isoformat(),
            }

        except Exception as e:
            print(f"   ⚠️  Erreur RAGAS : {e} → bascule sur heuristique")
            return self._evaluer_heuristique(
                question, reponse_generee, documents_contexte
            )

    # ────────────────────────────────────────────────────────────────
    # ÉVALUATION HEURISTIQUE (fallback sans RAGAS)
    # ────────────────────────────────────────────────────────────────

    def _evaluer_heuristique(
        self,
        question          : str,
        reponse           : str,
        documents_contexte: List[Dict],
    ) -> Dict:
        """
        Évaluation heuristique légère si RAGAS n'est pas disponible.
        Calcule des proxys simples basés sur le chevauchement de tokens.
        """
        tokens_question = set(question.lower().split())
        tokens_reponse  = set(reponse.lower().split())

        # Proxy Faithfulness : taux de mots de la réponse présents dans le contexte
        texte_contexte  = " ".join(d.get("texte", "") for d in documents_contexte).lower()
        tokens_contexte = set(texte_contexte.split())
        communs_rep_ctx = tokens_reponse & tokens_contexte
        faithfulness_proxy = (
            len(communs_rep_ctx) / len(tokens_reponse)
            if tokens_reponse else 0.0
        )

        # Proxy Answer Relevancy : chevauchement question/réponse
        communs_q_rep = tokens_question & tokens_reponse
        relevancy_proxy = (
            len(communs_q_rep) / len(tokens_question)
            if tokens_question else 0.0
        )

        # Proxy Context Precision : % de documents ayant des mots de la question
        nb_pertinents = sum(
            1 for d in documents_contexte
            if tokens_question & set(d.get("texte", "").lower().split())
        )
        precision_proxy = (
            nb_pertinents / len(documents_contexte)
            if documents_contexte else 0.0
        )

        return {
            "question"          : question,
            "reponse"           : reponse,
            "nb_documents"      : len(documents_contexte),
            "faithfulness"      : round(min(faithfulness_proxy, 1.0), 4),
            "answer_relevancy"  : round(min(relevancy_proxy * 2, 1.0), 4),
            "context_recall"    : 0.0,
            "context_precision" : round(precision_proxy, 4),
            "methode"           : "heuristique",
            "timestamp"         : datetime.now().isoformat(),
        }

    # ────────────────────────────────────────────────────────────────
    # ÉVALUATION D'UN JEU DE DONNÉES COMPLET
    # ────────────────────────────────────────────────────────────────

    def evaluer_dataset(
        self,
        questions         : List[str],
        reponses          : List[str],
        documents_listes  : List[List[Dict]],
        reponses_ideales  : Optional[List[str]] = None,
    ) -> Dict:
        """
        Évalue un jeu de données complet et calcule les moyennes.

        Returns:
            Dict avec scores moyens + résultats détaillés par exemple
        """
        print(f"\n📊 Évaluation de {len(questions)} exemples...")
        resultats_detail = []

        for i, (question, reponse, documents) in enumerate(
            zip(questions, reponses, documents_listes), 1
        ):
            print(f"   [{i}/{len(questions)}] {question[:60]}...")
            ref = reponses_ideales[i - 1] if reponses_ideales else None
            res = self.evaluer_exemple(question, reponse, documents, ref)
            resultats_detail.append(res)

        # Calcul des moyennes
        def moyenne(cle):
            vals = [r[cle] for r in resultats_detail if r[cle] > 0]
            return round(sum(vals) / len(vals), 4) if vals else 0.0

        rapport = {
            "nb_exemples"       : len(questions),
            "faithfulness_moy"  : moyenne("faithfulness"),
            "relevancy_moy"     : moyenne("answer_relevancy"),
            "recall_moy"        : moyenne("context_recall"),
            "precision_moy"     : moyenne("context_precision"),
            "score_global"      : round(
                (moyenne("faithfulness") + moyenne("answer_relevancy")) / 2, 4
            ),
            "resultats_detail"  : resultats_detail,
            "timestamp"         : datetime.now().isoformat(),
        }

        self._sauvegarder_rapport(rapport)
        self.afficher_rapport(rapport)
        return rapport

    # ────────────────────────────────────────────────────────────────
    # JEU DE TEST PAR DÉFAUT (10 questions ISI KOMUNIK)
    # ────────────────────────────────────────────────────────────────

    def charger_dataset_test(self) -> List[Dict]:
        """
        Retourne un jeu de 10 questions de test représentatives
        du contexte ISI KOMUNIK.
        """
        return [
            {
                "question"       : "Comment créer une API REST avec Flask en Python ?",
                "reponse_ideale" : "Flask est un micro-framework Python. On crée une API REST en définissant des routes avec les décorateurs @app.route().",
            },
            {
                "question"       : "Comment gérer l'authentification JWT dans une application web ?",
                "reponse_ideale" : "JWT (JSON Web Token) est utilisé pour l'authentification. On génère un token signé avec une clé secrète.",
            },
            {
                "question"       : "Comment optimiser les requêtes SQL dans Django ?",
                "reponse_ideale" : "Django ORM permet d'optimiser avec select_related(), prefetch_related() et values() pour réduire les requêtes N+1.",
            },
            {
                "question"       : "Comment utiliser les hooks dans React ?",
                "reponse_ideale" : "Les hooks React (useState, useEffect) permettent d'utiliser l'état et le cycle de vie dans les composants fonctionnels.",
            },
            {
                "question"       : "Comment gérer les erreurs avec try/catch en JavaScript ?",
                "reponse_ideale" : "Le bloc try/catch permet de capturer les exceptions. On utilise throw pour lever des erreurs personnalisées.",
            },
            {
                "question"       : "Comment créer un middleware dans Express.js ?",
                "reponse_ideale" : "Un middleware Express est une fonction (req, res, next) qui s'exécute entre la requête et la réponse.",
            },
            {
                "question"       : "Comment lire et écrire des fichiers en Python ?",
                "reponse_ideale" : "Python utilise open() avec les modes 'r', 'w', 'a'. Le gestionnaire with garantit la fermeture du fichier.",
            },
            {
                "question"       : "Comment faire du scraping web avec BeautifulSoup ?",
                "reponse_ideale" : "BeautifulSoup parse le HTML. On utilise find() et find_all() pour extraire les éléments.",
            },
            {
                "question"       : "Comment gérer les dépendances avec npm en JavaScript ?",
                "reponse_ideale" : "npm install ajoute des dépendances dans package.json. --save-dev pour les dépendances de développement.",
            },
            {
                "question"       : "Comment créer une connexion à une base de données avec SQLAlchemy ?",
                "reponse_ideale" : "SQLAlchemy utilise create_engine() avec l'URL de connexion. Session gère les transactions.",
            },
        ]

    # ────────────────────────────────────────────────────────────────
    # SAUVEGARDE DU RAPPORT
    # ────────────────────────────────────────────────────────────────

    def _sauvegarder_rapport(self, rapport: Dict) -> None:
        """Sauvegarde le rapport d'évaluation en JSON"""
        horodatage = datetime.now().strftime("%Y%m%d_%H%M%S")
        fichier    = self.dossier_resultats / f"evaluation_{horodatage}.json"

        with open(fichier, "w", encoding="utf-8") as f:
            json.dump(rapport, f, ensure_ascii=False, indent=2)

        print(f"\n💾 Rapport sauvegardé : {fichier}")

    # ────────────────────────────────────────────────────────────────
    # AFFICHAGE DU RAPPORT
    # ────────────────────────────────────────────────────────────────

    def afficher_rapport(self, rapport: Dict) -> None:
        """Affiche le rapport d'évaluation dans le terminal"""
        print("\n" + "═" * 60)
        print("📊 RAPPORT D'ÉVALUATION RAGAS")
        print("═" * 60)
        print(f"  Exemples évalués   : {rapport['nb_exemples']}")
        print(f"  Faithfulness       : {rapport['faithfulness_moy']:.4f}  (cible > 0.90)")
        print(f"  Answer Relevancy   : {rapport['relevancy_moy']:.4f}  (cible > 0.80)")
        print(f"  Context Recall     : {rapport['recall_moy']:.4f}  (cible > 0.75)")
        print(f"  Context Precision  : {rapport['precision_moy']:.4f}  (cible > 0.80)")
        print(f"  ─────────────────────────────────────────────")
        print(f"  Score global       : {rapport['score_global']:.4f}")

        # Indicateur visuel
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


# ────────────────────────────────────────────────────────────────────
# TEST RAPIDE
# ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from retrieval.retrieval_hybride import RetrievalHybride
    from generation.generateur_reponse import GenerateurReponse

    moteur     = RetrievalHybride()
    generateur = GenerateurReponse()
    evaluateur = EvaluateurRAGAS()

    # Charger le jeu de test
    dataset = evaluateur.charger_dataset_test()

    questions        = []
    reponses         = []
    documents_listes = []
    reponses_ideales = []

    print(f"\n🔄 Génération des réponses pour {len(dataset)} questions...")

    for exemple in dataset:
        question = exemple["question"]
        print(f"   → {question[:60]}...")

        docs     = moteur.rechercher(question, top_k_retrieval=20, top_k_final=5)
        resultat = generateur.generer(question, docs)

        questions.append(question)
        reponses.append(resultat["reponse_seule"])
        documents_listes.append(docs)
        reponses_ideales.append(exemple.get("reponse_ideale", ""))

    # Évaluation RAGAS
    rapport = evaluateur.evaluer_dataset(
        questions        =questions,
        reponses         =reponses,
        documents_listes =documents_listes,
        reponses_ideales =reponses_ideales,
    )