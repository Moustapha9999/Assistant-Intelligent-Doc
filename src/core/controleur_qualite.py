"""Contrôle qualité heuristique avec feedback de régénération ciblé."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from core.schemas import AnalyseQuestion, PlanReponse, RapportQualite


# Signaux souples (synonymes) — évite d'exiger une phrase exacte
_SIGNAUX_BONNES_PRATIQUES = (
    "bonne pratique", "bonnes pratiques", "best practice", "recommand",
    "à privilégier", "a privilegier", "conseil", "idéalement", "idealement",
    "en production", "préfère", "prefere",
)
_SIGNAUX_PIEGES = (
    "erreur fréquente", "erreurs fréquentes", "piège", "piege", "attention",
    "à éviter", "a eviter", "ne pas", "anti-pattern", "antipattern", "warning",
    "erreur classique", "souvent oublié", "souvent oublie",
)
_SIGNAUX_EXEMPLE = (
    "exemple", "par exemple", "```", "def ", "class ", "curl ", "http://", "https://",
    "@app.", "from flask", "from fastapi",
)
_SIGNAUX_COMPARAISON = (
    "avantage", "inconvénient", "inconvenient", "limite", "versus", " vs ",
    "différence", "difference", "plutôt", "plutot", "choisir",
)
_SIGNAUX_DEBUG = (
    "cause", "diagnostic", "corrige", "correction", "vérifi", "verifi",
    "traceback", "exception", "fix",
)
_SIGNAUX_ARCHITECTURE = (
    "architecture", "couche", "module", "composant", "schéma", "schema",
    "diagramme", "stack",
)
_OUVERTURES_FAIBLES = (
    "bien sûr", "bien sur", "absolument", "excellente question",
    "je vais vous", "voici une réponse", "en tant qu'ia", "en tant qu'assistant",
    "avec plaisir", "bien entendu", "volontiers",
)
_REMPLISSAGE = (
    "il est important de noter", "dans le monde d'aujourd'hui",
    "au final, tout dépend", "n'hésitez pas à", "n hesit ez pas",
    "en conclusion, il faut retenir que tout",
)

_FEEDBACK_HUMANISE: Dict[str, str] = {
    "reponse_vide": "la réponse est vide — produis une vraie réponse",
    "reponse_trop_courte": "développe davantage (trop court pour la complexité)",
    "ouverture_faible": "commence directement par la réponse, sans formule creuse",
    "remplissage": "supprime le blabla générique, reste concret",
    "bonnes_pratiques_absentes": "ajoute 1-2 bonnes pratiques concrètes et actionnables",
    "pieges_absents": "signale au moins un piège / erreur fréquente",
    "etape_1_absente": "détaille clairement l'étape 1 (actions + fichiers/code)",
    "comparaison_incomplete": "équilibre avantages / limites des options",
    "structure_maths_absente": "montre la méthode puis la réponse finale clairement",
    "exemple_absent": "ajoute un exemple concret ou un extrait de code",
    "code_absent": "inclus un bloc de code exécutable minimal",
    "domaine_peu_visible": "ancre explicitement la réponse sur le domaine technique demandé",
    "pas_de_recommandation": "termine par une recommandation claire et justifiée",
    "debug_incomplet": "structure : diagnostic → cause → correction → vérifications",
    "architecture_absente": "ajoute une vue d'architecture / organisation des composants",
    "hors_sujet_probable": "reste strictement sur la question posée",
    "repetition": "élimine les passages répétitifs",
}

# Problèmes qui forcent presque toujours une régénération
_BLOQUANTS = frozenset({
    "reponse_vide",
    "code_absent",
    "etape_1_absente",
    "hors_sujet_probable",
    "ouverture_faible",
})


class ControleurQualite:
    def verifier(
        self,
        reponse: str,
        analyse: AnalyseQuestion,
        plan: PlanReponse,
        question: str = "",
    ) -> RapportQualite:
        score = 0.0
        max_score = 0.0
        problemes: List[str] = []
        contenu = (reponse or "").strip()
        # Ignore les préfixes d'erreur LLM
        if contenu.startswith("❌"):
            return RapportQualite(
                valide=False,
                score=0.0,
                problemes=["reponse_vide"],
                commentaire="Réponse en erreur LLM.",
            )
        contenu_low = contenu.lower()
        q_low = (question or "").lower()

        def check(ok: bool, poids: float, probleme: str | None = None) -> None:
            nonlocal score, max_score
            max_score += poids
            if ok:
                score += poids
            elif probleme:
                problemes.append(probleme)

        # 1. Présence
        check(bool(contenu), 1.5, "reponse_vide")
        if not contenu:
            return RapportQualite(
                valide=False,
                score=0.0,
                problemes=["reponse_vide"],
                commentaire="Réponse vide.",
            )

        # 2. Longueur adaptée
        mini = {
            "conversation": 15,
            "redaction": 80,
            "maths": 40,
            "explication": 90,
            "documentation": 100,
        }.get(analyse.mode, 110)
        if analyse.complexite == "complexe":
            mini = int(mini * 1.5)
        elif analyse.complexite == "moyenne":
            mini = int(mini * 1.15)
        check(len(contenu) >= mini or analyse.mode == "conversation", 1.0, "reponse_trop_courte")

        # 3. Ouverture utile
        if analyse.mode not in {"conversation"}:
            debut = contenu_low[:90].lstrip("#* \n")
            faible = any(debut.startswith(o) for o in _OUVERTURES_FAIBLES)
            check(not faible, 0.8, "ouverture_faible")

        # 4. Remplissage / phrases creuses
        if analyse.mode not in {"conversation"}:
            n_remplissage = sum(1 for r in _REMPLISSAGE if r in contenu_low)
            check(n_remplissage == 0, 0.4, "remplissage")

        # 5. Répétition grossière (même phrase 2×)
        if len(contenu) > 200:
            check(not self._detecte_repetition(contenu), 0.4, "repetition")

        # 6. Mode technique / debug
        if analyse.mode in {"technique", "debug"}:
            if plan.inclure_bonnes_pratiques:
                check(
                    self._contient(contenu_low, _SIGNAUX_BONNES_PRATIQUES),
                    1.0,
                    "bonnes_pratiques_absentes",
                )
            if plan.inclure_pieges:
                check(self._contient(contenu_low, _SIGNAUX_PIEGES), 1.0, "pieges_absents")
            if analyse.besoin_code:
                a_code = "```" in contenu or bool(
                    re.search(r"\b(def|class|import|from|@app\.|curl )\b", contenu)
                )
                check(a_code, 1.2, "code_absent")
            if analyse.mode == "debug":
                check(self._contient(contenu_low, _SIGNAUX_DEBUG), 0.8, "debug_incomplet")

        # 7. Projet
        if analyse.mode == "projet":
            check(
                any(
                    x in contenu_low
                    for x in ("étape 1", "etape 1", "première étape", "premiere etape", "étape 1 —")
                ),
                1.5,
                "etape_1_absente",
            )
            if analyse.besoin_schema or "architecture" in " ".join(plan.sections).lower():
                check(
                    self._contient(contenu_low, _SIGNAUX_ARCHITECTURE),
                    0.6,
                    "architecture_absente",
                )

        # 8. Comparaison
        if analyse.mode == "comparaison":
            check(self._contient(contenu_low, _SIGNAUX_COMPARAISON), 1.0, "comparaison_incomplete")
            check(
                any(x in contenu_low for x in ("recommand", "choisir", "préfère", "prefere", "optez")),
                0.6,
                "pas_de_recommandation",
            )

        # 9. Maths
        if analyse.mode == "maths":
            check(
                (
                    "méthode" in contenu_low
                    or "methode" in contenu_low
                    or "calcul" in contenu_low
                    or "étape" in contenu_low
                    or "etape" in contenu_low
                )
                and ("réponse" in contenu_low or "reponse" in contenu_low or "=" in contenu),
                1.0,
                "structure_maths_absente",
            )

        # 10. Exemple si demandé
        if plan.inclure_exemple and analyse.mode not in {"conversation", "redaction", "maths"}:
            check(self._contient(contenu_low, _SIGNAUX_EXEMPLE), 1.0, "exemple_absent")

        # 11. Ancrage domaine
        if analyse.domaine and analyse.domaine != "general" and analyse.mode in {
            "technique", "debug", "documentation", "projet", "comparaison"
        }:
            check(analyse.domaine.lower() in contenu_low, 0.5, "domaine_peu_visible")

        # 12. Hors-sujet léger : aucun mot significatif de la question
        if q_low and analyse.mode not in {"conversation", "maths"} and len(q_low) > 12:
            mots_q = self._mots_cles_question(q_low)
            if mots_q:
                hits = sum(1 for m in mots_q if m in contenu_low)
                check(hits >= max(1, len(mots_q) // 3), 0.7, "hors_sujet_probable")

        ratio = (score / max_score) if max_score else 0.0
        problemes = self._prioriser(problemes)
        bloquants = [p for p in problemes if p in _BLOQUANTS]

        if analyse.mode == "conversation":
            valide = ratio >= 0.5 and not bloquants
        elif analyse.mode in {"technique", "debug", "projet"}:
            valide = ratio >= 0.68 and len(bloquants) == 0
        else:
            valide = ratio >= 0.58 and "reponse_vide" not in problemes

        commentaire = self._commentaire(problemes, ratio, bloquants)
        return RapportQualite(
            valide=valide,
            score=round(ratio, 3),
            problemes=problemes,
            commentaire=commentaire,
        )

    def doit_regenerer(self, rapport: RapportQualite) -> bool:
        if rapport.valide:
            return False
        if not rapport.problemes:
            return False
        if any(p in _BLOQUANTS for p in rapport.problemes):
            return True
        return rapport.score < 0.55

    def construire_feedback_regeneration(
        self,
        rapport: RapportQualite,
        analyse: Optional[AnalyseQuestion] = None,
        question: str = "",
    ) -> str:
        if rapport.valide or not rapport.problemes:
            return ""

        # Bloquants d'abord, puis le reste (max 4)
        ordonnes = self._prioriser(rapport.problemes)
        points = [_FEEDBACK_HUMANISE.get(c, c.replace("_", " ")) for c in ordonnes[:4]]

        consignes_mode = ""
        if analyse:
            if analyse.mode == "technique":
                consignes_mode = (
                    "\nContrainte mode technique : réponse directe → concept bref → "
                    "exemple/code → bonnes pratiques → un piège."
                )
            elif analyse.mode == "debug":
                consignes_mode = (
                    "\nContrainte mode debug : diagnostic → cause probable → "
                    "correction → vérifications."
                )
            elif analyse.mode == "projet":
                consignes_mode = (
                    "\nContrainte mode projet : vue d'ensemble courte + architecture + "
                    "roadmap + détail UNIQUEMENT de l'étape 1."
                )
            elif analyse.mode == "comparaison":
                consignes_mode = (
                    "\nContrainte mode comparaison : verdict bref, tableau mental "
                    "avantages/limites, recommandation finale."
                )
            elif analyse.mode == "maths":
                consignes_mode = (
                    "\nContrainte mode maths : méthode détaillée puis réponse encadrée."
                )

        ancre = f"\nQuestion d'origine : {question.strip()}" if question.strip() else ""

        return (
            "Réécris une meilleure version de ta réponse précédente.\n"
            "Corrige précisément ces points :\n"
            + "\n".join(f"- {p}" for p in points)
            + consignes_mode
            + ancre
            + "\n\nRègles : garde le fond utile, enlève le blabla, commence directement "
            "par la réponse, n'invente pas de faits hors sujet."
        )

    def choisir_meilleure(
        self,
        reponse_a: str,
        rapport_a: RapportQualite,
        reponse_b: str,
        rapport_b: RapportQualite,
    ) -> Tuple[str, RapportQualite]:
        """Conserve la meilleure des deux versions (score, puis validité, puis longueur utile)."""
        if rapport_b.valide and not rapport_a.valide:
            return reponse_b, rapport_b
        if rapport_a.valide and not rapport_b.valide:
            return reponse_a, rapport_a
        if rapport_b.score > rapport_a.score + 0.02:
            return reponse_b, rapport_b
        if rapport_a.score > rapport_b.score + 0.02:
            return reponse_a, rapport_a
        # À score égal : préférer moins de problèmes bloquants
        ba = sum(1 for p in rapport_a.problemes if p in _BLOQUANTS)
        bb = sum(1 for p in rapport_b.problemes if p in _BLOQUANTS)
        if bb < ba:
            return reponse_b, rapport_b
        if ba < bb:
            return reponse_a, rapport_a
        # Sinon la plus longue si l'autre est trop courte
        if len(reponse_b) > len(reponse_a) * 1.25 and len(reponse_a) < 200:
            return reponse_b, rapport_b
        return reponse_a, rapport_a

    @staticmethod
    def _mots_cles_question(q_low: str) -> List[str]:
        stop = {
            "comment", "quoi", "quel", "quelle", "quels", "quelles", "avec", "pour",
            "dans", "une", "des", "les", "sur", "par", "est", "que", "qui", "donc",
            "faire", "peux", "peut", "vous", "moi", "the", "and", "for", "how",
        }
        mots = re.findall(r"[a-zA-Zàâäéèêëïîôùûüç0-9_+#.-]{3,}", q_low)
        return [m for m in mots if m not in stop][:8]

    @staticmethod
    def _detecte_repetition(texte: str) -> bool:
        phrases = [p.strip().lower() for p in re.split(r"[.!?]\s+", texte) if len(p.strip()) > 40]
        if len(phrases) < 2:
            return False
        vues = set()
        for p in phrases:
            cle = p[:80]
            if cle in vues:
                return True
            vues.add(cle)
        return False

    @staticmethod
    def _contient(texte: str, signaux: Tuple[str, ...]) -> bool:
        return any(s in texte for s in signaux)

    @staticmethod
    def _prioriser(problemes: List[str]) -> List[str]:
        ordre = [
            "reponse_vide",
            "hors_sujet_probable",
            "ouverture_faible",
            "reponse_trop_courte",
            "code_absent",
            "etape_1_absente",
            "debug_incomplet",
            "exemple_absent",
            "bonnes_pratiques_absentes",
            "pieges_absents",
            "comparaison_incomplete",
            "pas_de_recommandation",
            "architecture_absente",
            "structure_maths_absente",
            "domaine_peu_visible",
            "remplissage",
            "repetition",
        ]
        rang = {p: i for i, p in enumerate(ordre)}
        # unique en gardant l'ordre de priorité
        vus = set()
        out = []
        for p in sorted(problemes, key=lambda x: rang.get(x, 99)):
            if p not in vus:
                vus.add(p)
                out.append(p)
        return out

    def _commentaire(
        self,
        problemes: List[str],
        ratio: float,
        bloquants: List[str],
    ) -> str:
        if not problemes:
            return f"Réponse jugée suffisante (score {ratio:.0%})."
        labels = [_FEEDBACK_HUMANISE.get(p, p) for p in problemes[:5]]
        prefix = "Bloquant. " if bloquants else ""
        return f"{prefix}Score {ratio:.0%}. À améliorer : " + " ; ".join(labels)
