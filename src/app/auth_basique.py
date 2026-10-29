"""
Auth AssistDoc — style ChatGPT :
- Accès invité immédiat
- Modal « Connectez-vous ou inscrivez-vous »
- Après quota invité → obligation email / GitHub
- Admin uniquement si compte tier=admin
"""

from __future__ import annotations

import html
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import streamlit as st
from dotenv import load_dotenv

# Charge .env à la racine du projet (OAuth Google / GitHub)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from app.auth_apple import (
    apple_oauth_configure,
    echanger_code as echanger_code_apple,
    nouveau_state as nouveau_state_apple,
    url_autorisation as url_autorisation_apple,
)
from app.auth_github import (
    echanger_code as echanger_code_github,
    github_oauth_configure,
    nouveau_state as nouveau_state_github,
    url_autorisation as url_autorisation_github,
)
from app.auth_google import (
    echanger_code as echanger_code_google,
    google_oauth_configure,
    nouveau_state as nouveau_state_google,
    url_autorisation as url_autorisation_google,
)
from app import identite as _identite
from app.quotas import quota_pour
from app.ui_composants import afficher_erreur, journal, notifier
from app.utilisateurs_sqlite import MSG_INVITES_SATURE

users_db = _identite.users_db
_users_db = users_db


def utilisateur_session() -> Optional[Dict[str, Any]]:
    """Utilisateur de l'identité courante, relu en base (rôle et suspension à jour)."""
    ident = _identite.identite_session()
    u = _users_db().obtenir(ident.user_id)
    if not u or u.get("suspended"):
        return None
    return u


def utilisateur_courant() -> str:
    u = utilisateur_session()
    if not u:
        return ""
    return (u.get("email") or u.get("github_login") or u.get("display_name") or "").strip()


def tier_courant() -> str:
    u = utilisateur_session()
    return (u.get("tier") if u else "guest") or "guest"


def est_compte_connecte() -> bool:
    return tier_courant() in {"email", "github", "google", "apple", "admin"}


def est_admin_session() -> bool:
    u = utilisateur_session()
    return bool(u and u.get("tier") == "admin")


def peut_gerer_corpus() -> bool:
    return est_admin_session()


def aller_accueil() -> None:
    """Revient à la page Accueil (navigation Streamlit)."""
    for cible in ("accueil.py", "Accueil"):
        try:
            st.switch_page(cible)
            return
        except Exception:
            continue
    st.rerun()


def exiger_admin(*, autoriser_login: bool = True) -> bool:
    """
    Garde d'accès admin (page / actions).
    Retourne True si tier=admin. Sinon affiche « Accès refusé » et stoppe.
    """
    exiger_auth()
    if est_admin_session():
        return True

    journaliser_acces_refuse("administration")
    afficher_erreur("Accès refusé : cette page est réservée aux administrateurs.")
    if est_compte_connecte():
        st.info(
            f"Compte actuel : **{utilisateur_courant()}** "
            f"(rôle : `{tier_courant()}`). "
            "Déconnectez-vous puis reconnectez-vous avec un compte administrateur."
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Retour à l'Accueil", key="admin_denied_home", use_container_width=True):
                aller_accueil()
        with c2:
            if st.button("Se déconnecter", key="admin_denied_logout", use_container_width=True):
                deconnecter()
                aller_accueil()
    elif autoriser_login:
        st.caption("Connectez-vous avec l'adresse e-mail administrateur.")
        formulaire_connexion(key_prefix="admin_gate")
    st.stop()
    return False


_CLES_UI_AUTH = (
    "oauth_provider",
    "github_auth_url", "google_auth_url", "apple_auth_url",
    "force_login", "show_auth_dialog",
    "auth_email_step", "auth_pending_email",
)
CLE_MFA = "auth_mfa_en_attente"
DUREE_MFA_S = 300


def _origine_client() -> Optional[str]:
    """Adresse IP du client si Streamlit la connaît (sert uniquement à limiter les tentatives)."""
    try:
        return st.context.ip_address or None
    except Exception:
        return None


def _finaliser_connexion(user: Dict[str, Any]) -> None:
    """Rotation du jeton de session vers le compte authentifié."""
    st.session_state.pop(CLE_MFA, None)
    _identite.connecter(user)
    for k in _CLES_UI_AUTH:
        st.session_state.pop(k, None)


def _appliquer_user(user: Dict[str, Any]) -> bool:
    """Premier facteur validé. Si la MFA est active, la session n'est ouverte qu'après le code.

    L'identifiant en attente reste dans l'état serveur de la session Streamlit : le navigateur
    ne peut ni le choisir ni le modifier.
    """
    if user.get("totp_actif"):
        st.session_state[CLE_MFA] = {"uid": user["id"], "expire": time.time() + DUREE_MFA_S}
        st.session_state.show_auth_dialog = True
        return False
    _finaliser_connexion(user)
    return True


def _mfa_en_attente() -> Optional[str]:
    attente = st.session_state.get(CLE_MFA)
    if not attente:
        return None
    if attente.get("expire", 0) < time.time():
        st.session_state.pop(CLE_MFA, None)
        return None
    return attente.get("uid")


def _formulaire_mfa(uid: str, key_prefix: str) -> None:
    st.markdown(
        '<p class="auth-sub">Saisissez le code à 6 chiffres affiché par votre application '
        "d'authentification.</p>",
        unsafe_allow_html=True,
    )
    with st.form(f"{key_prefix}_form_mfa", border=False):
        code = st.text_input(
            "Code de vérification", max_chars=6, placeholder="123456",
            label_visibility="collapsed", key=f"{key_prefix}_mfa_code",
        )
        valider = st.form_submit_button("Vérifier", type="primary", use_container_width=True)
    if st.button("Annuler", key=f"{key_prefix}_mfa_annuler", use_container_width=True):
        st.session_state.pop(CLE_MFA, None)
        st.rerun()
    if valider:
        ok, msg = _users_db().verifier_totp(uid, code)
        user = _users_db().obtenir(uid) if ok else None
        if user and not user.get("suspended"):
            _finaliser_connexion(user)
            notifier("Connecté en administrateur." if user.get("tier") == "admin" else "Vous êtes connecté.")
            st.rerun()
        else:
            afficher_erreur(msg)


def assurer_session_invite() -> Dict[str, Any]:
    u = utilisateur_session()
    if u:
        return u
    # Compte suspendu ou supprimé pendant la session : nouvelle identité invitée
    _identite.deconnecter()
    return utilisateur_session() or {}


def deconnecter() -> None:
    for k in (*_CLES_UI_AUTH, CLE_MFA):
        st.session_state.pop(k, None)
    _identite.deconnecter()


def journaliser_acces_refuse(ressource: str) -> None:
    u = utilisateur_session() or {}
    _users_db().evenement_securite(
        "acces_refuse", "moyenne",
        f"Accès à « {ressource} » refusé (rôle : {u.get('tier') or 'guest'})",
        acteur=u.get("id") or "",
    )


def _oauth_lier_session() -> bool:
    return os.getenv("OAUTH_STATE_LIER_SESSION", "1").strip().lower() not in {"0", "false", "non", "no"}


def _etat_oauth_valide(state: str, fournisseur: str) -> bool:
    return _users_db().consommer_etat_oauth(
        state, fournisseur, _identite.jeton_session_courant(), exiger_meme_session=_oauth_lier_session()
    )


def _redirect_oauth() -> str:
    return (
        os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "").strip()
        or os.getenv("GITHUB_OAUTH_REDIRECT_URI", "").strip()
        or "http://localhost:8501/"
    )


def _echec_oauth(fournisseur: str, detail: str) -> None:
    journal.warning("Échec OAuth %s : %s", fournisseur, detail)
    _users_db().evenement_securite("oauth_echec", "faible", f"{fournisseur} : {detail}"[:300])
    afficher_erreur(f"La connexion avec {fournisseur} a échoué.", conseil="Recommencez la connexion.")


def _connexion_oauth(user: Dict[str, Any], fournisseur: str) -> None:
    _users_db().evenement_securite(
        "auth_succes", "info", f"Connexion {fournisseur} vérifiée", acteur=user["id"]
    )
    if _appliquer_user(user):
        notifier(f"Connecté avec {fournisseur}.")
    st.rerun()


def _traiter_callback_oauth() -> None:
    """Traite le retour OAuth Google ou GitHub (?code=&state=)."""
    try:
        qp = st.query_params
    except Exception:
        return
    code = qp.get("code")
    state = qp.get("state")
    apple_name = qp.get("apple_name") or ""
    apple_err = qp.get("apple_error")
    if apple_err:
        try:
            del st.query_params["apple_error"]
        except Exception:
            pass
        afficher_erreur("Connexion Apple interrompue.", conseil="Recommencez la connexion.")
        return
    if not code:
        return
    if isinstance(code, list):
        code = code[0]
    if isinstance(state, list):
        state = state[0]
    if isinstance(apple_name, list):
        apple_name = apple_name[0]
    state_s = str(state or "")
    provider = st.session_state.get("oauth_provider") or ""
    if state_s.startswith("ggl."):
        provider = "google"
    elif state_s.startswith("gh."):
        provider = "github"
    elif state_s.startswith("apl."):
        provider = "apple"

    for k in ("code", "state", "apple_name"):
        try:
            del st.query_params[k]
        except Exception:
            pass

    redirect = _redirect_oauth()

    if provider == "apple":
        if not apple_oauth_configure():
            return
        if not _etat_oauth_valide(state_s, "apple"):
            _echec_oauth("Apple", "état invalide ou expiré")
            return
        profile, err = echanger_code_apple(str(code))
        st.session_state.pop("apple_auth_url", None)
        st.session_state.pop("oauth_provider", None)
        if not profile:
            _echec_oauth("Apple", err)
            return
        user = _users_db().upsert_apple(
            profile["apple_id"],
            email=profile.get("email"),
            display_name=str(apple_name or ""),
        )
        _connexion_oauth(user, "Apple")
        return

    if provider == "google":
        if not google_oauth_configure():
            return
        if not _etat_oauth_valide(state_s, "google"):
            _echec_oauth("Google", "état invalide ou expiré")
            return
        profile, err = echanger_code_google(str(code), redirect)
        st.session_state.pop("google_auth_url", None)
        st.session_state.pop("oauth_provider", None)
        if not profile:
            _echec_oauth("Google", err)
            return
        user = _users_db().upsert_google(
            profile["google_id"],
            email=profile.get("email"),
            display_name=profile.get("name") or "",
        )
        _connexion_oauth(user, "Google")
        return

    if provider == "github":
        if not github_oauth_configure():
            return
        if not _etat_oauth_valide(state_s, "github"):
            _echec_oauth("GitHub", "état invalide ou expiré")
            return
        profile, err = echanger_code_github(str(code), redirect)
        st.session_state.pop("github_auth_url", None)
        st.session_state.pop("oauth_provider", None)
        if not profile:
            _echec_oauth("GitHub", err)
            return
        user = _users_db().upsert_github(
            profile["github_id"],
            profile["github_login"],
            email=profile.get("email"),
        )
        _connexion_oauth(user, "GitHub")
        return


def exiger_auth() -> bool:
    _identite.identite_courante()
    _traiter_callback_oauth()
    assurer_session_invite()
    return True


def _nouvel_etat(fournisseur: str, generer) -> str:
    state = generer()
    _users_db().enregistrer_etat_oauth(state, fournisseur, _identite.jeton_session_courant())
    st.session_state.oauth_provider = fournisseur
    return state


def _lancer_github() -> None:
    state = _nouvel_etat("github", nouveau_state_github)
    st.session_state["github_auth_url"] = url_autorisation_github(_redirect_oauth(), state)


def _lancer_google() -> None:
    state = _nouvel_etat("google", nouveau_state_google)
    redirect = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "").strip() or _redirect_oauth()
    st.session_state["google_auth_url"] = url_autorisation_google(redirect, state)


def _lancer_apple() -> None:
    state = _nouvel_etat("apple", nouveau_state_apple)
    st.session_state["apple_auth_url"] = url_autorisation_apple(state)


def _css_modal_auth(*, page_gate: bool = False) -> None:
    """Textes de la fenêtre de connexion ; boutons, champs et fenêtre suivent le thème commun."""
    st.markdown(
        """
        <style>
        .auth-card-title {
            text-align: center;
            font-size: var(--ui-fs-title);
            font-weight: 600;
            color: var(--ui-text);
            margin: 0 0 var(--ui-space-3) 0;
        }
        .auth-sub {
            text-align: center;
            color: var(--ui-text-muted);
            font-size: var(--ui-fs);
            line-height: 1.5;
            margin: 0 auto var(--ui-space-4) auto;
            max-width: 360px;
        }
        .auth-email {
            text-align: center;
            color: var(--ui-text);
            margin: 0 0 var(--ui-space-2) 0;
            overflow-wrap: anywhere;
        }
        .auth-ou-wrap {
            display: flex;
            align-items: center;
            gap: var(--ui-space-3);
            margin: var(--ui-space-4) 0;
            color: var(--ui-text-muted);
            font-size: var(--ui-fs-sm);
        }
        .auth-ou-wrap::before, .auth-ou-wrap::after {
            content: "";
            flex: 1;
            height: 1px;
            background: var(--ui-border);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _contenu_modal_auth(
    *, force: bool = False, show_title: bool = False, key_prefix: str = "modal", inject_css: bool = True
) -> None:
    """Modal centré style ChatGPT (Google / Apple / téléphone + email)."""
    if inject_css:
        _css_modal_auth(page_gate=False)

    uid_mfa = _mfa_en_attente()
    if uid_mfa:
        if show_title:
            st.markdown('<p class="auth-card-title">Vérification en deux étapes</p>', unsafe_allow_html=True)
        _formulaire_mfa(uid_mfa, key_prefix)
        return

    if show_title:
        st.markdown(
            '<p class="auth-card-title">Connectez-vous ou inscrivez-vous</p>',
            unsafe_allow_html=True,
        )

    if force:
        st.caption(
            f"Limite invité atteinte ({quota_pour('guest').requetes_par_jour} prompts/jour). "
            "Connectez-vous pour continuer."
        )

    st.markdown(
        '<p class="auth-sub">Vous recevrez des réponses plus intelligentes et pourrez '
        "charger des fichiers, des images, et bien plus encore.</p>",
        unsafe_allow_html=True,
    )

    # Social — Google puis GitHub (Apple retiré : trop complexe sans compte Developer)
    if google_oauth_configure():
        if st.button(
            "Continuer avec Google",
            use_container_width=True,
            key=f"{key_prefix}_google",
            icon=":material/language:",
        ):
            _lancer_google()
            st.rerun()
        url_g = st.session_state.get("google_auth_url")
        if url_g:
            st.link_button(
                "→ Autoriser sur Google",
                url_g,
                use_container_width=True,
                type="primary",
            )
    else:
        st.button(
            "Continuer avec Google",
            use_container_width=True,
            disabled=True,
            key=f"{key_prefix}_google",
            help="Ajoutez GOOGLE_OAUTH_CLIENT_ID / SECRET dans .env",
            icon=":material/language:",
        )
        st.caption("Google OAuth : ajoutez CLIENT_ID / SECRET dans `.env`.")

    if github_oauth_configure():
        if st.button(
            "Continuer avec GitHub",
            use_container_width=True,
            key=f"{key_prefix}_github",
            icon=":material/code:",
        ):
            _lancer_github()
            st.rerun()
        url = st.session_state.get("github_auth_url")
        if url:
            st.link_button(
                "→ Autoriser sur GitHub",
                url,
                use_container_width=True,
                type="primary",
            )
    else:
        st.button(
            "Continuer avec GitHub",
            use_container_width=True,
            disabled=True,
            key=f"{key_prefix}_github",
            help="Ajoutez GITHUB_OAUTH_CLIENT_ID / SECRET dans .env",
            icon=":material/code:",
        )
        st.caption(
            "GitHub OAuth : crée une OAuth App sur github.com/settings/developers "
            "puis ajoute CLIENT_ID / SECRET dans `.env`."
        )

    st.button(
        "Continuer avec un numéro de téléphone",
        use_container_width=True,
        disabled=True,
        key=f"{key_prefix}_phone",
        help="Bientôt disponible",
        icon=":material/call:",
    )

    st.markdown('<div class="auth-ou-wrap">ou</div>', unsafe_allow_html=True)

    # Formulaires : Entrée dans le champ valide l'étape (sans souris)
    etape = st.session_state.get("auth_email_step", "email")
    if etape == "email":
        with st.form(f"{key_prefix}_form_email", border=False):
            email = st.text_input(
                "Email",
                placeholder="Email address",
                label_visibility="collapsed",
                key=f"{key_prefix}_email",
            )
            continuer = st.form_submit_button(
                "Continuer",
                type="primary",
                use_container_width=True,
                key=f"{key_prefix}_email_go",
            )
        if continuer:
            email = (email or "").strip().lower()
            if "@" not in email:
                afficher_erreur("Entrez une adresse e-mail valide.")
            else:
                st.session_state.auth_pending_email = email
                st.session_state.auth_email_step = "password"
                st.rerun()
    else:
        email = st.session_state.get("auth_pending_email", "")
        st.markdown(
            f'<p class="auth-email"><b>{html.escape(email)}</b></p>',
            unsafe_allow_html=True,
        )
        if st.button("← Changer d'e-mail", key=f"{key_prefix}_back_email"):
            st.session_state.auth_email_step = "email"
            st.rerun()

        # Entrée déclenche le premier bouton du formulaire : « Se connecter »
        with st.form(f"{key_prefix}_form_pwd", border=False):
            password = st.text_input(
                "Mot de passe",
                type="password",
                placeholder="Mot de passe (min. 8 caractères)",
                label_visibility="collapsed",
                key=f"{key_prefix}_pwd",
            )
            c1, c2 = st.columns(2)
            with c1:
                connexion = st.form_submit_button(
                    "Se connecter", use_container_width=True, key=f"{key_prefix}_login"
                )
            with c2:
                inscription = st.form_submit_button(
                    "Créer un compte",
                    type="primary",
                    use_container_width=True,
                    key=f"{key_prefix}_reg",
                )
        if connexion:
            user, msg = _users_db().connecter_email(email, password, origine=_origine_client())
            if user:
                if _appliquer_user(user):
                    notifier(
                        "Connecté en administrateur."
                        if user.get("tier") == "admin"
                        else "Vous êtes connecté."
                    )
                st.rerun()
            else:
                afficher_erreur(msg)
        elif inscription:
            user, msg = _users_db().inscrire_email(email, password)
            if user:
                _appliquer_user(user)
                notifier("Compte créé. Bienvenue !")
                st.rerun()
            else:
                afficher_erreur(msg)


@st.dialog("Connectez-vous ou inscrivez-vous")
def _dialog_auth_modal(force: bool = False) -> None:
    _contenu_modal_auth(force=force, show_title=False, key_prefix="modal")


def formulaire_connexion(key_prefix: str = "auth") -> None:
    """Carte centrée style ChatGPT (page Admin gate)."""
    _css_modal_auth(page_gate=True)
    _, mid, _ = st.columns([1, 1.35, 1])
    with mid:
        _contenu_modal_auth(
            force=False, show_title=True, key_prefix=key_prefix, inject_css=False
        )


def barre_auth_top() -> None:
    """Boutons Se connecter / Inscription — taille identique via st-key-*."""
    u = utilisateur_session()
    tier = (u or {}).get("tier") or "guest"

    if est_compte_connecte():
        left, right = st.columns([5, 1])
        with left:
            if tier == "admin":
                st.caption(f"Admin · {utilisateur_courant()}")
            else:
                st.caption(f"Connecté · {utilisateur_courant()} · {tier}")
        with right:
            if st.button("Déconnexion", key="top_logout", use_container_width=True):
                deconnecter()
                notifier("Vous êtes déconnecté.", "info")
                st.rerun()
        return

    st.markdown(
        """
        <style>
        div.st-key-top_login, div.st-key-top_signup { min-width: 124px; }
        div.st-key-top_login button, div.st-key-top_signup button {
            min-height: var(--ui-btn-h-sm) !important;
            white-space: nowrap !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    _g, b1, b2 = st.columns([8, 1, 1], gap="small")
    with b1:
        if st.button("Se connecter", key="top_login", use_container_width=True):
            st.session_state.show_auth_dialog = True
            st.session_state.auth_email_step = "email"
            st.rerun()
    with b2:
        if st.button("Inscription", key="top_signup", type="primary", use_container_width=True):
            st.session_state.show_auth_dialog = True
            st.session_state.auth_email_step = "email"
            st.rerun()


def afficher_dialog_auth_si_besoin() -> None:
    """Ouvre le modal st.dialog (Inscription / Se connecter / quota)."""
    force = bool(st.session_state.get("force_login"))
    show = bool(st.session_state.get("show_auth_dialog")) or force
    if not show or est_compte_connecte():
        return
    _dialog_auth_modal(force=force)


def barre_compte_sidebar() -> None:
    """Statut compte en haut de sidebar (sans quota ni bouton login)."""
    u = utilisateur_session()
    if not u:
        return
    st.markdown("**Compte**")
    if u.get("tier") == "guest":
        st.caption("Invité")
    else:
        label = u.get("display_name") or u.get("email") or u.get("github_login") or "user"
        st.caption(f"{label} · **{u.get('tier')}**")


def barre_auth_sidebar_bas() -> None:
    """Bouton Se connecter / Déconnexion — tout en bas de la sidebar."""
    u = utilisateur_session()
    if not u:
        return
    st.divider()
    if u.get("tier") == "guest":
        if st.button("Se connecter / S'inscrire", key="sb_login", use_container_width=True):
            st.session_state.show_auth_dialog = True
            st.session_state.auth_email_step = "email"
            st.rerun()
    else:
        if st.button("Se déconnecter", key="btn_logout", use_container_width=True):
            deconnecter()
            notifier("Vous êtes déconnecté.", "info")
            st.rerun()


def consommer_requete(meta: Optional[Dict] = None) -> tuple[bool, str]:
    u = assurer_session_invite()
    ok, msg = _users_db().verifier_quota(u)
    if not ok:
        tier = u.get("tier") or "guest"
        sature = msg == MSG_INVITES_SATURE
        _users_db().evenement_securite(
            "quota_global_invites" if sature else "quota_depasse",
            "moyenne" if sature else "faible",
            f"Requête refusée (rôle : {tier})", acteur=u.get("id") or "",
        )
        if tier == "guest":
            st.session_state.force_login = True
            st.session_state.show_auth_dialog = True
        if tier == "guest" and not sature:
            return (
                False,
                "Limite invité atteinte. Connectez-vous avec votre email ou GitHub pour continuer.",
            )
        return False, msg
    _users_db().enregistrer_usage(u["id"], "ask", meta or {})
    return True, msg
