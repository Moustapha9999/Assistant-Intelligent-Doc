"""
Persistance des conversations et du feedback utilisateur (SQLite).

Isolation : chaque conversation a un propriétaire (`owner_id` = users.id, invité compris).
Toutes les opérations prennent `owner_id` en argument nommé obligatoire, fourni par
l'identité résolue côté serveur, et ne lisent ni ne modifient jamais une conversation
d'un autre propriétaire. Les conversations antérieures à la migration (owner_id NULL)
sont en quarantaine : aucune requête utilisateur ne les renvoie.
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
from app.sqlite_outils import colonnes, connecter, ecriture, lecture, sauvegarder_avant_migration
from securite.acces import AccesRefuse

VERSION_SCHEMA = 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _exiger_owner(owner_id: Optional[str]) -> str:
    owner = (owner_id or "").strip()
    if not owner:
        raise AccesRefuse("Identité requise")
    return owner


class HistoriqueSQLite:
    def __init__(self, chemin: Optional[Path] = None):
        self.chemin = Path(chemin or config.HISTORIQUE_DB)
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        self.sauvegarde_migration: Optional[Path] = None
        self._init_db()

    def _connect(self):
        return connecter(self.chemin)

    def _init_db(self) -> None:
        with lecture(self.chemin) as conn:
            existe = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='conversations'"
            ).fetchone()
            a_migrer = bool(existe) and "owner_id" not in colonnes(conn, "conversations")
        if a_migrer:
            self.sauvegarde_migration = sauvegarder_avant_migration(self.chemin, "isolation")

        with lecture(self.chemin) as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    owner_id TEXT,
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
            conv_cols = colonnes(conn, "conversations")
            if "figee" not in conv_cols:
                conn.execute("ALTER TABLE conversations ADD COLUMN figee INTEGER NOT NULL DEFAULT 0")
            if "owner_id" not in conv_cols:
                # Anciennes conversations : propriétaire inconnu → NULL (quarantaine)
                conn.execute("ALTER TABLE conversations ADD COLUMN owner_id TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversations_owner "
                "ON conversations(owner_id, figee, maj_le)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id)")

            fb_cols = colonnes(conn, "feedback")
            for col, decl in (
                ("message_idx", "INTEGER DEFAULT 0"),
                ("commentaire", "TEXT DEFAULT ''"),
                ("cree_le", "TEXT DEFAULT ''"),
                ("user_label", "TEXT DEFAULT ''"),
                ("question", "TEXT DEFAULT ''"),
                ("extrait_reponse", "TEXT DEFAULT ''"),
                ("mode", "TEXT DEFAULT ''"),
                ("owner_id", "TEXT"),
            ):
                if col not in fb_cols:
                    conn.execute(f"ALTER TABLE feedback ADD COLUMN {col} {decl}")
            conn.execute(f"PRAGMA user_version = {VERSION_SCHEMA}")
            conn.commit()

    # ── Contrôle de propriété ────────────────────────────────────────────────

    @staticmethod
    def _proprietaire(conn, conversation_id: str) -> Optional[str]:
        row = conn.execute(
            "SELECT owner_id FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if row is None:
            return None
        return row["owner_id"] or ""

    def _verifier(self, conn, conversation_id: str, owner: str) -> None:
        if self._proprietaire(conn, conversation_id) != owner:
            raise AccesRefuse("Conversation introuvable")

    # ── Conversations ────────────────────────────────────────────────────────

    def creer_conversation(
        self, titre: str = "Nouvelle discussion", figee: bool = False, *, owner_id: str
    ) -> str:
        owner = _exiger_owner(owner_id)
        cid = str(uuid.uuid4())
        now = _utc_now()
        with ecriture(self.chemin) as conn:
            conn.execute(
                "INSERT INTO conversations (id, owner_id, titre, cree_le, maj_le, figee) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (cid, owner, titre, now, now, 1 if figee else 0),
            )
        return cid

    def lister_conversations(self, limite: int = 50, *, owner_id: str) -> List[Dict[str, Any]]:
        owner = _exiger_owner(owner_id)
        with lecture(self.chemin) as conn:
            rows = conn.execute(
                "SELECT id, titre, cree_le, maj_le, figee FROM conversations "
                "WHERE owner_id = ? ORDER BY figee DESC, maj_le DESC LIMIT ?",
                (owner, limite),
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

    def obtenir_conversation(self, conversation_id: str, *, owner_id: str) -> Optional[Dict[str, Any]]:
        owner = _exiger_owner(owner_id)
        with lecture(self.chemin) as conn:
            row = conn.execute(
                "SELECT id, titre, cree_le, maj_le, figee FROM conversations "
                "WHERE id = ? AND owner_id = ?",
                (conversation_id, owner),
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

    def est_figee(self, conversation_id: str, *, owner_id: str) -> bool:
        meta = self.obtenir_conversation(conversation_id, owner_id=owner_id)
        return bool(meta and meta.get("figee"))

    def charger_messages(self, conversation_id: str, *, owner_id: str) -> List[Dict[str, Any]]:
        """Messages d'une conversation du propriétaire ; AccesRefuse sinon (rien n'est lu)."""
        owner = _exiger_owner(owner_id)
        with lecture(self.chemin) as conn:
            self._verifier(conn, conversation_id, owner)
            rows = conn.execute(
                "SELECT m.role, m.content, m.meta_json FROM messages m "
                "JOIN conversations c ON c.id = m.conversation_id "
                "WHERE m.conversation_id = ? AND c.owner_id = ? ORDER BY m.id ASC",
                (conversation_id, owner),
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
        *,
        owner_id: str,
    ) -> None:
        """Crée ou remplace la conversation du propriétaire, en une seule transaction.

        Une conversation existante d'un autre propriétaire (ou en quarantaine) n'est jamais
        modifiée : AccesRefuse.
        """
        owner = _exiger_owner(owner_id)
        now = _utc_now()
        with ecriture(self.chemin) as conn:
            existante = conn.execute(
                "SELECT owner_id, titre, figee FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if existante is not None and existante["owner_id"] != owner:
                raise AccesRefuse("Conversation introuvable")
            figee_val = (
                (1 if figee else 0)
                if figee is not None
                else (int(existante["figee"]) if existante else 0)
            )
            # Discussion figée : on garde le titre déjà en base
            if existante is not None and existante["figee"]:
                titre = existante["titre"]

            if existante is None:
                conn.execute(
                    "INSERT INTO conversations (id, owner_id, titre, cree_le, maj_le, figee) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (conversation_id, owner, titre, now, now, figee_val),
                )
            else:
                conn.execute(
                    "UPDATE conversations SET titre = ?, maj_le = ?, figee = ? "
                    "WHERE id = ? AND owner_id = ?",
                    (titre, now, figee_val, conversation_id, owner),
                )
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
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

    def renommer_conversation(self, conversation_id: str, titre: str, *, owner_id: str) -> bool:
        owner = _exiger_owner(owner_id)
        titre = (titre or "").strip()
        if not titre:
            return False
        with ecriture(self.chemin) as conn:
            cur = conn.execute(
                "UPDATE conversations SET titre = ?, maj_le = ? "
                "WHERE id = ? AND owner_id = ? AND figee = 0",
                (titre[:120], _utc_now(), conversation_id, owner),
            )
            return cur.rowcount > 0

    def figer_conversation(self, conversation_id: str, figee: bool = True, *, owner_id: str) -> bool:
        owner = _exiger_owner(owner_id)
        with ecriture(self.chemin) as conn:
            cur = conn.execute(
                "UPDATE conversations SET figee = ?, maj_le = ? WHERE id = ? AND owner_id = ?",
                (1 if figee else 0, _utc_now(), conversation_id, owner),
            )
            return cur.rowcount > 0

    def supprimer_conversation(
        self, conversation_id: str, forcer: bool = False, *, owner_id: str
    ) -> bool:
        owner = _exiger_owner(owner_id)
        with ecriture(self.chemin) as conn:
            row = conn.execute(
                "SELECT figee FROM conversations WHERE id = ? AND owner_id = ?",
                (conversation_id, owner),
            ).fetchone()
            if row is None or (row["figee"] and not forcer):
                return False
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            conn.execute("DELETE FROM feedback WHERE conversation_id = ?", (conversation_id,))
            cur = conn.execute(
                "DELETE FROM conversations WHERE id = ? AND owner_id = ?",
                (conversation_id, owner),
            )
            return cur.rowcount > 0

    # ── Feedback ─────────────────────────────────────────────────────────────

    def enregistrer_feedback(
        self,
        conversation_id: Optional[str],
        message_idx: int,
        note: int,
        commentaire: str = "",
        *,
        owner_id: str,
        user_label: str = "",
        question: str = "",
        extrait_reponse: str = "",
        mode: str = "",
    ) -> None:
        """Enregistre un 👍/👎 ou signalement (snapshot pour l'Admin).

        Si `conversation_id` est fourni, la conversation doit appartenir à `owner_id`.
        """
        owner = _exiger_owner(owner_id)
        with ecriture(self.chemin) as conn:
            if conversation_id:
                self._verifier(conn, conversation_id, owner)
            conn.execute(
                "INSERT INTO feedback (conversation_id, message_idx, note, commentaire, cree_le, "
                "user_label, question, extrait_reponse, mode, owner_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    conversation_id or None,
                    message_idx,
                    int(note),
                    commentaire or "",
                    _utc_now(),
                    (user_label or "")[:120],
                    (question or "")[:2000],
                    (extrait_reponse or "")[:4000],
                    (mode or "")[:80],
                    owner,
                ),
            )

    def lister_feedback(self, limite: int = 100) -> List[Dict[str, Any]]:
        """Administration uniquement : feedbacks 👍/👎 / signalements avec extrait."""
        with lecture(self.chemin) as conn:
            rows = conn.execute(
                "SELECT f.id, f.conversation_id, f.note, f.message_idx, f.commentaire, f.cree_le, "
                "f.user_label, f.question, f.extrait_reponse, f.mode, c.titre "
                "FROM feedback f LEFT JOIN conversations c ON c.id = f.conversation_id "
                "ORDER BY f.cree_le DESC LIMIT ?",
                (limite,),
            ).fetchall()

            out = []
            for r in rows:
                d = dict(r)
                for cle in ("commentaire", "cree_le", "user_label", "question", "mode"):
                    d[cle] = d.get(cle) or ""
                d["message_idx"] = d.get("message_idx") or 0
                note = int(d.get("note") or 0)
                d["label"] = "positif" if note > 0 else "negatif" if note < 0 else "neutre"

                contenu = (d.get("extrait_reponse") or "").strip()
                if not contenu and d.get("conversation_id"):
                    idx = int(d["message_idx"])
                    msgs = conn.execute(
                        "SELECT content FROM messages WHERE conversation_id = ? ORDER BY id ASC",
                        (d["conversation_id"],),
                    ).fetchall()
                    if 0 <= idx < len(msgs):
                        contenu = msgs[idx]["content"] or ""
                    elif msgs:
                        contenu = next((m["content"] for m in reversed(msgs) if m["content"]), "")
                d["extrait_reponse"] = contenu
                d["extrait_court"] = (contenu[:220] + "…") if len(contenu) > 220 else contenu
                out.append(d)
        return out

    def stats_feedback(self) -> Dict[str, int]:
        """Administration uniquement."""
        with lecture(self.chemin) as conn:
            total = conn.execute("SELECT COUNT(*) AS n FROM feedback").fetchone()["n"]
            pos = conn.execute("SELECT COUNT(*) AS n FROM feedback WHERE note > 0").fetchone()["n"]
            neg = conn.execute("SELECT COUNT(*) AS n FROM feedback WHERE note < 0").fetchone()["n"]
            signal = conn.execute(
                "SELECT COUNT(*) AS n FROM feedback WHERE commentaire LIKE '[signalement]%'"
            ).fetchone()["n"]
        return {
            "total": int(total),
            "positifs": int(pos),
            "negatifs": int(neg),
            "signalements": int(signal),
        }

    def compter_quarantaine(self) -> int:
        """Conversations antérieures à l'isolation, sans propriétaire connu (jamais exposées)."""
        with lecture(self.chemin) as conn:
            return int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM conversations WHERE owner_id IS NULL OR owner_id = ''"
                ).fetchone()["n"]
            )


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
        from app.gestionnaire_fichiers import fichiers_pour_persistance

        out["fichiers"] = [
            fichiers_pour_persistance(f) for f in out["fichiers"] or [] if isinstance(f, dict)
        ]
    return out


def _jsonable(v: Any) -> bool:
    try:
        json.dumps(v, default=str)
        return True
    except (TypeError, ValueError):
        return False
