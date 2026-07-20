"""Schémas partagés pour l'orchestration de l'assistant."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AnalyseQuestion:
    mode: str
    domaine: str = "general"
    complexite: str = "simple"
    besoin_rag: bool = False
    besoin_web: bool = False
    besoin_code: bool = False
    besoin_comparaison: bool = False
    besoin_exemples: bool = True
    besoin_schema: bool = False
    besoin_tutoriel: bool = False
    besoin_projet: bool = False
    besoin_maths: bool = False
    besoin_abstention: bool = False
    strategie_sources: str = "aucune"  # rag | web | hybride | aucune
    notes: List[str] = field(default_factory=list)


@dataclass
class PlanReponse:
    sections: List[str]
    ton: str = "professionnel"
    profondeur: str = "moyenne"
    longueur_cible: str = "moyenne"
    detail_etape_unique: bool = False
    inclure_exemple: bool = True
    inclure_bonnes_pratiques: bool = False
    inclure_pieges: bool = False
    inclure_conclusion: bool = True


@dataclass
class RapportQualite:
    valide: bool
    score: float
    problemes: List[str] = field(default_factory=list)
    commentaire: str = ""


@dataclass
class ResultatOrchestration:
    analyse: AnalyseQuestion
    plan: PlanReponse
    documents: List[Dict[str, Any]] = field(default_factory=list)
    ressources_web: List[Dict[str, Any]] = field(default_factory=list)
    prompt_systeme: str = ""
    prompt_utilisateur: str = ""
    reponse: str = ""
    reponse_seule: str = ""
    citations: str = ""
    mode: str = "conversation"
    tokens_utilises: int = 0
    abstention: bool = False
    rapport_qualite: Optional[RapportQualite] = None
    stream: Any = None
    usage_holder: Dict[str, Any] = field(default_factory=dict)
    contexte_projet: Dict[str, Any] = field(default_factory=dict)
    preferences_longues: Dict[str, str] = field(default_factory=dict)
    score_rag: float = 0.0
    meta_journal: Dict[str, Any] = field(default_factory=dict)
    images_generees: List[Dict[str, Any]] = field(default_factory=list)

