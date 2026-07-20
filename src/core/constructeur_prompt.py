"""Assemblage des prompts système/utilisateur à partir des modules texte."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from core.gestionnaire_modes import obtenir_mode
from core.schemas import AnalyseQuestion, PlanReponse
from retrieval.contexte import resume_contexte_global


class ConstructeurPrompt:
    def __init__(self, prompts_dir: Path | None = None):
        self.prompts_dir = prompts_dir or Path(__file__).resolve().parents[1] / "prompts"

    def construire(
        self,
        question: str,
        analyse: AnalyseQuestion,
        plan: PlanReponse,
        documents: List[Dict],
        ressources_web: List[Dict],
        historique: List[Dict] | None = None,
        contexte_fichiers: str = "",
        preferences: Dict | None = None,
        preferences_longues: Dict | None = None,
        contexte_projet: str = "",
        insights: str = "",
        comprehension: str = "",
    ) -> tuple[str, str]:
        mode_def = obtenir_mode(analyse.mode)
        system_core = self._charger("system_core.txt")
        constitution = self._charger("constitution.md", obligatoire=False)
        mode_prompt = self._charger(mode_def.prompt_mode)
        domain_prompt = self._charger(f"domain_{analyse.domaine}.txt", obligatoire=False)
        qualite_prompt = self._charger("qualite_reponse.txt", obligatoire=False)

        historique_txt = self._formater_historique(historique or [])
        docs_txt = self._formater_docs(documents, question=question)
        web_txt = self._formater_web(ressources_web)
        plan_txt = self._formater_plan(plan)
        prefs_txt = self._formater_preferences(preferences or {})
        prefs_lt = self._formater_preferences_longues(preferences_longues or {})

        system_prompt = "\n\n".join(
            bloc
            for bloc in [
                system_core,
                constitution,
                mode_prompt,
                domain_prompt,
                qualite_prompt,
                prefs_txt,
                prefs_lt,
                insights,
            ]
            if bloc and bloc.strip()
        )
        user_prompt = f"""Question utilisateur :
{question}

Compréhension :
{comprehension or "Analyser l'intention et répondre de façon ciblée."}

Analyse décidée :
- mode: {analyse.mode}
- domaine: {analyse.domaine}
- complexité: {analyse.complexite}
- besoin_code: {analyse.besoin_code}
- besoin_rag: {analyse.besoin_rag}
- besoin_web: {analyse.besoin_web}
- strategie_sources: {getattr(analyse, "strategie_sources", "n/a")}

Plan attendu (passe planification) :
{plan_txt}

{contexte_projet or "Mémoire projet : aucune."}

Historique récent :
{historique_txt}

Contexte fichiers joints :
{contexte_fichiers or "Aucun fichier joint."}

Contexte RAG (chunks résumés / classés par thème) :
{docs_txt}

Ressources web :
{web_txt}

Instructions finales (passes réponse → critique → amélioration) :
- Réponds d'abord directement à la question.
- Adapte ton niveau à la demande et aux préférences.
- Reste strictement dans le sujet.
- Si le contexte RAG est vide ou faible, n'invente pas de faits documentaires.
- Les éléments du plan ci-dessus sont des consignes d'organisation, pas des titres obligatoires à recopier.
- Privilégie les chunks dont le thème correspond à la question.
- Si des ressources web sont fournies, cite-les seulement quand elles apportent une info utile.
- Relis mentalement ta réponse : complète, exacte, exemples/code si nécessaires.
"""
        return system_prompt.strip(), user_prompt.strip()

    def _charger(self, nom: str, obligatoire: bool = True) -> str:
        path = self.prompts_dir / nom
        if path.exists():
            return path.read_text(encoding="utf-8")
        if obligatoire:
            raise FileNotFoundError(f"Prompt introuvable : {path}")
        return ""

    def _formater_historique(self, historique: List[Dict]) -> str:
        if not historique:
            return "Aucun."
        lignes = []
        for msg in historique[-8:]:
            role = msg.get("role", "user")
            contenu = (msg.get("content") or "").strip()
            if contenu:
                lignes.append(f"- {role}: {contenu[:300]}")
        return "\n".join(lignes) if lignes else "Aucun."

    def _formater_docs(self, documents: List[Dict], question: str = "") -> str:
        if not documents:
            return "Aucun document RAG."
        if any(d.get("theme") or d.get("resume_auto") for d in documents):
            return resume_contexte_global(documents[:6], requete=question, max_chars_total=4200)
        par_theme: Dict[str, List[Dict]] = {}
        for doc in documents[:6]:
            theme = doc.get("theme") or "general"
            par_theme.setdefault(theme, []).append(doc)

        blocs = []
        idx = 1
        for theme, docs in par_theme.items():
            for doc in docs:
                resume_flag = "résumé" if doc.get("resume_auto") else "brut"
                blocs.append(
                    f"[Doc {idx}|{theme}|{resume_flag}] repo={doc.get('nom_complet','N/A')} | "
                    f"section={doc.get('section_titre','N/A')} | "
                    f"score={doc.get('score_confiance', doc.get('score_rerank', doc.get('score_dense', 0)))}\n"
                    f"{(doc.get('texte') or '')[:900]}"
                )
                idx += 1
        return "\n\n".join(blocs)

    def _formater_web(self, ressources: List[Dict]) -> str:
        if not ressources:
            return "Aucune ressource web."
        lignes = []
        for r in ressources[:6]:
            if r.get("url") and r.get("titre"):
                extrait = (r.get("extrait") or "").strip()
                ligne = f"- {r['titre'][:100]} | {r['url']}"
                if extrait:
                    ligne += f"\n  {extrait[:180]}"
                lignes.append(ligne)
        return "\n".join(lignes) if lignes else "Aucune ressource web."

    def _formater_plan(self, plan: PlanReponse) -> str:
        lignes = [
            f"- ton: {plan.ton}",
            f"- profondeur: {plan.profondeur}",
            f"- longueur_cible: {plan.longueur_cible}",
            "- organisation conseillée :",
        ]
        lignes.extend(f"  - {section}" for section in plan.sections)
        if plan.detail_etape_unique:
            lignes.append("- détailler uniquement l'étape 1 si projet")
        if plan.inclure_bonnes_pratiques:
            lignes.append("- inclure bonnes pratiques")
        if plan.inclure_pieges:
            lignes.append("- inclure erreurs fréquentes / pièges")
        return "\n".join(lignes)

    def _formater_preferences(self, preferences: Dict) -> str:
        if not preferences:
            return ""
        lignes = ["Préférences dérivées de l'historique courant :"]
        for cle, valeur in preferences.items():
            lignes.append(f"- {cle}: {valeur}")
        return "\n".join(lignes)

    def _formater_preferences_longues(self, preferences: Dict) -> str:
        if not preferences:
            return ""
        lignes = ["Préférences long terme :"]
        for cle, valeur in preferences.items():
            lignes.append(f"- {cle}: {valeur}")
        return "\n".join(lignes)

    def construire_comprehension(self, analyse: AnalyseQuestion, question: str) -> str:
        """Passe 'compréhension' sans appel LLM supplémentaire."""
        q = (question or "").strip()
        bits = [
            f"Intention détectée : mode={analyse.mode}, domaine={analyse.domaine}, complexité={analyse.complexite}.",
            f"Sources prévues : {getattr(analyse, 'strategie_sources', 'aucune')}.",
        ]
        if analyse.besoin_code:
            bits.append("La réponse doit inclure du code utile.")
        if analyse.besoin_projet:
            bits.append(
                "Traiter comme un projet : architecture et roadmap avant le code massif. "
                "Sans documents RAG fiables : mentorat pur, aucune citation inventée."
            )
        if analyse.mode in {"cours", "expert"}:
            bits.append("Répondre comme un professeur structuré.")
        if analyse.mode == "perplexity":
            bits.append("Synthèse sourcée à partir du web.")
        if analyse.mode == "resume":
            bits.append("Produire un résumé fidèle, sans invention.")
        if len(q) > 20:
            bits.append(f"Reformulation courte : {q[:160]}")
        return "\n".join(bits)
