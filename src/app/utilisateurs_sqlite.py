"""Comptes utilisateurs, sessions, usage et journal d'audit (SQLite partagé chat + Admin).

Identité :
- chaque utilisateur (invité compris) a un `users.id` UUID aléatoire, référence unique de ses données ;
- les comptes OAuth sont rattachés par l'identifiant du fournisseur (google_id, github_id, apple_id),
  jamais par l'adresse e-mail ;
- une session = jeton aléatoire (cookie navigateur) dont seule l'empreinte SHA-256 est stockée,
  avec expiration et révocation côté serveur.

Sécurité :
- connexion par e-mail limitée (échecs comptés par empreinte d'e-mail et d'adresse IP) ;
- second facteur TOTP facultatif, avec protection contre le rejeu ;
- changements de rôle et suspensions vérifiés ici (l'acteur doit être un administrateur actif),
  pas seulement par l'interface ;
- journal d'audit en ajout seul (déclencheurs SQLite) et chaîné par empreintes SHA-256.
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
from typing import Any, Dict, Iterable, List, Optional, Tuple

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

from app.quotas import quota_pour
from app.sqlite_outils import colonnes, connecter, ecriture, lecture, sauvegarder_avant_migration
from securite import mots_de_passe, politique, totp
from securite.evenements import (
    CATEGORIE_ADMIN,
    CATEGORIE_SECURITE,
    cle_tentative,
    gravite_valide,
    masquer_email,
)

TIERS_COMPTE = {"email", "github", "google", "apple", "admin"}
TIERS = ("guest", "email", "github", "google", "apple", "admin")
DUREE_ETAT_OAUTH = timedelta(minutes=10)
MOT_DE_PASSE_MIN = 8

MSG_ECHEC_CONNEXION = "Email ou mot de passe incorrect."
MSG_BLOCAGE = "Trop de tentatives de connexion. Réessayez dans quelques minutes."
MSG_MFA_INVALIDE = "Code de vérification invalide ou déjà utilisé."
MSG_MFA_BLOCAGE = "Trop de codes invalides. Réessayez dans quelques minutes."
MSG_INVITES_SATURE = "L'accès invité est momentanément saturé. Connectez-vous pour continuer."
MSG_QUOTA_INVITE = (
    "Vous avez atteint votre limite de {n} requêtes gratuites pour aujourd'hui. "
    "Connectez-vous pour continuer à utiliser l'assistant."
)
MSG_SESSION_INVALIDE = "Session expirée ou invalide. Reconnectez-vous."
MSG_MDP_ACTUEL = "Mot de passe actuel incorrect."
MSG_MDP_BLOCAGE = "Trop de tentatives. Réessayez dans quelques minutes."
MSG_MDP_SANS_MOT_DE_PASSE = "Ce compte se connecte via un fournisseur externe : aucun mot de passe à modifier."

# Colonnes jamais renvoyées hors de ce module
_COLONNES_SECRETES = ("password_hash", "totp_secret")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def duree_session(tier: str) -> timedelta:
    """Invité : 30 jours ; compte : 14 jours (réglables dans Admin → Sécurité)."""
    if (tier or "guest") in TIERS_COMPTE:
        return timedelta(days=politique.valeur("SESSION_JOURS_COMPTE"))
    return timedelta(days=politique.valeur("SESSION_JOURS_INVITE"))


def empreinte_jeton(jeton: str) -> str:
    return hashlib.sha256((jeton or "").encode("utf-8")).hexdigest()


def empreinte_audit(precedente: str, acteur: str, action: str, details: str, cree_le: str,
                    categorie: str, gravite: str) -> str:
    contenu = json.dumps(
        [precedente or "", acteur or "", action, details or "", cree_le, categorie, gravite],
        ensure_ascii=False,
    )
    return hashlib.sha256(contenu.encode("utf-8")).hexdigest()


def _hash_pwd_legacy(password: str, salt: str = "") -> str:
    material = f"{salt}:{password}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _hash_pwd(password: str, salt: str = "") -> str:
    """scrypt (hashlib) avec sel aléatoire ; format « scrypt$<sel hex>$<hash hex> »."""
    sel = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode("utf-8"), salt=sel, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${sel.hex()}${h.hex()}"


_LEURRE: List[str] = []


def _hash_leurre() -> str:
    """Hachage factice : un e-mail inconnu coûte le même calcul qu'un mot de passe faux."""
    if not _LEURRE:
        _LEURRE.append(_hash_pwd(secrets.token_hex(16)))
    return _LEURRE[0]


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


def _public(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    d = dict(row)
    for col in _COLONNES_SECRETES:
        d.pop(col, None)
    d["totp_actif"] = bool(d.get("totp_actif"))
    return d


class UtilisateursSQLite:
    def __init__(self, chemin: Optional[Path] = None):
        self.chemin = Path(chemin or (config.DB_DIR / "utilisateurs.db"))
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._seed_admin()

    def _connect(self) -> sqlite3.Connection:
        return connecter(self.chemin)

    def _init_db(self) -> None:
        if self.chemin.exists():
            with lecture(self.chemin) as conn:
                existe = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'admin_audit'"
                ).fetchone()
                if existe and "empreinte" not in colonnes(conn, "admin_audit"):
                    sauvegarder_avant_migration(self.chemin, "securite")
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
                CREATE TABLE IF NOT EXISTS auth_tentatives (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cle TEXT NOT NULL,
                    succes INTEGER NOT NULL,
                    cree_le TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_tentatives_cle ON auth_tentatives(cle, cree_le);
                """
            )
            # Migration douce
            cols = colonnes(conn, "users")
            for col in ("google_id", "apple_id", "github_id", "github_login", "totp_secret"):
                if col not in cols:
                    conn.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
            if "totp_actif" not in cols:
                conn.execute("ALTER TABLE users ADD COLUMN totp_actif INTEGER NOT NULL DEFAULT 0")
            if "totp_dernier_pas" not in cols:
                conn.execute("ALTER TABLE users ADD COLUMN totp_dernier_pas INTEGER")
            for col in ("google_id", "github_id", "apple_id"):
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_users_{col} ON users({col})"
                )
            cols_audit = colonnes(conn, "admin_audit")
            if "categorie" not in cols_audit:
                conn.execute(
                    f"ALTER TABLE admin_audit ADD COLUMN categorie TEXT NOT NULL DEFAULT '{CATEGORIE_ADMIN}'"
                )
            if "gravite" not in cols_audit:
                conn.execute("ALTER TABLE admin_audit ADD COLUMN gravite TEXT NOT NULL DEFAULT 'info'")
            for col in ("empreinte", "empreinte_prec"):
                if col not in cols_audit:
                    conn.execute(f"ALTER TABLE admin_audit ADD COLUMN {col} TEXT")
            conn.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_date ON admin_audit(cree_le);
                CREATE TRIGGER IF NOT EXISTS admin_audit_ajout_seul_maj
                    BEFORE UPDATE ON admin_audit
                    BEGIN SELECT RAISE(ABORT, 'journal d''audit en ajout seul'); END;
                CREATE TRIGGER IF NOT EXISTS admin_audit_ajout_seul_suppr
                    BEFORE DELETE ON admin_audit
                    BEGIN SELECT RAISE(ABORT, 'journal d''audit en ajout seul'); END;
                """
            )

    def _seed_admin(self) -> None:
        """Crée un admin depuis ADMIN_EMAIL / ADMIN_PASSWORD s'il n'existe aucun administrateur."""
        email = (os.getenv("ADMIN_EMAIL") or "admin@assistdoc.local").strip().lower()
        password = (os.getenv("ADMIN_PASSWORD") or os.getenv("STREAMLIT_PASSWORD") or "").strip()
        if not password:
            # Pas de secret → pas de seed auto (évite un admin faible en prod)
            return
        secret_totp = (os.getenv("ADMIN_TOTP_SECRET") or "").replace(" ", "").upper() or None
        promu: Optional[str] = None
        with ecriture(self.chemin) as conn:
            if conn.execute("SELECT 1 FROM users WHERE tier = 'admin' LIMIT 1").fetchone():
                return
            exist = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if exist:
                # Adresse déjà inscrite (l'inscription ne vérifie pas l'e-mail) : le mot de passe
                # est remplacé et toutes les sessions existantes de ce compte sont révoquées.
                promu = exist["id"]
                conn.execute(
                    "UPDATE users SET tier = 'admin', password_hash = ?, totp_secret = ?, "
                    "totp_actif = ?, totp_dernier_pas = NULL WHERE id = ?",
                    (_hash_pwd(password), secret_totp, 1 if secret_totp else 0, promu),
                )
                conn.execute(
                    "UPDATE sessions SET revoque_le = ? WHERE user_id = ? AND revoque_le IS NULL",
                    (_utc_now(), promu),
                )
            else:
                uid = str(uuid.uuid4())
                conn.execute(
                    "INSERT INTO users (id, email, password_hash, display_name, tier, cree_le, "
                    "derniere_connexion, totp_secret, totp_actif) "
                    "VALUES (?, ?, ?, ?, 'admin', ?, ?, ?, ?)",
                    (uid, email, _hash_pwd(password), "Administrateur", _utc_now(), _utc_now(),
                     secret_totp, 1 if secret_totp else 0),
                )
        self.audit(
            "systeme", "seed_admin",
            f"Administrateur initial depuis les secrets ({masquer_email(email)})"
            + (" — compte existant promu, sessions révoquées" if promu else ""),
            categorie=CATEGORIE_SECURITE, gravite="elevee" if promu else "info",
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
        if "@" not in email or len(email) > 254:
            return None, "Adresse e-mail invalide."
        if len(password or "") < MOT_DE_PASSE_MIN:
            return None, f"Mot de passe trop court ({MOT_DE_PASSE_MIN} caractères minimum)."
        if len(password) > 1024:
            return None, "Mot de passe trop long."
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
                        _hash_pwd(password),
                        (display_name or email.split("@")[0])[:80],
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError:
            return None, "Cet email est déjà inscrit."
        return self.obtenir(uid), "Compte créé."

    # ── Limitation des tentatives ────────────────────────────────────────────

    def _enregistrer_tentative(self, cles: Iterable[str], succes: bool) -> None:
        now = _maintenant()
        retention = now - timedelta(days=politique.valeur("SECU_RETENTION_TENTATIVES_JOURS"))
        with ecriture(self.chemin) as conn:
            conn.execute("DELETE FROM auth_tentatives WHERE cree_le < ?", (retention.isoformat(),))
            conn.executemany(
                "INSERT INTO auth_tentatives (cle, succes, cree_le) VALUES (?, ?, ?)",
                [(c, 1 if succes else 0, now.isoformat()) for c in cles],
            )

    def echecs_recents(self, cle: str) -> int:
        """Échecs de la clé dans la fenêtre, depuis le dernier succès."""
        depuis = (_maintenant() - timedelta(minutes=politique.valeur("SECU_FENETRE_MIN"))).isoformat()
        with lecture(self.chemin) as conn:
            ok = conn.execute(
                "SELECT MAX(cree_le) AS d FROM auth_tentatives WHERE cle = ? AND succes = 1", (cle,)
            ).fetchone()["d"]
            borne = max(depuis, ok) if ok else depuis
            return int(conn.execute(
                "SELECT COUNT(*) AS n FROM auth_tentatives WHERE cle = ? AND succes = 0 AND cree_le > ?",
                (cle, borne),
            ).fetchone()["n"])

    def _bloque(self, cles: Iterable[str]) -> bool:
        maximum = politique.valeur("SECU_MAX_ECHECS")
        for cle in cles:
            # Une adresse IP peut être partagée (NAT, proxy) : seuil plus large
            seuil = maximum * 4 if cle.startswith("ip:") else maximum
            if self.echecs_recents(cle) >= seuil:
                return True
        return False

    def debloquer(self, cle: str, acteur: str = "") -> None:
        """Considère la clé comme réussie (lève le blocage) ; réservé à la récupération."""
        self._enregistrer_tentative([cle], True)
        self.evenement_securite("auth_deblocage", "moyenne", "Blocage de connexion levé", acteur=acteur)

    def connecter_email(
        self, email: str, password: str, origine: Optional[str] = None
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """Connexion par mot de passe. `origine` : adresse IP du client si connue.

        Le message d'échec est identique que l'adresse existe ou non ; l'état « suspendu »
        n'est révélé qu'après un mot de passe correct.
        """
        email = (email or "").strip().lower()
        cles = [cle_tentative("email", email)]
        if origine:
            cles.append(cle_tentative("ip", origine))
        masque = masquer_email(email)
        if self._bloque(cles):
            self.evenement_securite("auth_bloquee", "faible", f"Tentative pendant un blocage ({masque})")
            return None, MSG_BLOCAGE
        with lecture(self.chemin) as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        stocke = (row["password_hash"] if row else "") or ""
        valide = _verifier_pwd(password or "", stocke or _hash_leurre(), row["id"] if row else "")
        if not row or not stocke or not valide:
            self._enregistrer_tentative(cles, False)
            self.evenement_securite("auth_echec", "faible", f"Échec de connexion par e-mail ({masque})")
            if self._bloque(cles):
                self.evenement_securite(
                    "auth_verrouillage", "moyenne",
                    f"Blocage temporaire après {politique.valeur('SECU_MAX_ECHECS')} échecs ({masque})",
                )
            return None, MSG_ECHEC_CONNEXION
        if row["suspended"]:
            self.evenement_securite(
                "auth_compte_suspendu", "moyenne", f"Connexion refusée : compte suspendu ({masque})",
                acteur=row["id"],
            )
            return None, "Compte suspendu. Contactez l'administrateur."
        self._enregistrer_tentative(cles, True)
        if not stocke.startswith("scrypt$"):
            with ecriture(self.chemin) as conn:
                conn.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (_hash_pwd(password), row["id"]),
                )
        self._touch(row["id"])
        self.evenement_securite(
            "auth_succes", "info", f"Mot de passe vérifié ({masque})", acteur=row["id"]
        )
        return self.obtenir(row["id"]), "Connecté."

    def changer_mot_de_passe(self, user_id: str, nouveau: str, acteur: str = "") -> Tuple[bool, str]:
        """Réinitialisation hors interface (script de récupération) ; toutes les sessions sont révoquées."""
        compte = self.obtenir(user_id) or {}
        problemes = mots_de_passe.erreurs(nouveau, [compte.get("email") or "", compte.get("display_name") or ""])
        if problemes:
            return False, problemes[0]
        with ecriture(self.chemin) as conn:
            cur = conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ? AND email IS NOT NULL",
                (_hash_pwd(nouveau), user_id),
            )
            if cur.rowcount == 0:
                return False, "Compte introuvable ou sans connexion par e-mail."
        self.revoquer_sessions_utilisateur(user_id, acteur=acteur)
        self.audit(acteur, "mot_de_passe_reinitialise", f"Compte {user_id[:8]}",
                   categorie=CATEGORIE_SECURITE, gravite="elevee")
        return True, "Mot de passe modifié ; sessions révoquées."

    def modifier_mon_mot_de_passe(
        self, jeton_session: Optional[str], actuel: str, nouveau: str, confirmation: str,
        code_mfa: str = "",
    ) -> Tuple[bool, str]:
        """Changement par le titulaire. Le compte est déduit du jeton de session (jamais d'un
        identifiant fourni) ; les autres sessions sont révoquées, la session courante conservée."""
        user = self.valider_session(jeton_session)
        if not user or user.get("tier") == "guest":
            self.evenement_securite("acces_refuse", "moyenne", "Changement de mot de passe sans session valide")
            return False, MSG_SESSION_INVALIDE
        uid = user["id"]
        cles = [cle_tentative("mdp", uid)]
        if self._bloque(cles):
            self.evenement_securite("mot_de_passe_echec", "moyenne", "Tentative pendant un blocage", acteur=uid)
            return False, MSG_MDP_BLOCAGE
        with lecture(self.chemin) as conn:
            row = conn.execute("SELECT email, password_hash FROM users WHERE id = ?", (uid,)).fetchone()
        stocke = (row["password_hash"] if row else "") or ""
        if not row or not row["email"] or not stocke:
            return False, MSG_MDP_SANS_MOT_DE_PASSE
        if not _verifier_pwd(actuel or "", stocke, uid):
            self._enregistrer_tentative(cles, False)
            self.evenement_securite("mot_de_passe_echec", "moyenne", "Mot de passe actuel incorrect", acteur=uid)
            if self._bloque(cles):
                self.evenement_securite(
                    "auth_verrouillage", "elevee", "Changement de mot de passe bloqué après échecs", acteur=uid
                )
            return False, MSG_MDP_ACTUEL
        if user.get("totp_actif"):
            ok, msg = self.verifier_totp(uid, code_mfa)
            if not ok:
                return False, msg
        problemes = mots_de_passe.erreurs(nouveau, [row["email"], user.get("display_name") or ""])
        if problemes:
            return False, problemes[0]
        if nouveau != confirmation:
            return False, "La confirmation ne correspond pas au nouveau mot de passe."
        if _verifier_pwd(nouveau, stocke, uid):
            return False, "Le nouveau mot de passe doit être différent de l'actuel."
        with ecriture(self.chemin) as conn:
            # Condition sur l'ancien hachage : deux soumissions simultanées ne peuvent pas aboutir toutes deux
            cur = conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ? AND password_hash = ?",
                (_hash_pwd(nouveau), uid, stocke),
            )
            if cur.rowcount != 1:
                return False, "Le mot de passe a été modifié entre-temps. Rechargez la page."
            revoquees = conn.execute(
                "UPDATE sessions SET revoque_le = ? WHERE user_id = ? AND revoque_le IS NULL AND jeton_hash != ?",
                (_utc_now(), uid, empreinte_jeton(jeton_session or "")),
            ).rowcount
        try:
            self._enregistrer_tentative(cles, True)
        except sqlite3.Error as exc:  # le mot de passe est déjà enregistré : ne pas signaler un échec
            print(f"   ⚠️  Compteur de tentatives non remis à zéro : {type(exc).__name__}")
        self.evenement_securite(
            "mot_de_passe_modifie", "moyenne",
            f"Modifié par le titulaire ; {revoquees} autre(s) session(s) révoquée(s), session courante conservée",
            acteur=uid,
        )
        if revoquees:
            return True, (f"Mot de passe modifié. {revoquees} autre(s) session(s) ont été fermée(s) ; "
                          "cette session reste ouverte.")
        return True, "Mot de passe modifié. Cette session reste ouverte."

    # ── Second facteur (TOTP) ────────────────────────────────────────────────

    def _ligne_totp(self, user_id: str) -> Optional[sqlite3.Row]:
        with lecture(self.chemin) as conn:
            return conn.execute(
                "SELECT id, totp_secret, totp_actif, totp_dernier_pas, suspended FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()

    def preparer_totp(self, user_id: str) -> str:
        """Nouveau secret en attente de confirmation (MFA pas encore active)."""
        secret = totp.generer_secret()
        with ecriture(self.chemin) as conn:
            cur = conn.execute(
                "UPDATE users SET totp_secret = ?, totp_dernier_pas = NULL "
                "WHERE id = ? AND totp_actif = 0",
                (secret, user_id),
            )
            if cur.rowcount == 0:
                raise ValueError("MFA déjà active ou compte introuvable")
        return secret

    def activer_totp(self, user_id: str, code: str) -> bool:
        row = self._ligne_totp(user_id)
        if not row or row["totp_actif"] or not row["totp_secret"]:
            return False
        pas = totp.verifier(row["totp_secret"], code)
        if pas is None:
            self.evenement_securite("mfa_echec", "faible", "Code invalide à l'activation", acteur=user_id)
            return False
        with ecriture(self.chemin) as conn:
            conn.execute(
                "UPDATE users SET totp_actif = 1, totp_dernier_pas = ? WHERE id = ?", (pas, user_id)
            )
        self.audit(user_id, "mfa_active", f"Compte {user_id[:8]}", categorie=CATEGORIE_SECURITE, gravite="info")
        return True

    def desactiver_totp(self, user_id: str, acteur: str = "") -> bool:
        with ecriture(self.chemin) as conn:
            cur = conn.execute(
                "UPDATE users SET totp_secret = NULL, totp_actif = 0, totp_dernier_pas = NULL WHERE id = ?",
                (user_id,),
            )
        if cur.rowcount:
            self.audit(acteur or user_id, "mfa_desactive", f"Compte {user_id[:8]}",
                       categorie=CATEGORIE_SECURITE, gravite="moyenne")
        return bool(cur.rowcount)

    def verifier_totp(self, user_id: str, code: str) -> Tuple[bool, str]:
        """Second facteur à la connexion : limité en tentatives, chaque code ne sert qu'une fois."""
        cles = [cle_tentative("mfa", user_id)]
        if self._bloque(cles):
            self.evenement_securite("auth_bloquee", "faible", "Code MFA pendant un blocage", acteur=user_id)
            return False, MSG_MFA_BLOCAGE
        row = self._ligne_totp(user_id)
        if not row or not row["totp_actif"] or row["suspended"]:
            return False, MSG_MFA_INVALIDE
        pas = totp.verifier(row["totp_secret"], code, dernier_pas=row["totp_dernier_pas"])
        accepte = False
        if pas is not None:
            with ecriture(self.chemin) as conn:
                cur = conn.execute(
                    "UPDATE users SET totp_dernier_pas = ? WHERE id = ? "
                    "AND (totp_dernier_pas IS NULL OR totp_dernier_pas < ?)",
                    (pas, user_id, pas),
                )
                accepte = cur.rowcount == 1
        self._enregistrer_tentative(cles, accepte)
        if not accepte:
            self.evenement_securite("mfa_echec", "faible", "Code MFA invalide", acteur=user_id)
            if self._bloque(cles):
                self.evenement_securite("auth_verrouillage", "moyenne", "Blocage MFA après échecs", acteur=user_id)
            return False, MSG_MFA_INVALIDE
        self.evenement_securite("auth_succes", "info", "Second facteur vérifié", acteur=user_id)
        return True, "Code vérifié."

    # ── Comptes OAuth ────────────────────────────────────────────────────────

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

    def revoquer_sessions_utilisateur(
        self, user_id: str, acteur: str = "", sauf_jeton: Optional[str] = None
    ) -> int:
        """Révoque toutes les sessions du compte (sauf, éventuellement, la session courante)."""
        sauf = empreinte_jeton(sauf_jeton) if sauf_jeton else ""
        with ecriture(self.chemin) as conn:
            cur = conn.execute(
                "UPDATE sessions SET revoque_le = ? WHERE user_id = ? AND revoque_le IS NULL "
                "AND jeton_hash != ?",
                (_utc_now(), user_id, sauf),
            )
            n = cur.rowcount
        if acteur and n:
            self.evenement_securite(
                "session_revoquee", "moyenne", f"{n} session(s) révoquée(s) pour le compte {user_id[:8]}",
                acteur=acteur,
            )
        return n

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
        """Compte sans ses secrets (hachage du mot de passe, secret TOTP)."""
        with lecture(self.chemin) as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        return _public(row)

    def lister_users(self, limite: int = 200) -> List[Dict[str, Any]]:
        with lecture(self.chemin) as conn:
            rows = conn.execute("SELECT * FROM users").fetchall()
        users = [_public(r) for r in rows]
        users.sort(
            key=lambda u: u.get("derniere_connexion") or u.get("cree_le") or "",
            reverse=True,
        )
        return users[:limite]

    # ── Administration (contrôles côté serveur) ──────────────────────────────

    def est_admin_actif(self, user_id: Optional[str]) -> bool:
        if not user_id:
            return False
        with lecture(self.chemin) as conn:
            row = conn.execute(
                "SELECT 1 FROM users WHERE id = ? AND tier = 'admin' AND suspended = 0", (user_id,)
            ).fetchone()
        return row is not None

    def _refuser(self, acteur: str, operation: str) -> bool:
        self.evenement_securite(
            "acces_refuse", "elevee",
            f"Opération « {operation} » refusée : l'acteur n'est pas un administrateur actif",
            acteur=acteur,
        )
        return False

    def set_tier(self, user_id: str, tier: str, admin_id: str = "") -> bool:
        """Change le rôle. L'acteur doit être un administrateur actif ; le dernier administrateur
        actif ne peut pas être rétrogradé ; un administrateur ne peut pas se rétrograder."""
        tier = (tier or "").lower()
        if tier not in TIERS:
            return False
        if not self.est_admin_actif(admin_id):
            return self._refuser(admin_id, "modifier un rôle")
        if admin_id == user_id and tier != "admin":
            return False
        with ecriture(self.chemin) as conn:
            cible = conn.execute("SELECT tier FROM users WHERE id = ?", (user_id,)).fetchone()
            if cible is None:
                return False
            ancien = cible["tier"]
            if ancien == "admin" and tier != "admin":
                n_admins = conn.execute(
                    "SELECT COUNT(*) AS n FROM users WHERE tier = 'admin' AND suspended = 0"
                ).fetchone()["n"]
                if n_admins <= 1:
                    return False
            conn.execute("UPDATE users SET tier = ? WHERE id = ?", (tier, user_id))
        if ancien == "admin" and tier != "admin":
            self.revoquer_sessions_utilisateur(user_id)
        privilegie = "admin" in (ancien, tier)
        self.audit(
            admin_id, "set_tier", f"{user_id} : {ancien} → {tier}",
            categorie=CATEGORIE_SECURITE if privilegie else CATEGORIE_ADMIN,
            gravite="elevee" if privilegie else "info",
        )
        return True

    def suspendre(self, user_id: str, suspended: bool, admin_id: str = "") -> bool:
        """Suspend ou réactive un compte (administrateur actif requis). Suspendre révoque
        les sessions ; on ne peut ni se suspendre soi-même ni suspendre le dernier administrateur."""
        if not self.est_admin_actif(admin_id):
            return self._refuser(admin_id, "suspendre un compte" if suspended else "réactiver un compte")
        if suspended and admin_id == user_id:
            return False
        with ecriture(self.chemin) as conn:
            cible = conn.execute("SELECT tier FROM users WHERE id = ?", (user_id,)).fetchone()
            if cible is None:
                return False
            if suspended and cible["tier"] == "admin":
                n_admins = conn.execute(
                    "SELECT COUNT(*) AS n FROM users WHERE tier = 'admin' AND suspended = 0"
                ).fetchone()["n"]
                if n_admins <= 1:
                    return False
            conn.execute(
                "UPDATE users SET suspended = ? WHERE id = ?", (1 if suspended else 0, user_id)
            )
        if suspended:
            self.revoquer_sessions_utilisateur(user_id)
        self.audit(
            admin_id, "suspend" if suspended else "unsuspend", user_id,
            categorie=CATEGORIE_SECURITE, gravite="moyenne",
        )
        return True

    # ── Usage et quotas ──────────────────────────────────────────────────────

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

    @staticmethod
    def _requetes_jour(conn: sqlite3.Connection, user_id: str) -> int:
        """Requêtes depuis minuit UTC (renouvellement quotidien du quota)."""
        debut = _maintenant().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        return int(conn.execute(
            "SELECT COUNT(*) AS n FROM usage_events WHERE user_id = ? AND kind = 'ask' AND cree_le >= ?",
            (user_id, debut),
        ).fetchone()["n"])

    @staticmethod
    def _requetes_invites_heure(conn: sqlite3.Connection) -> int:
        depuis = (_maintenant() - timedelta(hours=1)).isoformat()
        return int(conn.execute(
            "SELECT COUNT(*) AS n FROM usage_events e JOIN users u ON u.id = e.user_id "
            "WHERE e.kind = 'ask' AND u.tier = 'guest' AND e.cree_le >= ?",
            (depuis,),
        ).fetchone()["n"])

    def compter_requetes_jour(self, user_id: str) -> int:
        with lecture(self.chemin) as conn:
            return self._requetes_jour(conn, user_id)

    def requetes_invites_derniere_heure(self) -> int:
        with lecture(self.chemin) as conn:
            return self._requetes_invites_heure(conn)

    def _controle_quota(self, conn: sqlite3.Connection, user: Dict[str, Any]) -> Tuple[bool, str]:
        if not user:
            return False, "Non connecté."
        if user.get("suspended"):
            return False, "Compte suspendu."
        tier = user.get("tier") or "guest"
        q = quota_pour(tier)
        if q.requetes_par_jour < 0:
            return True, "Illimité (admin)."
        if tier == "guest":
            plafond = politique.valeur("QUOTA_INVITES_GLOBAL_HEURE")
            if plafond and self._requetes_invites_heure(conn) >= plafond:
                return False, MSG_INVITES_SATURE
        n = self._requetes_jour(conn, user["id"])
        if n >= q.requetes_par_jour:
            if tier == "guest":
                return False, MSG_QUOTA_INVITE.format(n=q.requetes_par_jour)
            return (
                False,
                f"Quota atteint ({n}/{q.requetes_par_jour} requêtes/jour pour {q.label}). "
                "Réessayez demain.",
            )
        reste = q.requetes_par_jour - n
        return True, f"{reste} requête(s) restante(s) aujourd'hui ({q.label})."

    def verifier_quota(self, user: Dict[str, Any]) -> Tuple[bool, str]:
        """Consultation seule (aucune requête n'est décomptée)."""
        with lecture(self.chemin) as conn:
            return self._controle_quota(conn, user)

    def reserver_requete(
        self, user: Dict[str, Any], meta: Optional[Dict] = None
    ) -> Tuple[bool, str]:
        """Contrôle du quota et décompte de la requête dans une même transaction exclusive :
        des requêtes simultanées ne peuvent pas dépasser la limite."""
        with ecriture(self.chemin) as conn:
            ok, msg = self._controle_quota(conn, user)
            if ok:
                conn.execute(
                    "INSERT INTO usage_events (user_id, kind, meta_json, cree_le) VALUES (?, 'ask', ?, ?)",
                    (user["id"], json.dumps(meta or {}, ensure_ascii=False), _utc_now()),
                )
        return ok, msg

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

    # ── Journal d'audit (ajout seul, chaîné) ─────────────────────────────────

    def audit(
        self,
        admin_id: str,
        action: str,
        details: str = "",
        *,
        categorie: str = CATEGORIE_ADMIN,
        gravite: str = "info",
    ) -> None:
        """Ajoute une entrée chaînée à la précédente (toute modification ultérieure est détectable)."""
        cree_le = _utc_now()
        acteur = admin_id or ""
        details = (details or "")[:1000]
        gravite = gravite_valide(gravite)
        with ecriture(self.chemin) as conn:
            prec = conn.execute(
                "SELECT empreinte FROM admin_audit WHERE empreinte IS NOT NULL ORDER BY id DESC LIMIT 1"
            ).fetchone()
            precedente = prec["empreinte"] if prec else ""
            conn.execute(
                "INSERT INTO admin_audit (admin_id, action, details, cree_le, categorie, gravite, "
                "empreinte, empreinte_prec) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (acteur, action, details, cree_le, categorie, gravite,
                 empreinte_audit(precedente, acteur, action, details, cree_le, categorie, gravite),
                 precedente),
            )

    def evenement_securite(self, action: str, gravite: str = "faible", details: str = "",
                           acteur: str = "") -> None:
        """Événement de sécurité (jamais de mot de passe, de jeton, de clé ni de contenu de document)."""
        try:
            self.audit(acteur, action, details, categorie=CATEGORIE_SECURITE, gravite=gravite)
        except sqlite3.Error as exc:
            print(f"   ⚠️  Journal de sécurité indisponible : {type(exc).__name__}")

    def lister_audit(
        self,
        limite: int = 40,
        *,
        categorie: Optional[str] = None,
        depuis: Optional[str] = None,
        actions: Optional[Iterable[str]] = None,
        gravites: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]:
        conditions, params = [], []
        if categorie:
            conditions.append("categorie = ?")
            params.append(categorie)
        if depuis:
            conditions.append("cree_le >= ?")
            params.append(depuis)
        for colonne, valeurs in (("action", actions), ("gravite", gravites)):
            valeurs = list(valeurs or [])
            if valeurs:
                conditions.append(f"{colonne} IN ({', '.join('?' for _ in valeurs)})")
                params.extend(valeurs)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with lecture(self.chemin) as conn:
            rows = conn.execute(
                f"SELECT id, admin_id, action, details, cree_le, categorie, gravite FROM admin_audit "
                f"{where} ORDER BY id DESC LIMIT ?",
                (*params, int(limite)),
            ).fetchall()
        return [dict(r) for r in rows]

    def verifier_journal(self) -> Dict[str, Any]:
        """Recalcule la chaîne d'empreintes. Les entrées antérieures au chaînage sont comptées à part."""
        with lecture(self.chemin) as conn:
            rows = conn.execute(
                "SELECT id, admin_id, action, details, cree_le, categorie, gravite, empreinte, "
                "empreinte_prec FROM admin_audit ORDER BY id"
            ).fetchall()
        non_chainees = 0
        precedente = ""
        for r in rows:
            if not r["empreinte"]:
                non_chainees += 1
                continue
            attendue = empreinte_audit(
                precedente, r["admin_id"], r["action"], r["details"], r["cree_le"],
                r["categorie"], r["gravite"],
            )
            if (r["empreinte_prec"] or "") != precedente or not hmac.compare_digest(attendue, r["empreinte"]):
                return {
                    "valide": False, "total": len(rows), "non_chainees": non_chainees,
                    "premiere_anomalie": r["id"],
                }
            precedente = r["empreinte"]
        return {"valide": True, "total": len(rows), "non_chainees": non_chainees, "premiere_anomalie": None}
