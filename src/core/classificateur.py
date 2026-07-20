"""Classification de l'intention, du domaine et de la complexité."""

from __future__ import annotations

import re
from typing import Optional

from core.schemas import AnalyseQuestion
from generation.generateur_reponse import (
    demande_code_explicite,
    est_cahier_des_charges,
    est_demande_maths,
    est_demande_projet,
    est_demande_roadmap,
    est_demande_technique,
    est_salutation,
    necessite_recherche_web,
)


DOMAINES = {
    "fastapi": ("fastapi", "pydantic", "uvicorn", "httpexception"),
    "flask": ("flask", "jinja", "werkzeug", "jsonify"),
    "python": ("python", "py", "pathlib", "pytest"),
    "docker": ("docker", "dockerfile", "compose", "container"),
    "sql": ("sql", "postgres", "mysql", "sqlite", "query", "requête"),
    "react": ("react", "jsx", "useeffect", "usestate"),
    "architecture": ("architecture", "microservice", "monolithe", "design pattern"),
    "debug": ("bug", "erreur", "traceback", "exception", "corrige"),
}


class ClassificateurAssistant:
    def analyser(self, question: str, mode_force: Optional[str] = None, a_un_fichier: bool = False) -> AnalyseQuestion:
        q = (question or "").strip()
        q_low = q.lower()

        if mode_force == "technique":
            mode = "technique"
        elif mode_force == "projet":
            mode = "projet"
        elif mode_force == "cdc":
            mode = "projet"
        elif mode_force == "texte" and est_salutation(q):
            mode = "conversation"
        elif est_salutation(q):
            mode = "conversation"
        elif any(x in q_low for x in ("résume", "resume", "fais un résumé", "fais un resume", "summarize")):
            mode = "resume"
        elif any(x in q_low for x in ("traduit", "traduire", "translate", "en anglais", "en français")):
            mode = "redaction"
        elif any(
            x in q_low
            for x in (
                "cours sur", "fais un cours", "comme un professeur", "enseigne",
                "leçon", "lecon", "tutoriel complet", "apprendre",
            )
        ) or (
            any(x in q_low for x in ("explique", "explication", "guide", "architecture"))
            and any(x in q_low for x in ("cours", "débutant", "debutant", "étape par étape", "etape par etape", "concepts"))
        ):
            mode = "cours"
        elif any(x in q_low for x in ("mode expert", "niveau expert", "en profondeur", "analyse experte")):
            mode = "expert"
        elif est_cahier_des_charges(q) or est_demande_projet(q):
            mode = "projet"
        elif demande_code_explicite(q) and any(
            x in q_low
            for x in (
                "écris", "ecris", "génère", "genere", "implémente", "implemente",
                "code pour", "fonction qui", "fonction python", "script qui", "classe qui",
            )
        ):
            mode = "code"
        elif est_demande_maths(q):
            mode = "maths"
        elif any(x in q_low for x in ("compare", "compar", "différence entre", "vs ", "versus")):
            mode = "comparaison"
        elif any(x in q_low for x in ("debug", "corrige", "bug", "erreur", "traceback", "ne marche pas")):
            mode = "debug"
        elif any(x in q_low for x in ("email", "mail", "lettre", "cv", "message", "rapport", "rédige", "redige")):
            mode = "redaction"
        elif any(x in q_low for x in ("documentation", "doc", "readme", "api reference", "guide d'utilisation")):
            mode = "documentation"
        elif est_demande_roadmap(q):
            mode = "projet"
        elif necessite_recherche_web(q) and any(
            x in q_low
            for x in (
                "actualité", "actualite", "aujourd'hui", "2024", "2025", "2026",
                "dernière version", "derniere version", "latest", "prix", "news",
                "cherche sur", "selon internet", "sources web",
            )
        ):
            mode = "perplexity"
        elif est_demande_technique(q) or (a_un_fichier and demande_code_explicite(q)):
            mode = "technique"
        elif necessite_recherche_web(q):
            mode = "explication"
        elif any(x in q_low for x in ("explique", "qu'est-ce", "quest-ce", "c'est quoi", "comment ça marche", "comment ca marche")):
            mode = "cours" if len(q) > 40 else "explication"
        else:
            mode = "conversation"

        domaine = self._detecter_domaine(q_low)
        complexite = self._detecter_complexite(q)
        besoin_code = mode in {"technique", "debug", "code", "projet"} or demande_code_explicite(q)

        besoin_rag = mode in {
            "technique", "debug", "comparaison", "documentation",
            "analyse", "cours", "expert", "code",
        }
        besoin_web = mode in {"explication", "comparaison", "analyse", "perplexity", "cours", "expert"} or (
            mode in {"technique", "debug", "documentation", "code"} and complexite != "simple"
        )
        if domaine != "general" and mode in {"explication", "technique", "debug", "documentation", "cours", "code"}:
            besoin_rag = True
        # Mode projet = mentorat : pas de RAG GitHub par défaut (évite sources hors sujet).
        # RAG seulement si une techno du corpus est explicitement ciblée.
        if mode == "projet":
            stack_corpus = domaine in {
                "fastapi", "flask", "django", "react", "docker", "jwt", "python", "sql",
            } or any(
                k in q_low
                for k in (
                    "fastapi", "flask", "django", "react", "docker", "jwt",
                    "postgres", "postgresql", "sqlite", "sqlalchemy",
                )
            )
            besoin_rag = stack_corpus
            besoin_web = any(
                s in q_low
                for s in (
                    "actualité", "actualite", "2024", "2025", "2026",
                    "dernière version", "derniere version", "latest",
                )
            )
        if mode in {"conversation", "maths", "redaction", "resume"}:
            besoin_rag = False
            besoin_web = False
        if mode == "perplexity":
            besoin_rag = False
            besoin_web = True

        besoin_comparaison = mode == "comparaison"
        besoin_tutoriel = bool(re.search(r"\b(étape par étape|tutoriel|pas à pas)\b", q_low))
        besoin_projet = mode == "projet"
        besoin_maths = mode == "maths"
        besoin_schema = mode in {"projet", "comparaison", "analyse", "cours", "expert"} and any(
            mot in q_low for mot in ("architecture", "schéma", "schema", "diagramme")
        )
        # Abstention corpus : modes doc technique uniquement (pas le mentorat projet)
        besoin_abstention = mode in {"technique", "debug", "documentation", "code"}

        if besoin_rag and besoin_web:
            strategie = "hybride"
        elif besoin_rag:
            strategie = "rag"
        elif besoin_web:
            strategie = "web"
        else:
            strategie = "aucune"

        notes = []
        if a_un_fichier:
            notes.append("fichiers_joints")
        if besoin_tutoriel:
            notes.append("tutoriel")
        if mode in {"cours", "expert"}:
            notes.append("mode_expert")
        if mode == "perplexity":
            notes.append("mode_perplexity")

        return AnalyseQuestion(
            mode=mode,
            domaine=domaine,
            complexite=complexite,
            besoin_rag=besoin_rag,
            besoin_web=besoin_web,
            besoin_code=besoin_code,
            besoin_comparaison=besoin_comparaison,
            besoin_exemples=(mode != "conversation"),
            besoin_schema=besoin_schema,
            besoin_tutoriel=besoin_tutoriel,
            besoin_projet=besoin_projet,
            besoin_maths=besoin_maths,
            besoin_abstention=besoin_abstention,
            strategie_sources=strategie,
            notes=notes,
        )

    def _detecter_domaine(self, q_low: str) -> str:
        for domaine, mots in DOMAINES.items():
            if any(m in q_low for m in mots):
                return domaine
        return "general"

    def _detecter_complexite(self, question: str) -> str:
        q = question.lower()
        score = 0
        if len(question) > 180:
            score += 1
        if len(question) > 500:
            score += 1
        if any(m in q for m in ("compare", "architecture", "système", "projet complet", "de a à z", "debug", "cours")):
            score += 1
        if question.count("\n") >= 5:
            score += 1
        return "complexe" if score >= 3 else "moyenne" if score >= 1 else "simple"
