"""Comptes utilisateurs, usage et journal admin (SQLite partagé chat + Admin)."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

from app.quotas import quota_pour


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_pwd(password: str, salt: str = "") -> str:
    material = f"{salt}:{password}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


class UtilisateursSQLite:
    def __init__(self, chemin: Optional[Path] = None):
        self.chemin = Path(chemin or (config.DB_DIR / "utilisateurs.db"))
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._seed_admin()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.chemin), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE,
                    password_hash TEXT,
                    display_name TEXT NOT NULL DEFAULT '',
                    tier TEXT NOT NULL DEFAULT 'guest',
                    github_id TEXT,
                    github_login TEXT,
                    google_id TEXT,
                    apple_id TEXT,
                    suspended INTEGER NOT NULL DEFAULT 0,
                    cree_le TEXT NOT NULL,
                    derniere_connexion TEXT
                );
                CREATE TABLE IF NOT EXISTS usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    meta_json TEXT,
                    cree_le TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS admin_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id TEXT,
                    action TEXT NOT NULL,
                    details TEXT,
                    cree_le TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_usage_user_day
                    ON usage_events(user_id, cree_le);
                """
            )
            # Migration douce
            cols = {
                r["name"]
                for r in conn.execute("PRAGMA table_info(users)").fetchall()
            }
            if "google_id" not in cols:
                conn.execute("ALTER TABLE users ADD COLUMN google_id TEXT")
            if "apple_id" not in cols:
                conn.execute("ALTER TABLE users ADD COLUMN apple_id TEXT")
            if "github_id" not in cols:
                conn.execute("ALTER TABLE users ADD COLUMN github_id TEXT")
            if "github_login" not in cols:
                conn.execute("ALTER TABLE users ADD COLUMN github_login TEXT")

    def _seed_admin(self) -> None:
        """Crée un admin depuis ADMIN_EMAIL / ADMIN_PASSWORD si absent."""
        import os

        email = (os.getenv("ADMIN_EMAIL") or "admin@assistdoc.local").strip().lower()
        password = (os.getenv("ADMIN_PASSWORD") or os.getenv("STREAMLIT_PASSWORD") or "").strip()
        if not password:
            # Pas de secret → pas de seed auto (évite un admin faible en prod)
            return
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE tier = 'admin' LIMIT 1"
            ).fetchone()
            if row:
                return
            exist = conn.execute(
                "SELECT id FROM users WHERE email = ?", (email,)
            ).fetchone()
            if exist:
                conn.execute(
                    "UPDATE users SET tier = 'admin', password_hash = ? WHERE id = ?",
                    (_hash_pwd(password, exist["id"]), exist["id"]),
                )
                return
            uid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO users "
                "(id, email, password_hash, display_name, tier, cree_le, derniere_connexion) "
                "VALUES (?, ?, ?, ?, 'admin', ?, ?)",
                (uid, email, _hash_pwd(password, uid), "Administrateur", _utc_now(), _utc_now()),
            )

    def creer_invite(self, display_name: str = "Invité") -> Dict[str, Any]:
        uid = str(uuid.uuid4())
        now = _utc_now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO users "
                "(id, email, password_hash, display_name, tier, cree_le, derniere_connexion) "
                "VALUES (?, NULL, NULL, ?, 'guest', ?, ?)",
                (uid, display_name[:80], now, now),
            )
        return self.obtenir(uid)  # type: ignore

    def inscrire_email(
        self, email: str, password: str, display_name: str = ""
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        email = (email or "").strip().lower()
        if "@" not in email or len(password) < 6:
            return None, "Email invalide ou mot de passe trop court (min. 6)."
        uid = str(uuid.uuid4())
        now = _utc_now()
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO users "
                    "(id, email, password_hash, display_name, tier, cree_le, derniere_connexion) "
                    "VALUES (?, ?, ?, ?, 'email', ?, ?)",
                    (
                        uid,
                        email,
                        _hash_pwd(password, uid),
                        (display_name or email.split("@")[0])[:80],
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError:
            return None, "Cet email est déjà inscrit."
        return self.obtenir(uid), "Compte créé."

    def connecter_email(
        self, email: str, password: str
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        email = (email or "").strip().lower()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email,)
            ).fetchone()
        if not row:
            return None, "Email ou mot de passe incorrect."
        if row["suspended"]:
            return None, "Compte suspendu. Contactez l'administrateur."
        if not hmac.compare_digest(
            row["password_hash"] or "", _hash_pwd(password, row["id"])
        ):
            return None, "Email ou mot de passe incorrect."
        self._touch(row["id"])
        return self.obtenir(row["id"]), "Connecté."

    def upsert_github(
        self, github_id: str, github_login: str, email: Optional[str] = None
    ) -> Dict[str, Any]:
        now = _utc_now()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE github_id = ?", (str(github_id),)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE users SET github_login = ?, derniere_connexion = ?, "
                    "tier = CASE WHEN tier = 'admin' THEN 'admin' ELSE 'github' END, "
                    "email = COALESCE(email, ?) WHERE id = ?",
                    (github_login, now, (email or "").lower() or None, row["id"]),
                )
                return self.obtenir(row["id"])  # type: ignore
            uid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO users "
                "(id, email, password_hash, display_name, tier, github_id, github_login, "
                "cree_le, derniere_connexion) VALUES (?, ?, NULL, ?, 'github', ?, ?, ?, ?)",
                (
                    uid,
                    (email or "").lower() or None,
                    github_login[:80],
                    str(github_id),
                    github_login,
                    now,
                    now,
                ),
            )
        return self.obtenir(uid)  # type: ignore

    def upsert_google(
        self,
        google_id: str,
        email: Optional[str] = None,
        display_name: str = "",
    ) -> Dict[str, Any]:
        now = _utc_now()
        email_n = (email or "").strip().lower() or None
        name = (display_name or (email_n.split("@")[0] if email_n else "Google"))[:80]
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE google_id = ?", (str(google_id),)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE users SET derniere_connexion = ?, "
                    "display_name = COALESCE(NULLIF(?, ''), display_name), "
                    "tier = CASE WHEN tier = 'admin' THEN 'admin' ELSE 'google' END, "
                    "email = COALESCE(email, ?) WHERE id = ?",
                    (now, name, email_n, row["id"]),
                )
                return self.obtenir(row["id"])  # type: ignore

            # Lier un compte email existant au même email
            if email_n:
                by_email = conn.execute(
                    "SELECT * FROM users WHERE email = ?", (email_n,)
                ).fetchone()
                if by_email:
                    conn.execute(
                        "UPDATE users SET google_id = ?, derniere_connexion = ?, "
                        "tier = CASE WHEN tier = 'admin' THEN 'admin' "
                        "WHEN tier IN ('github', 'google') THEN tier ELSE 'google' END "
                        "WHERE id = ?",
                        (str(google_id), now, by_email["id"]),
                    )
                    return self.obtenir(by_email["id"])  # type: ignore

            uid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO users "
                "(id, email, password_hash, display_name, tier, google_id, "
                "cree_le, derniere_connexion) VALUES (?, ?, NULL, ?, 'google', ?, ?, ?)",
                (uid, email_n, name, str(google_id), now, now),
            )
        return self.obtenir(uid)  # type: ignore

    def upsert_apple(
        self,
        apple_id: str,
        email: Optional[str] = None,
        display_name: str = "",
    ) -> Dict[str, Any]:
        now = _utc_now()
        email_n = (email or "").strip().lower() or None
        name = (display_name or (email_n.split("@")[0] if email_n else "Apple"))[:80]
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE apple_id = ?", (str(apple_id),)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE users SET derniere_connexion = ?, "
                    "display_name = COALESCE(NULLIF(?, ''), display_name), "
                    "tier = CASE WHEN tier = 'admin' THEN 'admin' ELSE 'apple' END, "
                    "email = COALESCE(email, ?) WHERE id = ?",
                    (now, name, email_n, row["id"]),
                )
                return self.obtenir(row["id"])  # type: ignore

            if email_n:
                by_email = conn.execute(
                    "SELECT * FROM users WHERE email = ?", (email_n,)
                ).fetchone()
                if by_email:
                    conn.execute(
                        "UPDATE users SET apple_id = ?, derniere_connexion = ?, "
                        "tier = CASE WHEN tier = 'admin' THEN 'admin' "
                        "WHEN tier IN ('github', 'google', 'apple') THEN tier "
                        "ELSE 'apple' END WHERE id = ?",
                        (str(apple_id), now, by_email["id"]),
                    )
                    return self.obtenir(by_email["id"])  # type: ignore

            uid = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO users "
                "(id, email, password_hash, display_name, tier, apple_id, "
                "cree_le, derniere_connexion) VALUES (?, ?, NULL, ?, 'apple', ?, ?, ?)",
                (uid, email_n, name, str(apple_id), now, now),
            )
        return self.obtenir(uid)  # type: ignore

    def _touch(self, user_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET derniere_connexion = ? WHERE id = ?",
                (_utc_now(), user_id),
            )

    def obtenir(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return dict(row) if row else None

    def lister_users(self, limite: int = 200) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM users").fetchall()
        users = [dict(r) for r in rows]
        users.sort(
            key=lambda u: u.get("derniere_connexion") or u.get("cree_le") or "",
            reverse=True,
        )
        return users[:limite]

    def set_tier(self, user_id: str, tier: str, admin_id: str = "") -> bool:
        tier = (tier or "").lower()
        if tier not in {"guest", "email", "github", "google", "apple", "admin"}:
            return False
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE users SET tier = ? WHERE id = ?", (tier, user_id)
            )
            ok = cur.rowcount > 0
        if ok:
            self.audit(admin_id, "set_tier", f"{user_id} → {tier}")
        return ok

    def suspendre(self, user_id: str, suspended: bool, admin_id: str = "") -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE users SET suspended = ? WHERE id = ?",
                (1 if suspended else 0, user_id),
            )
            ok = cur.rowcount > 0
        if ok:
            self.audit(
                admin_id,
                "suspend" if suspended else "unsuspend",
                user_id,
            )
        return ok

    def enregistrer_usage(
        self, user_id: str, kind: str = "ask", meta: Optional[Dict] = None
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO usage_events (user_id, kind, meta_json, cree_le) "
                "VALUES (?, ?, ?, ?)",
                (
                    user_id,
                    kind,
                    json.dumps(meta or {}, ensure_ascii=False),
                    _utc_now(),
                ),
            )

    def compter_requetes_jour(self, user_id: str) -> int:
        debut = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM usage_events "
                "WHERE user_id = ? AND kind = 'ask' AND cree_le >= ?",
                (user_id, debut),
            ).fetchone()
        return int(row["n"] if row else 0)

    def verifier_quota(self, user: Dict[str, Any]) -> Tuple[bool, str]:
        if not user:
            return False, "Non connecté."
        if user.get("suspended"):
            return False, "Compte suspendu."
        tier = user.get("tier") or "guest"
        q = quota_pour(tier)
        if q.requetes_par_jour < 0:
            return True, "Illimité (admin)."
        n = self.compter_requetes_jour(user["id"])
        if n >= q.requetes_par_jour:
            return (
                False,
                f"Quota atteint ({n}/{q.requetes_par_jour} requêtes/jour pour {q.label}). "
                "Créez un compte email ou connectez GitHub pour plus d'usage.",
            )
        reste = q.requetes_par_jour - n
        return True, f"{reste} requête(s) restante(s) aujourd'hui ({q.label})."

    def stats_globales(self) -> Dict[str, Any]:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
            par_tier = {
                r["tier"]: r["n"]
                for r in conn.execute(
                    "SELECT tier, COUNT(*) AS n FROM users GROUP BY tier"
                ).fetchall()
            }
            asks_24h = conn.execute(
                "SELECT COUNT(*) AS n FROM usage_events WHERE kind = 'ask' "
                "AND cree_le >= ?",
                ((datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),),
            ).fetchone()["n"]
            actifs = conn.execute(
                "SELECT COUNT(DISTINCT user_id) AS n FROM usage_events "
                "WHERE cree_le >= ?",
                ((datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),),
            ).fetchone()["n"]
        return {
            "users_total": int(total),
            "par_tier": par_tier,
            "asks_24h": int(asks_24h),
            "users_actifs_24h": int(actifs),
        }

    def usage_recent(self, limite: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT e.*, u.email, u.display_name, u.tier FROM usage_events e "
                "LEFT JOIN users u ON u.id = e.user_id "
                "ORDER BY e.cree_le DESC LIMIT ?",
                (limite,),
            ).fetchall()
        return [dict(r) for r in rows]

    def audit(self, admin_id: str, action: str, details: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO admin_audit (admin_id, action, details, cree_le) "
                "VALUES (?, ?, ?, ?)",
                (admin_id or "", action, details[:1000], _utc_now()),
            )

    def lister_audit(self, limite: int = 40) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM admin_audit ORDER BY cree_le DESC LIMIT ?",
                (limite,),
            ).fetchall()
        return [dict(r) for r in rows]
