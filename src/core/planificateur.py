"""Planification de la forme de réponse avant génération."""

from __future__ import annotations

from core.schemas import AnalyseQuestion, PlanReponse


class PlanificateurAssistant:
    def construire_plan(self, analyse: AnalyseQuestion) -> PlanReponse:
        mode = analyse.mode

        if mode == "code":
            return PlanReponse(
                sections=[
                    "fournir le code complet et exécutable",
                    "analyser brièvement le code",
                    "expliquer les parties importantes",
                    "proposer des tests minimaux",
                    "indiquer des optimisations",
                    "proposer une alternative",
                    "signaler les erreurs fréquentes",
                ],
                ton="technique",
                profondeur="élevée",
                longueur_cible="longue",
                inclure_exemple=True,
                inclure_bonnes_pratiques=True,
                inclure_pieges=True,
            )
        if mode in {"cours", "expert"}:
            return PlanReponse(
                sections=[
                    "introduction",
                    "concepts clés",
                    "pourquoi c'est important",
                    "exemple concret",
                    "code ou démonstration si utile",
                    "cas réel",
                    "pièges",
                    "bonnes pratiques",
                    "alternatives",
                    "résumé",
                    "exercices",
                    "ressources",
                ],
                ton="professeur",
                profondeur="élevée",
                longueur_cible="longue",
                inclure_exemple=True,
                inclure_bonnes_pratiques=True,
                inclure_pieges=True,
            )
        if mode == "resume":
            return PlanReponse(
                sections=["résumé essentiel", "points clés", "conclusion courte"],
                ton="clair",
                profondeur="courte",
                longueur_cible="courte",
                inclure_exemple=False,
                inclure_conclusion=True,
            )
        if mode == "perplexity":
            return PlanReponse(
                sections=[
                    "réponse directe synthétique",
                    "points clés issus des sources",
                    "nuances / divergences",
                    "liste des sources utilisées",
                ],
                ton="informatif",
                profondeur="moyenne",
                longueur_cible="moyenne",
                inclure_exemple=False,
                inclure_conclusion=True,
            )
        if mode == "technique":
            return PlanReponse(
                sections=[
                    "ouvrir par une réponse directe",
                    "expliquer le concept simplement",
                    "dérouler l'implémentation étape par étape",
                    "donner du code complet si nécessaire",
                    "ajouter les bonnes pratiques utiles",
                    "signaler les erreurs fréquentes",
                    "terminer par les prochaines étapes",
                ],
                ton="pédagogique",
                profondeur="élevée",
                longueur_cible="longue",
                inclure_exemple=True,
                inclure_bonnes_pratiques=True,
                inclure_pieges=True,
            )
        if mode == "debug":
            return PlanReponse(
                sections=[
                    "commencer par le diagnostic",
                    "expliquer la cause probable",
                    "proposer la correction",
                    "montrer le code corrigé si utile",
                    "indiquer les vérifications à faire",
                    "signaler les pièges courants",
                ],
                ton="analytique",
                profondeur="élevée",
                longueur_cible="moyenne",
                inclure_exemple=True,
                inclure_bonnes_pratiques=True,
                inclure_pieges=True,
            )
        if mode == "projet":
            return PlanReponse(
                sections=[
                    "commencer par la vue d'ensemble",
                    "proposer l'architecture",
                    "justifier les choix techniques",
                    "donner la roadmap complète",
                    "lister les fichiers à créer",
                    "détailler uniquement l'étape 1",
                    "indiquer les tests à effectuer",
                    "annoncer l'étape suivante",
                ],
                ton="mentor",
                profondeur="élevée",
                longueur_cible="longue",
                detail_etape_unique=True,
                inclure_exemple=True,
                inclure_bonnes_pratiques=True,
                inclure_pieges=True,
            )
        if mode == "comparaison":
            return PlanReponse(
                sections=[
                    "ouvrir par une réponse brève",
                    "comparer les options de manière équilibrée",
                    "mettre en avant les avantages",
                    "présenter les limites",
                    "expliquer quand choisir chaque option",
                    "finir par une recommandation",
                ],
                ton="équilibré",
                profondeur="moyenne",
                longueur_cible="moyenne",
                inclure_exemple=True,
            )
        if mode == "redaction":
            return PlanReponse(
                sections=["rédiger directement le texte final"],
                ton="fluide",
                profondeur="moyenne",
                longueur_cible="moyenne",
                inclure_exemple=False,
                inclure_conclusion=False,
            )
        if mode == "maths":
            return PlanReponse(
                sections=["présenter la méthode", "dérouler les calculs", "indiquer la réponse finale"],
                ton="pédagogique",
                profondeur="moyenne",
                longueur_cible="moyenne",
                inclure_exemple=False,
                inclure_conclusion=False,
            )
        if mode in {"documentation", "analyse", "explication"}:
            return PlanReponse(
                sections=[
                    "ouvrir par une réponse brève",
                    "développer les points importants",
                    "ajouter un exemple concret",
                    "présenter les limites",
                    "donner les cas d'usage",
                ],
                ton="professionnel",
                profondeur="moyenne",
                longueur_cible="moyenne",
                inclure_exemple=True,
            )
        return PlanReponse(
            sections=["répondre naturellement"],
            ton="naturel",
            profondeur="courte",
            longueur_cible="courte",
            inclure_exemple=False,
            inclure_conclusion=False,
        )
