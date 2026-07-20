"""
Auth AssistDoc — style ChatGPT :
- Accès invité immédiat
- Modal « Connectez-vous ou inscrivez-vous »
- Après quota invité → obligation email / GitHub
- Admin uniquement si compte tier=admin
"""

from __future__ import annotations

import os
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
from app.quotas import quota_pour
from app.utilisateurs_sqlite import UtilisateursSQLite


@st.cache_resource
def users_db() -> UtilisateursSQLite:
    return UtilisateursSQLite()


_users_db = users_db


def utilisateur_session() -> Optional[Dict[str, Any]]:
    uid = st.session_state.get("auth_user_id")
    if not uid:
        return None
    u = _users_db().obtenir(uid)
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


def _appliquer_user(user: Dict[str, Any]) -> None:
    st.session_state.auth_ok = True
    st.session_state.auth_user_id = user["id"]
    st.session_state.auth_user = (
        user.get("email") or user.get("github_login") or user.get("display_name") or "user"
    )
    st.session_state.auth_tier = user.get("tier") or "guest"
    for k in ("force_login", "show_auth_dialog", "auth_email_step", "auth_pending_email"):
        st.session_state.pop(k, None)


def assurer_session_invite() -> Dict[str, Any]:
    u = utilisateur_session()
    if u:
        return u
    user = _users_db().creer_invite("Invité")
    _appliquer_user(user)
    return user


def deconnecter() -> None:
    for k in (
        "auth_ok", "auth_user_id", "auth_user", "auth_tier",
        "github_oauth_state", "google_oauth_state", "apple_oauth_state",
        "oauth_provider",
        "github_auth_url", "google_auth_url", "apple_auth_url",
        "force_login", "show_auth_dialog",
        "auth_email_step", "auth_pending_email",
    ):
        st.session_state.pop(k, None)
    assurer_session_invite()


def _redirect_oauth() -> str:
    return (
        os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "").strip()
        or os.getenv("GITHUB_OAUTH_REDIRECT_URI", "").strip()
        or "http://localhost:8501/"
    )


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
        st.error("Connexion Apple interrompue.")
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
        attendu = st.session_state.get("apple_oauth_state")
        if attendu and state_s and state_s != attendu:
            st.error("État OAuth Apple invalide.")
            return
        profile, err = echanger_code_apple(str(code))
        st.session_state.pop("apple_oauth_state", None)
        st.session_state.pop("apple_auth_url", None)
        st.session_state.pop("oauth_provider", None)
        if not profile:
            st.error(err)
            return
        user = _users_db().upsert_apple(
            profile["apple_id"],
            email=profile.get("email"),
            display_name=str(apple_name or ""),
        )
        _appliquer_user(user)
        st.toast("Connecté avec Apple")
        st.rerun()
        return

    if provider == "google":
        if not google_oauth_configure():
            return
        attendu = st.session_state.get("google_oauth_state")
        if attendu and state_s and state_s != attendu:
            st.error("État OAuth Google invalide.")
            return
        profile, err = echanger_code_google(str(code), redirect)
        st.session_state.pop("google_oauth_state", None)
        st.session_state.pop("google_auth_url", None)
        st.session_state.pop("oauth_provider", None)
        if not profile:
            st.error(err)
            return
        user = _users_db().upsert_google(
            profile["google_id"],
            email=profile.get("email"),
            display_name=profile.get("name") or "",
        )
        _appliquer_user(user)
        st.toast("Connecté avec Google")
        st.rerun()
        return

    if provider == "github":
        if not github_oauth_configure():
            return
        attendu = st.session_state.get("github_oauth_state")
        if attendu and state_s and state_s != attendu:
            st.error("État OAuth GitHub invalide.")
            return
        profile, err = echanger_code_github(str(code), redirect)
        st.session_state.pop("github_oauth_state", None)
        st.session_state.pop("github_auth_url", None)
        st.session_state.pop("oauth_provider", None)
        if not profile:
            st.error(err)
            return
        user = _users_db().upsert_github(
            profile["github_id"],
            profile["github_login"],
            email=profile.get("email"),
        )
        _appliquer_user(user)
        st.toast("Connecté avec GitHub — quota élevé activé")
        st.rerun()
        return


def exiger_auth() -> bool:
    _traiter_callback_oauth()
    assurer_session_invite()
    return True


def _lancer_github() -> None:
    state = nouveau_state_github()
    st.session_state.oauth_provider = "github"
    st.session_state.github_oauth_state = state
    st.session_state["github_auth_url"] = url_autorisation_github(_redirect_oauth(), state)


def _lancer_google() -> None:
    state = nouveau_state_google()
    st.session_state.oauth_provider = "google"
    st.session_state.google_oauth_state = state
    redirect = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "").strip() or _redirect_oauth()
    st.session_state["google_auth_url"] = url_autorisation_google(redirect, state)


def _lancer_apple() -> None:
    state = nouveau_state_apple()
    st.session_state.oauth_provider = "apple"
    st.session_state.apple_oauth_state = state
    st.session_state["apple_auth_url"] = url_autorisation_apple(state)


def _css_modal_auth(*, page_gate: bool = False) -> None:
    """Styles du modal auth — alignés sur ChatGPT."""
    page = ""
    if page_gate:
        page = """
        section.main .stButton > button {
            border-radius: 999px !important;
            min-height: 48px !important;
            font-weight: 500 !important;
            font-size: 0.95rem !important;
            border: 1px solid rgba(255,255,255,0.55) !important;
            background: transparent !important;
            color: #fff !important;
        }
        section.main .stButton > button:hover {
            background: rgba(255,255,255,0.06) !important;
            border-color: #fff !important;
        }
        section.main .stButton > button[kind="primary"] {
            background: #ffffff !important;
            color: #111111 !important;
            border: none !important;
            font-weight: 600 !important;
        }
        section.main .stButton > button[kind="primary"]:hover {
            background: #e8e8e8 !important;
            color: #111 !important;
        }
        section.main .stButton > button:disabled {
            opacity: 0.55 !important;
            border-color: rgba(255,255,255,0.35) !important;
        }
        section.main div[data-baseweb="input"] > div {
            background: #000 !important;
            border-radius: 999px !important;
            border: 1px solid rgba(255,255,255,0.45) !important;
            min-height: 48px !important;
        }
        section.main input { color: #fff !important; }
        """
    st.markdown(
        f"""
        <style>
        div[data-testid="stDialog"] {{
            width: min(420px, 94vw) !important;
        }}
        div[data-testid="stDialog"] > div {{
            padding: 0.75rem 0.35rem 0.5rem 0.35rem !important;
            background: #2f2f2f !important;
        }}
        div[data-testid="stDialog"] h2 {{
            text-align: center !important;
            font-size: 1.35rem !important;
            font-weight: 600 !important;
            letter-spacing: -0.02em;
            margin: 0.15rem 0 0.55rem 0 !important;
            color: #fff !important;
        }}
        .auth-card-title {{
            text-align: center;
            font-size: 1.35rem;
            font-weight: 600;
            color: #fff;
            margin: 0 0 0.65rem 0;
            letter-spacing: -0.02em;
        }}
        .auth-sub {{
            text-align: center;
            color: #ececec;
            font-size: 0.92rem;
            line-height: 1.45;
            margin: 0 auto 1.25rem auto;
            max-width: 340px;
            font-weight: 400;
        }}
        .auth-ou-wrap {{
            display: flex;
            align-items: center;
            gap: 14px;
            margin: 1.05rem 0 1.05rem 0;
            color: #cfcfcf;
            font-size: 0.88rem;
        }}
        .auth-ou-wrap::before, .auth-ou-wrap::after {{
            content: "";
            flex: 1;
            height: 1px;
            background: rgba(255,255,255,0.18);
        }}
        div[data-testid="stDialog"] .stButton > button {{
            border-radius: 999px !important;
            min-height: 48px !important;
            font-weight: 500 !important;
            font-size: 0.95rem !important;
            border: 1px solid rgba(255,255,255,0.55) !important;
            background: transparent !important;
            color: #fff !important;
        }}
        div[data-testid="stDialog"] .stButton > button:hover {{
            background: rgba(255,255,255,0.06) !important;
            border-color: #fff !important;
        }}
        div[data-testid="stDialog"] .stButton > button[kind="primary"] {{
            background: #ffffff !important;
            color: #111111 !important;
            border: none !important;
            font-weight: 600 !important;
        }}
        div[data-testid="stDialog"] .stButton > button[kind="primary"]:hover {{
            background: #e8e8e8 !important;
            color: #111 !important;
        }}
        div[data-testid="stDialog"] .stButton > button:disabled {{
            opacity: 0.55 !important;
            border-color: rgba(255,255,255,0.35) !important;
        }}
        div[data-testid="stDialog"] div[data-baseweb="input"] > div {{
            background: #000 !important;
            border-radius: 999px !important;
            border: 1px solid rgba(255,255,255,0.45) !important;
            min-height: 48px !important;
        }}
        div[data-testid="stDialog"] input {{ color: #fff !important; }}
        {page}
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

    etape = st.session_state.get("auth_email_step", "email")
    if etape == "email":
        email = st.text_input(
            "Email",
            placeholder="Email address",
            label_visibility="collapsed",
            key=f"{key_prefix}_email",
        )
        if st.button(
            "Continuer",
            type="primary",
            use_container_width=True,
            key=f"{key_prefix}_email_go",
        ):
            email = (email or "").strip().lower()
            if "@" not in email:
                st.error("Entrez une adresse e-mail valide.")
            else:
                st.session_state.auth_pending_email = email
                st.session_state.auth_email_step = "password"
                st.rerun()
    else:
        email = st.session_state.get("auth_pending_email", "")
        st.markdown(
            f"<p style='text-align:center;color:#ddd;margin:0 0 0.5rem 0'>"
            f"<b>{email}</b></p>",
            unsafe_allow_html=True,
        )
        if st.button("← Changer d'e-mail", key=f"{key_prefix}_back_email"):
            st.session_state.auth_email_step = "email"
            st.rerun()

        password = st.text_input(
            "Mot de passe",
            type="password",
            placeholder="Mot de passe (min. 6 caractères)",
            label_visibility="collapsed",
            key=f"{key_prefix}_pwd",
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Se connecter", use_container_width=True, key=f"{key_prefix}_login"):
                user, msg = _users_db().connecter_email(email, password)
                if user:
                    _appliquer_user(user)
                    st.toast(
                        "Connecté en administrateur"
                        if user.get("tier") == "admin"
                        else "Connecté — quota email activé"
                    )
                    st.rerun()
                else:
                    st.error(msg)
        with c2:
            if st.button(
                "Créer un compte",
                type="primary",
                use_container_width=True,
                key=f"{key_prefix}_reg",
            ):
                user, msg = _users_db().inscrire_email(email, password)
                if user:
                    _appliquer_user(user)
                    st.toast("Compte créé — bienvenue !")
                    st.rerun()
                else:
                    st.error(msg)


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
                st.rerun()
        return

    # Même largeur / hauteur forcée sur les 2 boutons (classes st-key-*)
    st.markdown(
        """
        <style>
        div.st-key-top_login,
        div.st-key-top_signup {
            width: 124px !important;
        }
        div.st-key-top_login button,
        div.st-key-top_signup button {
            width: 124px !important;
            min-width: 124px !important;
            max-width: 124px !important;
            height: 34px !important;
            min-height: 34px !important;
            max-height: 34px !important;
            padding: 0 10px !important;
            font-size: 13px !important;
            font-weight: 500 !important;
            white-space: nowrap !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            box-sizing: border-box !important;
            border-radius: 8px !important;
        }
        /* Inscription = même boîte, fond bleu */
        div.st-key-top_signup button {
            background: #3d8bfd !important;
            color: #fff !important;
            border: none !important;
        }
        div.st-key-top_signup button:hover {
            background: #2f7ae5 !important;
            color: #fff !important;
        }
        div.st-key-top_login button {
            background: rgba(255,255,255,0.06) !important;
            color: #ececec !important;
            border: 1px solid rgba(255,255,255,0.18) !important;
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
        # secondary volontairement : même chrome que Se connecter, bleu via CSS
        if st.button("Inscription", key="top_signup", use_container_width=True):
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
            st.rerun()


def consommer_requete(meta: Optional[Dict] = None) -> tuple[bool, str]:
    u = assurer_session_invite()
    ok, msg = _users_db().verifier_quota(u)
    if not ok:
        if (u.get("tier") or "guest") == "guest":
            st.session_state.force_login = True
            st.session_state.show_auth_dialog = True
            return (
                False,
                "Limite invité atteinte. Connectez-vous avec votre email ou GitHub pour continuer.",
            )
        return False, msg
    _users_db().enregistrer_usage(u["id"], "ask", meta or {})
    return True, msg
