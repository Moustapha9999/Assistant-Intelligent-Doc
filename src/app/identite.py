"""
Résolution centralisée de l'identité courante (interface Streamlit).

Règles :
- l'identité est toujours un `users.id` (UUID aléatoire) validé côté serveur ; il n'existe
  aucun propriétaire générique partagé (pas de « guest » commun) ;
- le navigateur ne détient qu'un jeton de session aléatoire (cookie `assistdoc_sid`) ; le serveur
  n'en stocke que l'empreinte, avec expiration et révocation (table `sessions`) ;
- jeton absent, inconnu, expiré, révoqué ou compte suspendu → nouvelle identité invitée unique ;
- connexion : nouveau jeton pour le compte (rotation), l'ancien est révoqué ;
- déconnexion : jeton révoqué, nouvelle identité invitée distincte ;
- aucune fusion automatique entre invité et compte, ni entre deux comptes.

Le cookie est lu et écrit par un composant JavaScript (Streamlit ne sait pas poser d'en-tête
Set-Cookie, et Streamlit Cloud ne transmet pas toujours les cookies au serveur) : il ne peut donc
pas être HttpOnly. Aucun rechargement de page n'est utilisé. Il est `Secure` (HTTPS), `SameSite=Lax`, à durée limitée,
et ne contient aucune donnée personnelle. Sans cookie (navigateur qui les bloque), l'isolation
reste garantie : chaque session Streamlit obtient simplement sa propre identité invitée.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from app.utilisateurs_sqlite import TIERS_COMPTE, UtilisateursSQLite, duree_session

NOM_COOKIE = "assistdoc_sid"


@dataclass(frozen=True)
class Identite:
    user_id: str
    tier: str
    libelle: str

    @property
    def est_authentifiee(self) -> bool:
        return self.tier in TIERS_COMPTE

    @property
    def est_invitee(self) -> bool:
        return not self.est_authentifiee

    @property
    def est_admin(self) -> bool:
        return self.tier == "admin"

    @classmethod
    def depuis_user(cls, user: Dict[str, Any]) -> "Identite":
        tier = (user.get("tier") or "guest").lower()
        libelle = (
            user.get("email") or user.get("github_login") or user.get("display_name") or ""
        ).strip()
        return cls(user_id=user["id"], tier=tier, libelle=libelle)


# ── Logique pure (testable sans Streamlit) ───────────────────────────────────


def choisir_session(
    db: UtilisateursSQLite,
    jeton_session: Optional[str],
    provisoire: bool,
    jeton_cookie: Optional[str],
    cookie_connu: bool,
) -> Tuple[Dict[str, Any], str, bool]:
    """Retourne (utilisateur, jeton, provisoire).

    - jeton déjà confirmé pour cette session Streamlit et toujours valide : conservé ;
    - sinon jeton du cookie navigateur s'il est valide (remplace une identité provisoire) ;
    - sinon jeton de session existant, ou nouvelle identité invitée unique.

    Une identité est « provisoire » tant que le navigateur n'a pas encore transmis son cookie :
    elle ne doit pas être écrite dans le cookie, pour ne pas écraser une session valide.
    """
    if jeton_session and not provisoire:
        user = db.valider_session(jeton_session)
        if user:
            return user, jeton_session, False
    if jeton_cookie and jeton_cookie != jeton_session:
        user = db.valider_session(jeton_cookie)
        if user:
            if jeton_session and provisoire:
                db.revoquer_session(jeton_session)
            return user, jeton_cookie, False
    if jeton_session:
        user = db.valider_session(jeton_session)
        if user:
            return user, jeton_session, provisoire and not cookie_connu
    invite = db.creer_invite("Invité")
    return invite, db.creer_session(invite["id"]), not cookie_connu


def resoudre_identite(
    db: UtilisateursSQLite,
    jeton_session: Optional[str],
    jeton_cookie: Optional[str],
) -> Tuple[Dict[str, Any], str, bool]:
    """Retourne (utilisateur, jeton, nouvelle_identite) quand le cookie est connu."""
    user, jeton, _ = choisir_session(db, jeton_session, False, jeton_cookie, True)
    return user, jeton, jeton not in (jeton_session, jeton_cookie)


def ouvrir_session_compte(
    db: UtilisateursSQLite, user: Dict[str, Any], jeton_precedent: Optional[str]
) -> str:
    """Connexion : révoque le jeton précédent (invité ou autre compte) et en émet un nouveau."""
    db.revoquer_session(jeton_precedent)
    return db.creer_session(user["id"])


def fermer_session(db: UtilisateursSQLite, jeton: Optional[str]) -> Tuple[Dict[str, Any], str]:
    """Déconnexion : révoque le jeton et crée une identité invitée distincte."""
    db.revoquer_session(jeton)
    invite = db.creer_invite("Invité")
    return invite, db.creer_session(invite["id"])


# ── Intégration Streamlit ────────────────────────────────────────────────────

CLE_COMPOSANT = "_assistdoc_cookie"

# Composant v2 (non isolé dans une iframe) : lit le cookie du document de l'application,
# le transmet au serveur, et écrit le jeton confirmé. Aucun rechargement de page.
_JS_COOKIE = """
export default function(component) {
  const { data, setStateValue } = component;
  const lire = () => {
    const m = document.cookie.match(/(?:^|; )assistdoc_sid=([^;]*)/);
    return m ? decodeURIComponent(m[1]) : "";
  };
  if (data && data.nouveau) {
    const secure = window.location.protocol === "https:" ? "; Secure" : "";
    document.cookie = "assistdoc_sid=" + encodeURIComponent(data.nouveau)
      + "; Max-Age=" + data.age + "; Path=/; SameSite=Lax" + secure;
  }
  setStateValue("cookie", lire());
}
"""

_composant_cookie = None


def _st():
    import streamlit as st

    return st


def users_db() -> UtilisateursSQLite:
    st = _st()

    @st.cache_resource
    def _instance() -> UtilisateursSQLite:
        return UtilisateursSQLite()

    return _instance()


def _cookie_contexte() -> str:
    try:
        return (_st().context.cookies.get(NOM_COOKIE) or "").strip()
    except Exception:
        return ""


def _cookie_composant() -> Optional[str]:
    """Valeur transmise par le navigateur ; None tant qu'elle n'est pas encore connue."""
    etat = _st().session_state.get(CLE_COMPOSANT)
    try:
        valeur = etat.get("cookie") if etat is not None else None
    except Exception:
        return None
    return None if valeur is None else str(valeur).strip()


def _appliquer(user: Dict[str, Any], jeton: str, provisoire: bool = False) -> Identite:
    st = _st()
    st.session_state["_jeton_session"] = jeton
    st.session_state["_jeton_provisoire"] = provisoire
    st.session_state["_cookie_a_ecrire"] = (
        None if provisoire else (jeton, int(duree_session(user.get("tier")).total_seconds()))
    )
    st.session_state.auth_ok = True
    st.session_state.auth_user_id = user["id"]
    st.session_state.auth_user = (
        user.get("email") or user.get("github_login") or user.get("display_name") or "user"
    )
    st.session_state.auth_tier = user.get("tier") or "guest"
    return Identite.depuis_user(user)


def identite_courante() -> Identite:
    """Identité validée côté serveur pour la session Streamlit en cours (à appeler à chaque run)."""
    st = _st()
    contexte = _cookie_contexte()
    composant = _cookie_composant()
    user, jeton, provisoire = choisir_session(
        users_db(),
        st.session_state.get("_jeton_session"),
        bool(st.session_state.get("_jeton_provisoire")),
        contexte or composant or "",
        bool(contexte) or composant is not None,
    )
    return _appliquer(user, jeton, provisoire)


def identite_session() -> Identite:
    """Identité déjà résolue pendant ce run (sans nouvel accès base) ; la résout sinon."""
    st = _st()
    uid = st.session_state.get("auth_user_id")
    if uid and st.session_state.get("_jeton_session"):
        return Identite(
            user_id=uid,
            tier=(st.session_state.get("auth_tier") or "guest").lower(),
            libelle=str(st.session_state.get("auth_user") or ""),
        )
    return identite_courante()


def connecter(user: Dict[str, Any]) -> Identite:
    st = _st()
    jeton = ouvrir_session_compte(users_db(), user, st.session_state.get("_jeton_session"))
    return _appliquer(user, jeton)


def deconnecter() -> Identite:
    st = _st()
    invite, jeton = fermer_session(users_db(), st.session_state.get("_jeton_session"))
    return _appliquer(invite, jeton)


def jeton_session_courant() -> Optional[str]:
    return _st().session_state.get("_jeton_session")


def synchroniser_cookie() -> None:
    """À appeler une fois par run, après identite_courante()."""
    global _composant_cookie
    st = _st()
    if _composant_cookie is None:
        _composant_cookie = st.components.v2.component("assistdoc_session", js=_JS_COOKIE)
    a_ecrire = st.session_state.get("_cookie_a_ecrire")
    data = {"nouveau": a_ecrire[0], "age": a_ecrire[1]} if a_ecrire else {}
    _composant_cookie(key=CLE_COMPOSANT, data=data, on_cookie_change=lambda: None)
