"""
Persistance des conversations et du feedback utilisateur (SQLite).
"""

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


class HistoriqueSQLite:
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
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    titre TEXT NOT NULL DEFAULT 'Nouvelle discussion',
                    cree_le TEXT NOT NULL,
                    maj_le TEXT NOT NULL,
                    figee INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    meta_json TEXT,
                    cree_le TEXT NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id)
                );
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT,
                    message_idx INTEGER,
                    note INTEGER NOT NULL,
                    commentaire TEXT,
                    cree_le TEXT NOT NULL
                );
                """
            )
            # Migrations douces (anciennes bases)
            conv_cols = {
                r["name"]
                for r in conn.execute("PRAGMA table_info(conversations)").fetchall()
            }
            if "figee" not in conv_cols:
                conn.execute(
                    "ALTER TABLE conversations ADD COLUMN figee INTEGER NOT NULL DEFAULT 0"
                )

            fb_cols = {
                r["name"]
                for r in conn.execute("PRAGMA table_info(feedback)").fetchall()
            }
            if fb_cols:
                if "message_idx" not in fb_cols:
                    conn.execute(
                        "ALTER TABLE feedback ADD COLUMN message_idx INTEGER DEFAULT 0"
                    )
                if "commentaire" not in fb_cols:
                    conn.execute(
                        "ALTER TABLE feedback ADD COLUMN commentaire TEXT DEFAULT ''"
                    )
                if "cree_le" not in fb_cols:
                    conn.execute(
                        "ALTER TABLE feedback ADD COLUMN cree_le TEXT DEFAULT ''"
                    )
                for col, decl in (
                    ("user_label", "TEXT DEFAULT ''"),
                    ("question", "TEXT DEFAULT ''"),
                    ("extrait_reponse", "TEXT DEFAULT ''"),
                    ("mode", "TEXT DEFAULT ''"),
                ):
                    if col not in fb_cols:
                        conn.execute(f"ALTER TABLE feedback ADD COLUMN {col} {decl}")

    def creer_conversation(self, titre: str = "Nouvelle discussion", figee: bool = False) -> str:
        cid = str(uuid.uuid4())
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO conversations (id, titre, cree_le, maj_le, figee) VALUES (?, ?, ?, ?, ?)",
                (cid, titre, now, now, 1 if figee else 0),
            )
        return cid

    def lister_conversations(self, limite: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, titre, cree_le, maj_le, figee FROM conversations "
                "ORDER BY figee DESC, maj_le DESC LIMIT ?",
                (limite,),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "titre": r["titre"],
                "cree_le": r["cree_le"],
                "maj_le": r["maj_le"],
                "figee": bool(r["figee"]),
            }
            for r in rows
        ]

    def obtenir_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, titre, cree_le, maj_le, figee FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "titre": row["titre"],
            "cree_le": row["cree_le"],
            "maj_le": row["maj_le"],
            "figee": bool(row["figee"]),
        }

    def est_figee(self, conversation_id: str) -> bool:
        meta = self.obtenir_conversation(conversation_id)
        return bool(meta and meta.get("figee"))

    def charger_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT role, content, meta_json FROM messages "
                "WHERE conversation_id = ? ORDER BY id ASC",
                (conversation_id,),
            ).fetchall()
        messages = []
        for r in rows:
            msg: Dict[str, Any] = {"role": r["role"], "content": r["content"]}
            if r["meta_json"]:
                try:
                    meta = json.loads(r["meta_json"])
                    if isinstance(meta, dict):
                        msg.update(meta)
                except json.JSONDecodeError:
                    pass
            messages.append(msg)
        return messages

    def sauvegarder_conversation(
        self,
        conversation_id: str,
        titre: str,
        messages: List[Dict[str, Any]],
        figee: Optional[bool] = None,
    ) -> None:
        now = _utc_now()
        with self._connect() as conn:
            existante = conn.execute(
                "SELECT figee FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            figee_val = (
                (1 if figee else 0)
                if figee is not None
                else (int(existante["figee"]) if existante else 0)
            )
            # Discussion figée : on garde le titre déjà en base
            if existante and existante["figee"]:
                row_titre = conn.execute(
                    "SELECT titre FROM conversations WHERE id = ?",
                    (conversation_id,),
                ).fetchone()
                titre = row_titre["titre"] if row_titre else titre

            conn.execute(
                "INSERT INTO conversations (id, titre, cree_le, maj_le, figee) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET "
                "titre=excluded.titre, maj_le=excluded.maj_le, figee=excluded.figee",
                (conversation_id, titre, now, now, figee_val),
            )
            conn.execute(
                "DELETE FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            )
            for msg in messages:
                meta = {
                    k: v
                    for k, v in msg.items()
                    if k not in ("role", "content") and _jsonable(v)
                }
                meta = _alleger_meta_messages(meta)
                conn.execute(
                    "INSERT INTO messages (conversation_id, role, content, meta_json, cree_le) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        conversation_id,
                        msg.get("role", "user"),
                        msg.get("content", ""),
                        json.dumps(meta, ensure_ascii=False, default=str),
                        now,
                    ),
                )

    def renommer_conversation(self, conversation_id: str, titre: str) -> bool:
        titre = (titre or "").strip()
        if not titre:
            return False
        if self.est_figee(conversation_id):
            return False
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE conversations SET titre = ?, maj_le = ? WHERE id = ?",
                (titre[:120], _utc_now(), conversation_id),
            )
            return cur.rowcount > 0

    def figer_conversation(self, conversation_id: str, figee: bool = True) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE conversations SET figee = ?, maj_le = ? WHERE id = ?",
                (1 if figee else 0, _utc_now(), conversation_id),
            )
            return cur.rowcount > 0

    def supprimer_conversation(self, conversation_id: str, forcer: bool = False) -> bool:
        if not forcer and self.est_figee(conversation_id):
            return False
        with self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            conn.execute("DELETE FROM feedback WHERE conversation_id = ?", (conversation_id,))
            cur = conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            return cur.rowcount > 0

    def enregistrer_feedback(
        self,
        conversation_id: str,
        message_idx: int,
        note: int,
        commentaire: str = "",
        *,
        user_label: str = "",
        question: str = "",
        extrait_reponse: str = "",
        mode: str = "",
    ) -> None:
        """Enregistre un 👍/👎 ou signalement (snapshot pour l'Admin)."""
        with self._connect() as conn:
            fb_cols = {
                r["name"]
                for r in conn.execute("PRAGMA table_info(feedback)").fetchall()
            }
            cols = ["conversation_id", "message_idx", "note", "commentaire", "cree_le"]
            vals: List[Any] = [
                conversation_id,
                message_idx,
                int(note),
                commentaire or "",
                _utc_now(),
            ]
            for col, val in (
                ("user_label", (user_label or "")[:120]),
                ("question", (question or "")[:2000]),
                ("extrait_reponse", (extrait_reponse or "")[:4000]),
                ("mode", (mode or "")[:80]),
            ):
                if col in fb_cols:
                    cols.append(col)
                    vals.append(val)
            placeholders = ", ".join("?" for _ in cols)
            conn.execute(
                f"INSERT INTO feedback ({', '.join(cols)}) VALUES ({placeholders})",
                tuple(vals),
            )

    def lister_feedback(self, limite: int = 100) -> List[Dict[str, Any]]:
        """Feedbacks 👍/👎 / signalements avec extrait (snapshot ou messages)."""
        with self._connect() as conn:
            # Schema résilient (anciennes bases)
            fb_cols = {
                r["name"]
                for r in conn.execute("PRAGMA table_info(feedback)").fetchall()
            }
            select_cols = ["f.id", "f.conversation_id", "f.note"]
            for col in (
                "message_idx",
                "commentaire",
                "cree_le",
                "user_label",
                "question",
                "extrait_reponse",
                "mode",
            ):
                if col in fb_cols:
                    select_cols.append(f"f.{col}")
            sql = (
                f"SELECT {', '.join(select_cols)}, c.titre "
                "FROM feedback f "
                "LEFT JOIN conversations c ON c.id = f.conversation_id "
            )
            if "cree_le" in fb_cols:
                sql += "ORDER BY f.cree_le DESC "
            else:
                sql += "ORDER BY f.id DESC "
            sql += "LIMIT ?"
            rows = conn.execute(sql, (limite,)).fetchall()

            out = []
            for r in rows:
                d = dict(r)
                if "message_idx" not in d:
                    d["message_idx"] = 0
                if "commentaire" not in d:
                    d["commentaire"] = ""
                if "cree_le" not in d:
                    d["cree_le"] = ""
                if "user_label" not in d:
                    d["user_label"] = ""
                if "question" not in d:
                    d["question"] = ""
                if "mode" not in d:
                    d["mode"] = ""
                note = int(d.get("note") or 0)
                if note > 0:
                    d["label"] = "positif"
                elif note < 0:
                    d["label"] = "negatif"
                else:
                    d["label"] = "neutre"

                contenu = (d.get("extrait_reponse") or "").strip()
                if not contenu:
                    cid = d.get("conversation_id")
                    idx = int(d.get("message_idx") or 0)
                    if cid:
                        msgs = conn.execute(
                            "SELECT content FROM messages "
                            "WHERE conversation_id = ? ORDER BY id ASC",
                            (cid,),
                        ).fetchall()
                        if 0 <= idx < len(msgs):
                            contenu = msgs[idx]["content"] or ""
                        elif msgs:
                            for m in reversed(msgs):
                                if m["content"]:
                                    contenu = m["content"]
                                    break
                d["extrait_reponse"] = contenu
                d["extrait_court"] = (
                    (contenu[:220] + "…") if len(contenu) > 220 else contenu
                )
                out.append(d)
        return out

    def stats_feedback(self) -> Dict[str, int]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS n FROM feedback").fetchone()["n"]
            pos = conn.execute(
                "SELECT COUNT(*) AS n FROM feedback WHERE note > 0"
            ).fetchone()["n"]
            neg = conn.execute(
                "SELECT COUNT(*) AS n FROM feedback WHERE note < 0"
            ).fetchone()["n"]
            signal = conn.execute(
                "SELECT COUNT(*) AS n FROM feedback WHERE commentaire LIKE '[signalement]%'"
            ).fetchone()["n"]
        return {
            "total": int(total),
            "positifs": int(pos),
            "negatifs": int(neg),
            "signalements": int(signal),
        }


def _alleger_meta_messages(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Retire base64 / bytes volumineux avant persistance SQLite."""
    out = dict(meta)
    if out.get("images"):
        out["images"] = [
            {
                "caption": (i or {}).get("caption"),
                "provider": (i or {}).get("provider"),
                "media_type": (i or {}).get("media_type"),
            }
            for i in (out["images"] or [])
            if isinstance(i, dict)
        ]
    if out.get("fichiers"):
        legers = []
        for f in out["fichiers"] or []:
            if not isinstance(f, dict):
                continue
            f2 = {
                k: v
                for k, v in f.items()
                if k not in ("image_b64", "audio_bytes", "bytes")
            }
            if f.get("type") == "image":
                f2["image_omise"] = True
            # Tronquer contenu vision très long en base
            contenu = f2.get("contenu")
            if isinstance(contenu, str) and len(contenu) > 4000:
                f2["contenu"] = contenu[:4000] + "…"
            legers.append(f2)
        out["fichiers"] = legers
    return out


def _jsonable(v: Any) -> bool:
    try:
        json.dumps(v, default=str)
        return True
    except (TypeError, ValueError):
        return False
