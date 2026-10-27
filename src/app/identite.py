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

Le cookie est écrit par JavaScript (Streamlit ne sait pas poser d'en-tête Set-Cookie) :
il ne peut donc pas être HttpOnly. Il est `Secure` (HTTPS), `SameSite=Lax`, à durée limitée,
et ne contient aucune donnée personnelle. Sans cookie (navigateur qui les bloque), l'isolation
reste garantie : chaque session Streamlit obtient simplement sa propre identité invitée.
"""

from __future__ import annotations

import json
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


def resoudre_identite(
    db: UtilisateursSQLite,
    jeton_session: Optional[str],
    jeton_cookie: Optional[str],
) -> Tuple[Dict[str, Any], str, bool]:
    """Retourne (utilisateur, jeton, nouvelle_identite).

    Ordre : jeton déjà associé à la session Streamlit, puis jeton du cookie navigateur ;
    à défaut, création d'une identité invitée unique.
    """
    for jeton in (jeton_session, jeton_cookie):
        if jeton:
            user = db.valider_session(jeton)
            if user:
                return user, jeton, False
    invite = db.creer_invite("Invité")
    return invite, db.creer_session(invite["id"]), True


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


def _st():
    import streamlit as st

    return st


def users_db() -> UtilisateursSQLite:
    st = _st()

    @st.cache_resource
    def _instance() -> UtilisateursSQLite:
        return UtilisateursSQLite()

    return _instance()


def _cookie_navigateur() -> str:
    try:
        return (_st().context.cookies.get(NOM_COOKIE) or "").strip()
    except Exception:
        return ""


def _appliquer(user: Dict[str, Any], jeton: str) -> Identite:
    st = _st()
    precedent = st.session_state.get("_jeton_session")
    if jeton != precedent:
        # Paire (valeur attendue dans le navigateur, nouvelle valeur) pour le script cookie
        ancien = precedent if precedent else _cookie_navigateur()
        st.session_state["_cookie_paire"] = (ancien, jeton, int(duree_session(user.get("tier")).total_seconds()))
    st.session_state["_jeton_session"] = jeton
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
    user, jeton, _ = resoudre_identite(
        users_db(), st.session_state.get("_jeton_session"), _cookie_navigateur()
    )
    return _appliquer(user, jeton)


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


def script_cookie(ancien: str, nouveau: str, max_age: int) -> str:
    """JavaScript qui synchronise le cookie du navigateur avec la session serveur.

    - cookie déjà remplacé par un autre onglet (ni l'ancien ni le nouveau jeton) : on recharge
      pour adopter la session la plus récente au lieu de l'écraser ;
    - sinon on écrit le nouveau jeton (et on renouvelle sa durée).
    """
    params = json.dumps(
        {"nom": NOM_COOKIE, "ancien": ancien or "", "nouveau": nouveau, "age": int(max_age)}
    ).replace("<", "\\u003c")
    return f"""
<script>
(function() {{
  const p = {params};
  try {{
    const doc = window.parent.document;
    const m = doc.cookie.match(new RegExp('(?:^|; )' + p.nom + '=([^;]*)'));
    const actuel = m ? decodeURIComponent(m[1]) : "";
    if (actuel && actuel !== p.ancien && actuel !== p.nouveau) {{
      window.parent.location.reload();
      return;
    }}
    const secure = window.parent.location.protocol === "https:" ? "; Secure" : "";
    doc.cookie = p.nom + "=" + encodeURIComponent(p.nouveau) + "; Max-Age=" + p.age
      + "; Path=/; SameSite=Lax" + secure;
  }} catch (e) {{}}
}})();
</script>
"""


def synchroniser_cookie() -> None:
    """À appeler à chaque run (après identite_courante) : le composant est stable tant que
    la paire ne change pas, donc le script ne s'exécute qu'une fois par changement de jeton."""
    st = _st()
    paire = st.session_state.get("_cookie_paire")
    if not paire:
        return
    import streamlit.components.v1 as components

    ancien, nouveau, age = paire
    components.html(script_cookie(ancien, nouveau, age), height=0)
