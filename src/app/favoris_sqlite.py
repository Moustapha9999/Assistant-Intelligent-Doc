"""Favoris et collections de documents (SQLite), isolés par propriétaire (`owner_id` = users.id).

Les lignes antérieures à la migration (owner_id NULL) sont en quarantaine : jamais renvoyées.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from app.sqlite_outils import colonnes, ecriture, lecture, sauvegarder_avant_migration
from securite.acces import AccesRefuse

VERSION_SCHEMA = 1
COLLECTION_DEFAUT = "Général"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _exiger_owner(owner_id: Optional[str]) -> str:
    owner = (owner_id or "").strip()
    if not owner:
        raise AccesRefuse("Identité requise")
    return owner


class FavorisSQLite:
    def __init__(self, chemin: Optional[Path] = None):
        self.chemin = Path(chemin or (config.DB_DIR / "favoris.db"))
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        self.sauvegarde_migration: Optional[Path] = None
        self._init_db()

    def _init_db(self) -> None:
        with lecture(self.chemin) as conn:
            existe = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='collections'"
            ).fetchone()
            a_migrer = bool(existe) and "owner_id" not in colonnes(conn, "collections")
        if a_migrer:
            self.sauvegarde_migration = sauvegarder_avant_migration(self.chemin, "isolation")

        with lecture(self.chemin) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS collections (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT,
                    nom TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    cree_le TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS favoris (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT,
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
            for table in ("collections", "favoris"):
                if "owner_id" not in colonnes(conn, table):
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN owner_id TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_collections_owner ON collections(owner_id)")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_favoris_owner ON favoris(owner_id, collection_id)"
            )
            conn.execute(f"PRAGMA user_version = {VERSION_SCHEMA}")
            conn.commit()

    # ── Collections ──────────────────────────────────────────────────────────

    def collection_defaut_id(self, *, owner_id: str) -> str:
        owner = _exiger_owner(owner_id)
        with lecture(self.chemin) as conn:
            row = conn.execute(
                "SELECT id FROM collections WHERE owner_id = ? ORDER BY cree_le ASC LIMIT 1",
                (owner,),
            ).fetchone()
        return row["id"] if row else self.creer_collection(
            COLLECTION_DEFAUT, "Favoris par défaut", owner_id=owner
        )

    def creer_collection(self, nom: str, description: str = "", *, owner_id: str) -> str:
        owner = _exiger_owner(owner_id)
        cid = str(uuid.uuid4())
        with ecriture(self.chemin) as conn:
            conn.execute(
                "INSERT INTO collections (id, owner_id, nom, description, cree_le) "
                "VALUES (?, ?, ?, ?, ?)",
                (cid, owner, (nom or "Sans nom")[:80], (description or "")[:300], _utc_now()),
            )
        return cid

    def lister_collections(self, *, owner_id: str) -> List[Dict[str, Any]]:
        owner = _exiger_owner(owner_id)
        self.collection_defaut_id(owner_id=owner)
        with lecture(self.chemin) as conn:
            rows = conn.execute(
                "SELECT c.id, c.nom, c.description, c.cree_le, "
                "(SELECT COUNT(*) FROM favoris f WHERE f.collection_id = c.id AND f.owner_id = ?) AS nb "
                "FROM collections c WHERE c.owner_id = ? ORDER BY c.nom",
                (owner, owner),
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

    def supprimer_collection(self, collection_id: str, *, owner_id: str) -> bool:
        owner = _exiger_owner(owner_id)
        with ecriture(self.chemin) as conn:
            conn.execute(
                "DELETE FROM favoris WHERE collection_id = ? AND owner_id = ?",
                (collection_id, owner),
            )
            cur = conn.execute(
                "DELETE FROM collections WHERE id = ? AND owner_id = ?", (collection_id, owner)
            )
            return cur.rowcount > 0

    # ── Favoris ──────────────────────────────────────────────────────────────

    def ajouter_favori(
        self,
        doc: Dict[str, Any],
        collection_id: Optional[str] = None,
        *,
        owner_id: str,
    ) -> str:
        owner = _exiger_owner(owner_id)
        cid = collection_id or self.collection_defaut_id(owner_id=owner)
        fid = str(uuid.uuid4())
        meta = {
            k: doc.get(k)
            for k in ("score_confiance", "langage", "citation_courte", "url_blob", "url_commits")
            if doc.get(k) is not None
        }
        with ecriture(self.chemin) as conn:
            proprietaire = conn.execute(
                "SELECT owner_id FROM collections WHERE id = ?", (cid,)
            ).fetchone()
            if proprietaire is None or proprietaire["owner_id"] != owner:
                raise AccesRefuse("Collection introuvable")
            conn.execute(
                "INSERT INTO favoris "
                "(id, owner_id, collection_id, nom_complet, source_file, section_titre, url, "
                "citation, extrait, meta_json, cree_le) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    fid,
                    owner,
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

    def lister_favoris(
        self, collection_id: Optional[str] = None, *, owner_id: str
    ) -> List[Dict[str, Any]]:
        owner = _exiger_owner(owner_id)
        with lecture(self.chemin) as conn:
            if collection_id:
                rows = conn.execute(
                    "SELECT * FROM favoris WHERE collection_id = ? AND owner_id = ? "
                    "ORDER BY cree_le DESC",
                    (collection_id, owner),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM favoris WHERE owner_id = ? ORDER BY cree_le DESC LIMIT 200",
                    (owner,),
                ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item.pop("owner_id", None)
            try:
                item["meta"] = json.loads(item.pop("meta_json") or "{}")
            except json.JSONDecodeError:
                item["meta"] = {}
            out.append(item)
        return out

    def supprimer_favori(self, favori_id: str, *, owner_id: str) -> bool:
        owner = _exiger_owner(owner_id)
        with ecriture(self.chemin) as conn:
            cur = conn.execute(
                "DELETE FROM favoris WHERE id = ? AND owner_id = ?", (favori_id, owner)
            )
            return cur.rowcount > 0

    def est_deja_favori(
        self, nom_complet: str, source_file: str = "", section: str = "", *, owner_id: str
    ) -> bool:
        owner = _exiger_owner(owner_id)
        with lecture(self.chemin) as conn:
            row = conn.execute(
                "SELECT id FROM favoris WHERE owner_id = ? AND nom_complet = ? "
                "AND source_file = ? AND section_titre = ? LIMIT 1",
                (owner, nom_complet or "", source_file or "", section or ""),
            ).fetchone()
        return row is not None
