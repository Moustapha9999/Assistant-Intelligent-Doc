"""Gestion des modes fonctionnels de l'assistant."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class DefinitionMode:
    nom: str
    prompt_mode: str
    utilise_rag: bool
    utilise_web: bool
    detail_structure: bool


MODES: Dict[str, DefinitionMode] = {
    "conversation": DefinitionMode("conversation", "mode_conversation.txt", False, False, False),
    "explication": DefinitionMode("explication", "mode_conversation.txt", False, True, True),
    "technique": DefinitionMode("technique", "mode_technique.txt", True, True, True),
    "debug": DefinitionMode("debug", "mode_debug.txt", True, True, True),
    "projet": DefinitionMode("projet", "mode_projet.txt", False, False, True),
    "comparaison": DefinitionMode("comparaison", "mode_comparaison.txt", True, True, True),
    "redaction": DefinitionMode("redaction", "mode_redaction.txt", False, False, True),
    "maths": DefinitionMode("maths", "mode_maths.txt", False, False, True),
    "documentation": DefinitionMode("documentation", "mode_technique.txt", True, True, True),
    "analyse": DefinitionMode("analyse", "mode_comparaison.txt", True, True, True),
    "cours": DefinitionMode("cours", "mode_cours.txt", True, True, True),
    "expert": DefinitionMode("expert", "mode_expert.txt", True, True, True),
    "resume": DefinitionMode("resume", "mode_resume.txt", False, False, True),
    "code": DefinitionMode("code", "mode_code.txt", True, True, True),
    "perplexity": DefinitionMode("perplexity", "mode_perplexity.txt", False, True, True),
}


def obtenir_mode(mode: str) -> DefinitionMode:
    return MODES.get(mode, MODES["conversation"])
