"""Mémoire long terme : préférences utilisateur persistantes (SQLite)."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

_USER_ID = "default"

_SIGNAUX = {
    "stack_fastapi": (r"\bfastapi\b", "fastapi"),
    "stack_flask": (r"\bflask\b", "flask"),
    "stack_django": (r"\bdjango\b", "django"),
    "stack_react": (r"\breact\b", "react"),
    "stack_postgres": (r"\b(postgres|postgresql)\b", "postgresql"),
    "prefere_code_complet": (r"\b(code complet|exemple complet|montrer le code)\b", "oui"),
    "prefere_long": (r"\b(détaille|detaille|explique en profondeur|réponse longue)\b", "oui"),
    "prefere_court": (r"\b(sois concis|réponse courte|brièvement|brievement)\b", "oui"),
    "veut_apprendre": (r"\b(apprendre|cours|explique-moi|je débute|je debute)\b", "oui"),
}


class MemoireLongue:
    def __init__(self, chemin: Optional[Path] = None):
        self.chemin = Path(chemin or config.HISTORIQUE_DB)
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.chemin), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS preferences_utilisateur (
                    user_id TEXT NOT NULL,
                    cle TEXT NOT NULL,
                    valeur TEXT NOT NULL,
                    maj_le TEXT NOT NULL,
                    PRIMARY KEY (user_id, cle)
                )
                """
            )

    def charger(self, user_id: str = _USER_ID) -> Dict[str, str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT cle, valeur FROM preferences_utilisateur WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        return {r["cle"]: r["valeur"] for r in rows}

    def definir(self, cle: str, valeur: str, user_id: str = _USER_ID) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO preferences_utilisateur (user_id, cle, valeur, maj_le)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, cle) DO UPDATE SET
                    valeur = excluded.valeur,
                    maj_le = excluded.maj_le
                """,
                (user_id, cle, valeur, now),
            )

    def fusionner(self, prefs: Dict[str, Any], user_id: str = _USER_ID) -> None:
        for cle, valeur in (prefs or {}).items():
            if valeur is None or valeur == "":
                continue
            self.definir(str(cle), str(valeur), user_id=user_id)

    def extraire_depuis_texte(self, texte: str) -> Dict[str, str]:
        """Déduit des préférences depuis un message utilisateur."""
        t = (texte or "").lower()
        trouvees: Dict[str, str] = {}
        stacks = []
        for cle, (pattern, val) in _SIGNAUX.items():
            if re.search(pattern, t):
                if cle.startswith("stack_"):
                    stacks.append(val)
                else:
                    trouvees[cle.replace("prefere_", "").replace("veut_", "")] = val
        if stacks:
            # Garde les stacks uniques, max 5
            existantes = []
            try:
                existantes = json.loads(self.charger().get("stacks", "[]"))
            except Exception:
                existantes = []
            merged = []
            for s in existantes + stacks:
                if s not in merged:
                    merged.append(s)
            trouvees["stacks"] = json.dumps(merged[:5], ensure_ascii=False)
        if "code_complet" in trouvees:
            trouvees["code_complet"] = "oui"
        if trouvees.get("long") == "oui" and trouvees.get("court") == "oui":
            # Conflit : dernier signal gagne via ordre d'apparition
            if t.rfind("concis") > t.rfind("détail") and t.rfind("concis") > t.rfind("detail"):
                trouvees.pop("long", None)
            else:
                trouvees.pop("court", None)
        return trouvees

    def mettre_a_jour_depuis_echange(
        self,
        question: str,
        mode: str = "",
        user_id: str = _USER_ID,
    ) -> Dict[str, str]:
        extras = self.extraire_depuis_texte(question)
        if mode in {"cours", "expert"} or "apprendre" in extras:
            extras["apprendre"] = "oui"
        if mode == "projet":
            extras["style_mentorat"] = "oui"
        if extras:
            self.fusionner(extras, user_id=user_id)
        return self.charger(user_id)

    def formater_pour_prompt(self, prefs: Optional[Dict[str, str]] = None) -> str:
        prefs = prefs if prefs is not None else self.charger()
        if not prefs:
            return ""
        lignes = ["Préférences long terme de l'utilisateur :"]
        for cle, valeur in prefs.items():
            if cle == "stacks":
                try:
                    stacks = json.loads(valeur)
                    valeur = ", ".join(stacks) if isinstance(stacks, list) else valeur
                except Exception:
                    pass
            lignes.append(f"- {cle}: {valeur}")
        return "\n".join(lignes)
