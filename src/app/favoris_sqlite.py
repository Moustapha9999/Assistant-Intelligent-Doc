"""Favoris et collections de documents (SQLite)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FavorisSQLite:
    def __init__(self, chemin: Optional[Path] = None):
        self.chemin = Path(chemin or (config.DB_DIR / "favoris.db"))
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.chemin), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS collections (
                    id TEXT PRIMARY KEY,
                    nom TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    cree_le TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS favoris (
                    id TEXT PRIMARY KEY,
                    collection_id TEXT,
                    nom_complet TEXT,
                    source_file TEXT,
                    section_titre TEXT,
                    url TEXT,
                    citation TEXT,
                    extrait TEXT,
                    meta_json TEXT,
                    cree_le TEXT NOT NULL,
                    FOREIGN KEY(collection_id) REFERENCES collections(id)
                );
                """
            )
            # Collection par défaut
            row = conn.execute("SELECT id FROM collections WHERE nom = ?", ("Général",)).fetchone()
            if not row:
                cid = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO collections (id, nom, description, cree_le) VALUES (?, ?, ?, ?)",
                    (cid, "Général", "Favoris par défaut", _utc_now()),
                )

    def collection_defaut_id(self) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM collections ORDER BY cree_le ASC LIMIT 1"
            ).fetchone()
        return row["id"] if row else self.creer_collection("Général")

    def creer_collection(self, nom: str, description: str = "") -> str:
        cid = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO collections (id, nom, description, cree_le) VALUES (?, ?, ?, ?)",
                (cid, (nom or "Sans nom")[:80], description[:300], _utc_now()),
            )
        return cid

    def lister_collections(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT c.id, c.nom, c.description, c.cree_le, "
                "(SELECT COUNT(*) FROM favoris f WHERE f.collection_id = c.id) AS nb "
                "FROM collections c ORDER BY c.nom"
            ).fetchall()
        return [
            {
                "id": r["id"],
                "nom": r["nom"],
                "description": r["description"],
                "cree_le": r["cree_le"],
                "nb": int(r["nb"] or 0),
            }
            for r in rows
        ]

    def supprimer_collection(self, collection_id: str) -> bool:
        with self._connect() as conn:
            conn.execute("DELETE FROM favoris WHERE collection_id = ?", (collection_id,))
            cur = conn.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
            return cur.rowcount > 0

    def ajouter_favori(
        self,
        doc: Dict[str, Any],
        collection_id: Optional[str] = None,
    ) -> str:
        fid = str(uuid.uuid4())
        cid = collection_id or self.collection_defaut_id()
        meta = {
            k: doc.get(k)
            for k in ("score_confiance", "langage", "citation_courte", "url_blob", "url_commits")
            if doc.get(k) is not None
        }
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO favoris "
                "(id, collection_id, nom_complet, source_file, section_titre, url, "
                "citation, extrait, meta_json, cree_le) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    fid,
                    cid,
                    (doc.get("nom_complet") or "")[:200],
                    (doc.get("source_file") or "")[:300],
                    (doc.get("section_titre") or "")[:200],
                    (doc.get("url_blob") or doc.get("url") or "")[:500],
                    (doc.get("citation_courte") or "")[:200],
                    (doc.get("texte") or "")[:800],
                    json.dumps(meta, ensure_ascii=False),
                    _utc_now(),
                ),
            )
        return fid

    def lister_favoris(self, collection_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            if collection_id:
                rows = conn.execute(
                    "SELECT * FROM favoris WHERE collection_id = ? ORDER BY cree_le DESC",
                    (collection_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM favoris ORDER BY cree_le DESC LIMIT 200"
                ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            try:
                item["meta"] = json.loads(item.pop("meta_json") or "{}")
            except json.JSONDecodeError:
                item["meta"] = {}
            out.append(item)
        return out

    def supprimer_favori(self, favori_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM favoris WHERE id = ?", (favori_id,))
            return cur.rowcount > 0

    def est_deja_favori(self, nom_complet: str, source_file: str = "", section: str = "") -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM favoris WHERE nom_complet = ? AND source_file = ? "
                "AND section_titre = ? LIMIT 1",
                (nom_complet or "", source_file or "", section or ""),
            ).fetchone()
        return row is not None
