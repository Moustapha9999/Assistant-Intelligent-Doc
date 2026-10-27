"""Comptes utilisateurs, sessions, usage et journal admin (SQLite partagé chat + Admin).

Identité :
- chaque utilisateur (invité compris) a un `users.id` UUID aléatoire, référence unique de ses données ;
- les comptes OAuth sont rattachés par l'identifiant du fournisseur (google_id, github_id, apple_id),
  jamais par l'adresse e-mail ;
- une session = jeton aléatoire (cookie navigateur) dont seule l'empreinte SHA-256 est stockée,
  avec expiration et révocation côté serveur.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

from app.quotas import quota_pour
from app.sqlite_outils import colonnes, connecter, ecriture, lecture

TIERS_COMPTE = {"email", "github", "google", "apple", "admin"}
DUREE_ETAT_OAUTH = timedelta(minutes=10)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def duree_session(tier: str) -> timedelta:
    """Invité : 30 jours ; compte : 14 jours (surchargeables par variables d'environnement)."""
    if (tier or "guest") in TIERS_COMPTE:
        return timedelta(days=float(os.getenv("SESSION_JOURS_COMPTE", "14")))
    return timedelta(days=float(os.getenv("SESSION_JOURS_INVITE", "30")))


def empreinte_jeton(jeton: str) -> str:
    return hashlib.sha256((jeton or "").encode("utf-8")).hexdigest()


def _hash_pwd_legacy(password: str, salt: str = "") -> str:
    material = f"{salt}:{password}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _hash_pwd(password: str, salt: str = "") -> str:
    """scrypt (hashlib) avec sel aléatoire ; format « scrypt$<sel hex>$<hash hex> »."""
    sel = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode("utf-8"), salt=sel, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${sel.hex()}${h.hex()}"


def _verifier_pwd(password: str, stocke: str, user_id: str) -> bool:
    stocke = stocke or ""
    if stocke.startswith("scrypt$"):
        try:
            _, sel_hex, h_hex = stocke.split("$", 2)
            h = hashlib.scrypt(
                password.encode("utf-8"), salt=bytes.fromhex(sel_hex), n=2**14, r=8, p=1, dklen=32
            )
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(h.hex(), h_hex)
    # Ancien format (SHA-256 salé par l'id) : vérifié puis re-haché à la connexion
    return bool(stocke) and hmac.compare_digest(stocke, _hash_pwd_legacy(password, user_id))


class UtilisateursSQLite:
    def __init__(self, chemin: Optional[Path] = None):
        self.chemin = Path(chemin or (config.DB_DIR / "utilisateurs.db"))
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._seed_admin()

    def _connect(self) -> sqlite3.Connection:
        return connecter(self.chemin)

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
                CREATE TABLE IF NOT EXISTS sessions (
                    jeton_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    cree_le TEXT NOT NULL,
                    expire_le TEXT NOT NULL,
                    revoque_le TEXT,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
                CREATE TABLE IF NOT EXISTS oauth_etats (
                    etat_hash TEXT PRIMARY KEY,
                    fournisseur TEXT NOT NULL,
                    session_hash TEXT,
                    expire_le TEXT NOT NULL
                );
                """
            )
            # Migration douce
            cols = colonnes(conn, "users")
            for col in ("google_id", "apple_id", "github_id", "github_login"):
                if col not in cols:
                    conn.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
            for col in ("google_id", "github_id", "apple_id"):
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_users_{col} ON users({col})"
                )

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
        if not _verifier_pwd(password, row["password_hash"] or "", row["id"]):
            return None, "Email ou mot de passe incorrect."
        if not (row["password_hash"] or "").startswith("scrypt$"):
            with ecriture(self.chemin) as conn:
                conn.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (_hash_pwd(password), row["id"]),
                )
        self._touch(row["id"])
        return self.obtenir(row["id"]), "Connecté."

    def _upsert_oauth(
        self,
        colonne: str,
        identifiant: str,
        tier: str,
        email: Optional[str],
        display_name: str,
        extra: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Compte rattaché par l'identifiant du fournisseur ; jamais fusionné par e-mail.

        L'e-mail n'est qu'informatif : il n'est enregistré que s'il n'appartient pas déjà
        à un autre compte (l'inscription par e-mail ne vérifie pas l'adresse).
        """
        if colonne not in {"google_id", "github_id", "apple_id"}:
            raise ValueError(colonne)
        identifiant = str(identifiant or "").strip()
        if not identifiant:
            raise ValueError("Identifiant fournisseur manquant")
        now = _utc_now()
        email_n = (email or "").strip().lower() or None
        extra = extra or {}
        with ecriture(self.chemin) as conn:
            if email_n and conn.execute(
                f"SELECT 1 FROM users WHERE email = ? AND COALESCE({colonne}, '') != ?",
                (email_n, identifiant),
            ).fetchone():
                email_n = None
            row = conn.execute(
                f"SELECT id FROM users WHERE {colonne} = ?", (identifiant,)
            ).fetchone()
            if row:
                sets = [
                    "derniere_connexion = ?",
                    "display_name = COALESCE(NULLIF(?, ''), display_name)",
                    "tier = CASE WHEN tier = 'admin' THEN 'admin' ELSE ? END",
                    "email = COALESCE(email, ?)",
                ] + [f"{k} = ?" for k in extra]
                conn.execute(
                    f"UPDATE users SET {', '.join(sets)} WHERE id = ?",
                    (now, display_name[:80], tier, email_n, *extra.values(), row["id"]),
                )
                uid = row["id"]
            else:
                uid = str(uuid.uuid4())
                cols = ["id", "email", "password_hash", "display_name", "tier", colonne,
                        "cree_le", "derniere_connexion", *extra]
                vals = [uid, email_n, None, display_name[:80] or tier.title(), tier, identifiant,
                        now, now, *extra.values()]
                conn.execute(
                    f"INSERT INTO users ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                    vals,
                )
        return self.obtenir(uid)  # type: ignore

    def upsert_github(
        self, github_id: str, github_login: str, email: Optional[str] = None
    ) -> Dict[str, Any]:
        return self._upsert_oauth(
            "github_id", github_id, "github", email, github_login or "",
            extra={"github_login": github_login or ""},
        )

    def upsert_google(
        self,
        google_id: str,
        email: Optional[str] = None,
        display_name: str = "",
    ) -> Dict[str, Any]:
        email_n = (email or "").strip().lower()
        nom = display_name or (email_n.split("@")[0] if email_n else "Google")
        return self._upsert_oauth("google_id", google_id, "google", email, nom)

    def upsert_apple(
        self,
        apple_id: str,
        email: Optional[str] = None,
        display_name: str = "",
    ) -> Dict[str, Any]:
        email_n = (email or "").strip().lower()
        nom = display_name or (email_n.split("@")[0] if email_n else "Apple")
        return self._upsert_oauth("apple_id", apple_id, "apple", email, nom)

    # ── Sessions (jeton du cookie navigateur, validé côté serveur) ───────────

    def creer_session(self, user_id: str) -> str:
        """Nouveau jeton aléatoire pour `user_id` ; seule son empreinte est stockée."""
        user = self.obtenir(user_id)
        if not user:
            raise ValueError("Utilisateur inconnu")
        jeton = secrets.token_urlsafe(32)
        now = _maintenant()
        with ecriture(self.chemin) as conn:
            conn.execute(
                "DELETE FROM sessions WHERE expire_le < ? OR revoque_le IS NOT NULL AND revoque_le < ?",
                (now.isoformat(), (now - timedelta(days=7)).isoformat()),
            )
            conn.execute(
                "INSERT INTO sessions (jeton_hash, user_id, cree_le, expire_le) VALUES (?, ?, ?, ?)",
                (
                    empreinte_jeton(jeton),
                    user_id,
                    now.isoformat(),
                    (now + duree_session(user.get("tier") or "guest")).isoformat(),
                ),
            )
        return jeton

    def valider_session(self, jeton: Optional[str]) -> Optional[Dict[str, Any]]:
        """Utilisateur de la session si le jeton est connu, non révoqué, non expiré et
        le compte non suspendu ; sinon None. Prolonge l'expiration (session glissante)."""
        if not jeton or len(jeton) > 256:
            return None
        h = empreinte_jeton(jeton)
        now = _maintenant()
        with lecture(self.chemin) as conn:
            row = conn.execute(
                "SELECT s.user_id, s.expire_le, s.revoque_le, u.tier, u.suspended "
                "FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.jeton_hash = ?",
                (h,),
            ).fetchone()
        if row is None or row["revoque_le"] or row["suspended"]:
            return None
        try:
            expire = datetime.fromisoformat(row["expire_le"])
        except ValueError:
            return None
        if expire <= now:
            return None
        duree = duree_session(row["tier"])
        if expire - now < duree / 2:
            with ecriture(self.chemin) as conn:
                conn.execute(
                    "UPDATE sessions SET expire_le = ? WHERE jeton_hash = ? AND revoque_le IS NULL",
                    ((now + duree).isoformat(), h),
                )
        return self.obtenir(row["user_id"])

    def revoquer_session(self, jeton: Optional[str]) -> None:
        if not jeton:
            return
        with ecriture(self.chemin) as conn:
            conn.execute(
                "UPDATE sessions SET revoque_le = ? WHERE jeton_hash = ? AND revoque_le IS NULL",
                (_utc_now(), empreinte_jeton(jeton)),
            )

    def revoquer_sessions_utilisateur(self, user_id: str) -> int:
        with ecriture(self.chemin) as conn:
            cur = conn.execute(
                "UPDATE sessions SET revoque_le = ? WHERE user_id = ? AND revoque_le IS NULL",
                (_utc_now(), user_id),
            )
            return cur.rowcount

    # ── États OAuth (anti-CSRF, usage unique, liés à la session) ─────────────

    def enregistrer_etat_oauth(self, etat: str, fournisseur: str, jeton_session: Optional[str]) -> None:
        now = _maintenant()
        with ecriture(self.chemin) as conn:
            conn.execute("DELETE FROM oauth_etats WHERE expire_le < ?", (now.isoformat(),))
            conn.execute(
                "INSERT OR REPLACE INTO oauth_etats (etat_hash, fournisseur, session_hash, expire_le) "
                "VALUES (?, ?, ?, ?)",
                (
                    empreinte_jeton(etat),
                    fournisseur,
                    empreinte_jeton(jeton_session) if jeton_session else None,
                    (now + DUREE_ETAT_OAUTH).isoformat(),
                ),
            )

    def consommer_etat_oauth(
        self,
        etat: str,
        fournisseur: str,
        jeton_session: Optional[str],
        exiger_meme_session: bool = True,
    ) -> bool:
        """True si l'état a été émis par cette application pour ce fournisseur, n'est pas
        expiré, n'a jamais servi et (par défaut) appartient à la même session navigateur."""
        if not etat:
            return False
        with ecriture(self.chemin) as conn:
            row = conn.execute(
                "SELECT fournisseur, session_hash, expire_le FROM oauth_etats WHERE etat_hash = ?",
                (empreinte_jeton(etat),),
            ).fetchone()
            conn.execute("DELETE FROM oauth_etats WHERE etat_hash = ?", (empreinte_jeton(etat),))
        if row is None or row["fournisseur"] != fournisseur:
            return False
        if datetime.fromisoformat(row["expire_le"]) <= _maintenant():
            return False
        if exiger_meme_session:
            attendu = row["session_hash"]
            if not attendu or not jeton_session:
                return False
            return hmac.compare_digest(attendu, empreinte_jeton(jeton_session))
        return True

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
