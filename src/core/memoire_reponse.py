"""Mémoire légère de style/préférences dérivée de l'historique."""

from __future__ import annotations

from typing import Dict, List


class MemoireReponse:
    def extraire_preferences(self, historique: List[Dict]) -> Dict[str, str]:
        if not historique:
            return {}
        prefs: Dict[str, str] = {}
        contenus = " ".join((m.get("content") or "").lower() for m in historique[-8:])

        if "court" in contenus or "concis" in contenus:
            prefs["longueur"] = "courte"
        elif "détaille" in contenus or "detaille" in contenus or "explique" in contenus:
            prefs["longueur"] = "détaillée"

        if "étape par étape" in contenus or "pas à pas" in contenus:
            prefs["style"] = "pas_a_pas"

        if "exemple" in contenus:
            prefs["exemples"] = "souhaités"

        return prefs

