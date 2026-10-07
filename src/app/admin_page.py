"""
Dashboard Admin AssistDoc — modules séparés, feedbacks, corpus, paramètres IA.
"""

from __future__ import annotations

import html as html_lib
import importlib
import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]  # .../Assistant-Intelligent-Doc
sys.path.insert(0, str(ROOT / "src"))

from app import admin_corpus
from app import runtime_config
import app.auth_basique as _auth_basique

# Streamlit garde souvent l'ancien module en cache après hot-reload
importlib.reload(_auth_basique)

deconnecter = _auth_basique.deconnecter
est_admin_session = _auth_basique.est_admin_session
est_compte_connecte = _auth_basique.est_compte_connecte
exiger_auth = _auth_basique.exiger_auth
formulaire_connexion = _auth_basique.formulaire_connexion
tier_courant = _auth_basique.tier_courant
users_db = _auth_basique.users_db
utilisateur_courant = _auth_basique.utilisateur_courant
utilisateur_session = _auth_basique.utilisateur_session

from app.historique_sqlite import HistoriqueSQLite
from app.quotas import QUOTAS


def _aller_accueil() -> None:
    for cible in ("accueil.py", "Accueil"):
        try:
            st.switch_page(cible)
            return
        except Exception:
            continue
    st.rerun()


def _exiger_admin_page() -> None:
    """Garde d'accès — refus si non-admin (ne repose pas seulement sur le menu)."""
    exiger_auth()
    if est_admin_session():
        return
    st.error("Accès refusé — réservé aux administrateurs.")
    if est_compte_connecte():
        st.info(
            f"Compte actuel : **{utilisateur_courant()}** "
            f"(rôle : `{tier_courant()}`). "
            "Déconnectez-vous puis reconnectez-vous avec un compte administrateur."
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Retour à l'Accueil", key="admin_denied_home", use_container_width=True):
                _aller_accueil()
        with c2:
            if st.button("Se déconnecter", key="admin_denied_logout", use_container_width=True):
                deconnecter()
                _aller_accueil()
    else:
        st.caption("Connectez-vous avec l'adresse e-mail administrateur.")
        formulaire_connexion(key_prefix="admin_gate")
    st.stop()


def _esc(valeur) -> str:
    return html_lib.escape(str(valeur if valeur is not None else ""))


st.set_page_config(page_title="AssistDoc Admin", page_icon="🛡", layout="wide")
_logo_admin = ROOT / "assets" / "assistdoc_logo.png"
if _logo_admin.exists():
    st.logo(str(_logo_admin), size="small")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;650&family=IBM+Plex+Mono:wght@400;500&display=swap');

    :root {
        --ad-bg: #0b0f19;
        --ad-panel: #111827;
        --ad-elev: #161f2e;
        --ad-border: rgba(148, 163, 184, 0.14);
        --ad-text: #e8eef7;
        --ad-muted: #93a4bd;
        --ad-dim: #6b7c95;
        --ad-blue: #3b82f6;
        --ad-blue-soft: rgba(59, 130, 246, 0.14);
        --ad-green: #34d399;
        --ad-amber: #f59e0b;
        --ad-red: #f87171;
        --ad-violet: #a78bfa;
    }

    .stApp, [data-testid="stAppViewContainer"],
    [data-testid="stAppViewContainer"] > .main {
        background: var(--ad-bg) !important;
        color: var(--ad-text);
        font-family: 'IBM Plex Sans', system-ui, sans-serif;
    }
    .block-container {
        padding: 1.1rem 1.6rem 2.5rem !important;
        max-width: 1280px !important;
    }
    #MainMenu, footer, header { visibility: hidden; }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background: #0a0e17 !important;
        border-right: 1px solid var(--ad-border) !important;
    }
    [data-testid="stSidebar"] > div:first-child {
        padding: 0 12px 16px !important;
    }
    [data-testid="stSidebarHeader"] {
        padding: 10px 8px 6px !important;
        display: flex !important;
        align-items: center !important;
        gap: 10px !important;
    }
    [data-testid="stSidebarHeader"] [data-testid="stLogo"] {
        display: flex !important;
        align-items: center !important;
        gap: 10px !important;
    }
    [data-testid="stSidebarHeader"] [data-testid="stLogo"]::after {
        content: "AssistDoc";
        font-size: 15px;
        font-weight: 600;
        color: var(--ad-text);
        letter-spacing: -0.2px;
        white-space: nowrap;
    }
    [data-testid="stSidebarHeader"] img {
        width: 32px !important;
        height: 32px !important;
        border-radius: 9px !important;
        object-fit: cover !important;
    }
    section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
        display: flex !important;
        flex-direction: column !important;
        min-height: calc(100vh - 5rem) !important;
        padding-top: 0 !important;
    }
    .admin-sb-foot {
        margin-top: auto;
        padding-top: 1rem;
        border-top: 1px solid var(--ad-border);
    }
    .admin-sb-email {
        font-size: 12px;
        color: var(--ad-muted);
        margin-bottom: 10px;
        word-break: break-all;
        line-height: 1.35;
    }
    section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
        background: var(--ad-blue) !important;
        color: #fff !important;
        border: none !important;
        border-radius: 10px !important;
        font-weight: 550 !important;
        min-height: 40px !important;
    }
    section[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
        background: #2563eb !important;
    }

    /* ── Hero ── */
    .admin-hero {
        background:
            radial-gradient(ellipse 80% 120% at 0% 0%, rgba(59,130,246,0.18), transparent 55%),
            linear-gradient(135deg, #121a2a 0%, #152238 48%, #0f1a2c 100%);
        border: 1px solid var(--ad-border);
        border-radius: 14px;
        padding: 1.15rem 1.35rem;
        margin-bottom: 1rem;
        display: flex;
        align-items: flex-start;
        gap: 14px;
    }
    .admin-hero-icon {
        width: 42px; height: 42px; border-radius: 11px;
        background: var(--ad-blue-soft);
        border: 1px solid rgba(59,130,246,0.35);
        display: flex; align-items: center; justify-content: center;
        flex-shrink: 0;
        color: #93c5fd;
        font-size: 18px;
    }
    .admin-hero h1 {
        margin: 0 0 0.25rem 0;
        font-size: 1.35rem;
        font-weight: 650;
        letter-spacing: -0.03em;
        color: var(--ad-text);
    }
    .admin-hero p {
        margin: 0;
        color: var(--ad-muted);
        font-size: 0.9rem;
        line-height: 1.45;
    }
    .admin-hero b { color: #c7d7f0; font-weight: 600; }

    /* ── Metric cards ── */
    .kpi-row {
        display: grid;
        grid-template-columns: repeat(5, minmax(0, 1fr));
        gap: 12px;
        margin: 0 0 1.1rem 0;
    }
    .kpi {
        background: var(--ad-panel);
        border: 1px solid var(--ad-border);
        border-radius: 12px;
        padding: 14px 14px 12px;
        min-height: 86px;
    }
    .kpi-top {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 10px;
    }
    .kpi-label {
        font-size: 11px;
        font-weight: 550;
        color: var(--ad-dim);
        letter-spacing: 0.02em;
        text-transform: uppercase;
    }
    .kpi-ico {
        width: 28px; height: 28px; border-radius: 8px;
        display: flex; align-items: center; justify-content: center;
        font-size: 13px; font-weight: 700;
    }
    .kpi-ico.blue { background: rgba(59,130,246,0.15); color: #60a5fa; }
    .kpi-ico.green { background: rgba(52,211,153,0.14); color: #34d399; }
    .kpi-ico.violet { background: rgba(167,139,250,0.14); color: #a78bfa; }
    .kpi-ico.amber { background: rgba(245,158,11,0.14); color: #fbbf24; }
    .kpi-ico.red { background: rgba(248,113,113,0.14); color: #f87171; }
    .kpi-val {
        font-size: 1.55rem;
        font-weight: 650;
        letter-spacing: -0.03em;
        color: var(--ad-text);
        line-height: 1;
    }

    /* ── Section headers ── */
    .mod-head {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 12px;
        margin: 0.35rem 0 0.85rem 0;
    }
    .mod-head h2 {
        margin: 0;
        font-size: 1.15rem;
        font-weight: 650;
        letter-spacing: -0.02em;
        color: var(--ad-text);
    }
    .mod-head p {
        margin: 0.2rem 0 0 0;
        font-size: 0.82rem;
        color: var(--ad-dim);
    }

    /* ── Panels ── */
    .panel {
        background: var(--ad-panel);
        border: 1px solid var(--ad-border);
        border-radius: 12px;
        padding: 14px 16px;
        margin-bottom: 12px;
    }
    .panel-title {
        font-size: 11px;
        font-weight: 600;
        color: var(--ad-dim);
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 10px;
    }
    .code-block {
        font-family: 'IBM Plex Mono', ui-monospace, monospace;
        font-size: 12.5px;
        line-height: 1.55;
        color: #cbd5e1;
        background: #0a101c;
        border: 1px solid var(--ad-border);
        border-radius: 10px;
        padding: 12px 14px;
        white-space: pre-wrap;
    }
    .code-key { color: #7dd3fc; }
    .code-num { color: #86efac; }

    .quota-list { display: flex; flex-direction: column; gap: 8px; }
    .quota-row {
        display: flex; align-items: center; gap: 10px;
        font-size: 13px; color: var(--ad-muted);
    }
    .pill {
        display: inline-flex; align-items: center;
        border-radius: 999px;
        padding: 2px 10px;
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.01em;
        border: 1px solid transparent;
    }
    .pill-guest { background: rgba(245,158,11,0.12); color: #fbbf24; border-color: rgba(245,158,11,0.25); }
    .pill-email { background: rgba(59,130,246,0.12); color: #60a5fa; border-color: rgba(59,130,246,0.25); }
    .pill-github { background: rgba(148,163,184,0.12); color: #cbd5e1; border-color: rgba(148,163,184,0.25); }
    .pill-google { background: rgba(52,211,153,0.12); color: #34d399; border-color: rgba(52,211,153,0.25); }
    .pill-apple { background: rgba(226,232,240,0.08); color: #e2e8f0; border-color: rgba(226,232,240,0.18); }
    .pill-admin { background: rgba(52,211,153,0.16); color: #6ee7b7; border-color: rgba(52,211,153,0.3); }
    .pill-sus { background: rgba(248,113,113,0.14); color: #fca5a5; border-color: rgba(248,113,113,0.28); }

    /* ── User rows ── */
    .user-row {
        background: var(--ad-panel);
        border: 1px solid var(--ad-border);
        border-radius: 12px;
        padding: 12px 14px;
        margin-bottom: 8px;
    }
    .user-name { font-weight: 600; color: var(--ad-text); font-size: 0.95rem; }
    .user-mail { color: #34d399; font-size: 0.82rem; margin-top: 2px; }
    .user-meta { color: var(--ad-dim); font-size: 0.78rem; margin-top: 4px; }

    .fb-pos { color: #34d399; font-weight: 600; }
    .fb-neg { color: #f87171; font-weight: 600; }
    .fb-sig { color: #fbbf24; font-weight: 600; }

    /* ── Streamlit widgets ── */
    div[data-testid="stTabs"] button[data-baseweb="tab"] {
        font-family: 'IBM Plex Sans', system-ui, sans-serif !important;
        font-size: 0.9rem !important;
        color: var(--ad-muted) !important;
        padding-top: 0.55rem !important;
        padding-bottom: 0.55rem !important;
        gap: 0.4rem !important;
    }
    div[data-testid="stTabs"] button[data-baseweb="tab"] span {
        display: inline-flex !important;
        align-items: center !important;
        gap: 0.4rem !important;
    }
    div[data-testid="stTabs"] button[aria-selected="true"] {
        color: var(--ad-blue) !important;
        font-weight: 600 !important;
    }
    div[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
        background-color: var(--ad-blue) !important;
    }
    div[data-testid="stMetric"] {
        background: var(--ad-panel);
        border: 1px solid var(--ad-border);
        border-radius: 12px;
        padding: 10px 12px;
    }
    div[data-testid="stMetric"] label { color: var(--ad-dim) !important; }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        color: var(--ad-text) !important;
        font-weight: 650 !important;
    }
    .stButton > button {
        border-radius: 10px !important;
        font-family: 'IBM Plex Sans', system-ui, sans-serif !important;
    }
    .stButton > button[kind="primary"] {
        background: var(--ad-blue) !important;
        border: none !important;
    }
    .stButton > button[kind="secondary"] {
        background: var(--ad-elev) !important;
        border: 1px solid var(--ad-border) !important;
        color: var(--ad-text) !important;
    }
    [data-testid="stExpander"] {
        background: var(--ad-panel);
        border: 1px solid var(--ad-border);
        border-radius: 12px;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: var(--ad-panel) !important;
        border: 1px solid var(--ad-border) !important;
        border-radius: 12px !important;
    }
    .stSelectbox label, .stTextInput label, .stNumberInput label,
    .stSlider label, .stTextArea label {
        color: var(--ad-muted) !important;
        font-size: 0.85rem !important;
    }
    @media (max-width: 1100px) {
        .kpi-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Sécurité : ne pas se contenter du menu — refus si non-admin
_exiger_admin_page()

admin = utilisateur_session()
db = users_db()
histo = HistoriqueSQLite()
admin_label = admin.get("email") or admin.get("display_name") or "admin"


def _entete_module(titre: str, caption: str, module_key: str) -> None:
    """Titre + bouton Actualiser pour recharger les données du module."""
    c1, c2 = st.columns([5, 1])
    with c1:
        st.markdown(
            f"""
            <div class="mod-head">
              <div>
                <h2>{_esc(titre)}</h2>
                <p>{_esc(caption)}</p>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        if st.button(
            "Actualiser",
            key=f"admin_refresh_{module_key}",
            use_container_width=True,
            help="Recharger ce module",
        ):
            st.rerun()


def _pill_class(tier: str) -> str:
    t = (tier or "guest").lower()
    return {
        "guest": "pill-guest",
        "email": "pill-email",
        "github": "pill-github",
        "google": "pill-google",
        "apple": "pill-apple",
        "admin": "pill-admin",
    }.get(t, "pill-guest")


with st.sidebar:
    # Logo AssistDoc via st.logo() dans main.py (tout en haut)
    st.markdown('<div class="admin-sb-foot">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="admin-sb-email">Connecté · {_esc(admin_label)}</div>',
        unsafe_allow_html=True,
    )
    if st.button(
        "Se déconnecter",
        key="admin_logout",
        use_container_width=True,
        type="primary",
        help="Quitter l'admin et revenir en mode invité",
    ):
        deconnecter()
        st.toast("Déconnecté — mode invité")
        _aller_accueil()
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown(
    f"""
    <div class="admin-hero">
      <div class="admin-hero-icon">🛡</div>
      <div>
        <h1>AssistDoc Admin</h1>
        <p>Connecté : <b>{_esc(admin_label)}</b>
        · Pilotage users, feedbacks, corpus &amp; paramètres IA</p>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Vue d'ensemble ──────────────────────────────────────────────
stats = db.stats_globales()
fb_stats = histo.stats_feedback()
st.markdown(
    f"""
    <div class="kpi-row">
      <div class="kpi">
        <div class="kpi-top"><span class="kpi-label">Utilisateurs</span>
        <span class="kpi-ico blue">U</span></div>
        <div class="kpi-val">{_esc(stats["users_total"])}</div>
      </div>
      <div class="kpi">
        <div class="kpi-top"><span class="kpi-label">Actifs 24h</span>
        <span class="kpi-ico green">A</span></div>
        <div class="kpi-val">{_esc(stats["users_actifs_24h"])}</div>
      </div>
      <div class="kpi">
        <div class="kpi-top"><span class="kpi-label">Requêtes / 24h</span>
        <span class="kpi-ico violet">R</span></div>
        <div class="kpi-val">{_esc(stats["asks_24h"])}</div>
      </div>
      <div class="kpi">
        <div class="kpi-top"><span class="kpi-label">Feedbacks</span>
        <span class="kpi-ico amber">+</span></div>
        <div class="kpi-val">{_esc(fb_stats["positifs"])}</div>
      </div>
      <div class="kpi">
        <div class="kpi-top"><span class="kpi-label">Signalements</span>
        <span class="kpi-ico red">!</span></div>
        <div class="kpi-val">{_esc(fb_stats["negatifs"])} / {_esc(fb_stats["signalements"])}</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

modules = st.tabs(
    [
        ":material/person: Utilisateurs",
        ":material/chat_bubble: Feedbacks",
        ":material/bolt: Activité",
        ":material/database: Corpus",
        ":material/settings: Paramètres IA",
        ":material/description: Audit",
    ]
)

# ── Module Utilisateurs ─────────────────────────────────────────
with modules[0]:
    _entete_module(
        "Gestion des comptes",
        "Invité / email / GitHub / admin — suspension et changement de tier.",
        "users",
    )
    col_a, col_b = st.columns([1.35, 1])
    with col_a:
        lignes = []
        for tier, n in sorted((stats.get("par_tier") or {}).items()):
            lignes.append(
                f'  <span class="code-key">"{_esc(tier)}"</span>: '
                f'<span class="code-num">{_esc(n)}</span>'
            )
        bloc = "{\n" + ",\n".join(lignes) + "\n}" if lignes else "{}"
        st.markdown(
            f"""
            <div class="panel">
              <div class="panel-title">Répartition</div>
              <div class="code-block">{bloc}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_b:
        quotas_html = ['<div class="panel"><div class="panel-title">Quotas</div><div class="quota-list">']
        for tier, q in QUOTAS.items():
            lim = "∞" if q.requetes_par_jour < 0 else f"{q.requetes_par_jour} req/j"
            quotas_html.append(
                f'<div class="quota-row"><span class="pill {_pill_class(tier)}">'
                f'{_esc(tier)}</span><span>→ {_esc(lim)}</span></div>'
            )
        quotas_html.append("</div></div>")
        st.markdown("".join(quotas_html), unsafe_allow_html=True)

    users = db.lister_users(300)
    st.caption(f"{len(users)} utilisateur(s)")
    for u in users:
        ident = u.get("email") or u.get("github_login") or u["id"][:8]
        nom = u.get("display_name") or "—"
        vu = (u.get("derniere_connexion") or "")[:16] or "—"
        reqs = db.compter_requetes_jour(u["id"])
        sus_badge = (
            ' <span class="pill pill-sus">suspendu</span>' if u.get("suspended") else ""
        )
        with st.container(border=False):
            st.markdown(
                f"""
                <div class="user-row">
                  <div class="user-name">{_esc(nom)}{sus_badge}</div>
                  <div class="user-mail">{_esc(ident)}</div>
                  <div class="user-meta">
                    <span class="pill {_pill_class(u.get('tier'))}">tier {_esc(u.get('tier'))}</span>
                    &nbsp;· vu {_esc(vu)} · {_esc(reqs)} req aujourd'hui
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            cols = st.columns([2, 1, 1])
            with cols[0]:
                nouveau = st.selectbox(
                    "Tier",
                    ["guest", "email", "github", "google", "apple", "admin"],
                    index=["guest", "email", "github", "google", "apple", "admin"].index(
                        u.get("tier")
                        if u.get("tier")
                        in {"guest", "email", "github", "google", "apple", "admin"}
                        else "guest"
                    ),
                    key=f"tier_{u['id']}",
                    label_visibility="collapsed",
                )
            with cols[1]:
                if st.button("Appliquer", key=f"apply_tier_{u['id']}", use_container_width=True):
                    db.set_tier(u["id"], nouveau, admin_id=admin["id"])
                    st.toast(f"Tier → {nouveau}")
                    st.rerun()
            with cols[2]:
                if u.get("suspended"):
                    if st.button("Réactiver", key=f"unsus_{u['id']}", use_container_width=True):
                        db.suspendre(u["id"], False, admin_id=admin["id"])
                        st.rerun()
                else:
                    if st.button("Suspendre", key=f"sus_{u['id']}", use_container_width=True):
                        db.suspendre(u["id"], True, admin_id=admin["id"])
                        st.rerun()

# ── Module Feedbacks ────────────────────────────────────────────
with modules[1]:
    _entete_module(
        "Avis utilisateurs",
        "Votes et signalements enregistrés depuis le chat.",
        "feedbacks",
    )
    fb_stats = histo.stats_feedback()
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Total", fb_stats["total"])
    f2.metric("Positifs", fb_stats["positifs"])
    f3.metric("Négatifs", fb_stats["negatifs"])
    f4.metric("Signalements", fb_stats["signalements"])

    filtre = st.selectbox(
        "Filtrer",
        ["Tous", "Positifs", "Négatifs", "Signalements"],
        key="fb_filtre",
    )
    try:
        feedbacks = histo.lister_feedback(150)
    except Exception as exc:
        st.error(f"Impossible de charger les feedbacks : {exc}")
        st.caption(
            "Arrêtez Streamlit (Ctrl+C) puis relancez `streamlit run src/app/main.py`."
        )
        feedbacks = []
    if filtre == "Positifs":
        feedbacks = [f for f in feedbacks if f.get("label") == "positif"]
    elif filtre == "Négatifs":
        feedbacks = [f for f in feedbacks if f.get("label") == "negatif"]
    elif filtre == "Signalements":
        feedbacks = [
            f for f in feedbacks if (f.get("commentaire") or "").startswith("[signalement]")
        ]

    if not feedbacks:
        st.info("Aucun feedback pour ce filtre.")
    for fb in feedbacks:
        note = int(fb.get("note") or 0)
        if note > 0:
            badge = '<span class="fb-pos">Positif</span>'
        elif (fb.get("commentaire") or "").startswith("[signalement]"):
            badge = '<span class="fb-sig">Signalement</span>'
        else:
            badge = '<span class="fb-neg">Négatif</span>'
        user = (fb.get("user_label") or "invité").strip()
        mode = (fb.get("mode") or "").strip()
        with st.container(border=True):
            st.markdown(
                f"{badge} · `{str(fb.get('cree_le') or '')[:19]}` · "
                f"**{_esc(user)}**"
                + (f" · `{_esc(mode)}`" if mode else "")
                + f" · conv **{_esc((fb.get('titre') or fb.get('conversation_id') or '')[:40])}**",
                unsafe_allow_html=True,
            )
            if fb.get("question"):
                st.markdown(f"**Q :** {_esc(fb['question'][:300])}")
            if fb.get("extrait_court"):
                st.markdown(f"> {_esc(fb['extrait_court'])}")
            elif not fb.get("question"):
                st.caption("(Ancien feedback sans snapshot.)")
            if fb.get("commentaire"):
                st.caption(f"Commentaire : {_esc(fb['commentaire'])}")

# ── Module Activité ─────────────────────────────────────────────
with modules[2]:
    _entete_module("Activité récente", "Requêtes et journal RAG.", "activite")
    for e in db.usage_recent(80):
        st.markdown(
            f"`{str(e.get('cree_le') or '')[:19]}` · **{_esc(e.get('kind'))}** · "
            f"{_esc(e.get('display_name') or e.get('email') or e.get('user_id', '')[:8])} "
            f"({_esc(e.get('tier'))})"
        )
        meta = e.get("meta_json") or "{}"
        try:
            m = json.loads(meta)
            if m.get("question"):
                st.caption(f"Q : {_esc(m['question'][:120])}")
        except json.JSONDecodeError:
            pass

    journal = ROOT / "logs" / "interactions.jsonl"
    if journal.exists():
        with st.expander("Journal RAG (interactions.jsonl)", expanded=False):
            for line in journal.read_text(encoding="utf-8", errors="replace").splitlines()[-30:]:
                try:
                    obj = json.loads(line)
                    st.caption(
                        f"{obj.get('mode')} · rag={obj.get('score_rag')} · "
                        f"fb={obj.get('feedback')} · {(obj.get('question') or '')[:70]}"
                    )
                except json.JSONDecodeError:
                    continue

# ── Module Corpus ───────────────────────────────────────────────
with modules[3]:
    _entete_module(
        "Corpus & indexation",
        "Ajouter, supprimer ou ré-indexer les documents Qdrant.",
        "corpus",
    )

    try:
        stats_c = admin_corpus.stats_corpus()
        c1, c2, c3 = st.columns(3)
        c1.metric("Chunks locaux", stats_c.get("nombre_chunks", 0))
        c2.metric("Dépôts", stats_c.get("nombre_repos", 0))
        qd = stats_c.get("qdrant") or {}
        c3.metric("Points Qdrant", qd.get("points", "?"))
        if qd.get("erreur"):
            st.warning(f"Qdrant : {qd['erreur']}")
        else:
            st.caption(f"Collection : `{qd.get('collection', '?')}`")
        if stats_c.get("par_langage"):
            with st.expander("Chunks par langage"):
                st.json(stats_c["par_langage"])
    except Exception as exc:
        st.warning(str(exc))

    st.markdown("#### Ajouter un document")
    with st.form("admin_add_doc"):
        r1, r2 = st.columns(2)
        with r1:
            repo = st.text_input("Identifiant (owner/repo)", value="manuel/upload")
        with r2:
            src = st.text_input("Fichier source", value="notes.md")
        texte = st.text_area("Contenu Markdown / texte", height=160)
        if st.form_submit_button("Indexer maintenant", type="primary"):
            ok, msg = admin_corpus.ajouter_document_texte(texte, repo, src)
            db.audit(admin["id"], "corpus_add", msg)
            if ok:
                st.success(msg)
            else:
                st.error(msg)

    st.markdown("#### Supprimer un dépôt")
    try:
        repos = admin_corpus.lister_repos_qdrant(120)
    except Exception as exc:
        repos = []
        st.caption(str(exc))
    labels = [f"{r['nom_complet']} ({r['nb_points']})" for r in repos]
    if not labels:
        labels = admin_corpus.lister_repos_indexes()[:120]
    if labels:
        choix = st.selectbox("Dépôt", labels, key="corpus_del_sel")
        repo_del = choix.split(" (")[0] if " (" in choix else choix
        if st.button("Supprimer de Qdrant", type="secondary"):
            ok, msg = admin_corpus.supprimer_repo(repo_del)
            db.audit(admin["id"], "corpus_delete", msg)
            if ok:
                st.toast(msg)
            else:
                st.error(msg)
            st.rerun()
    else:
        st.info("Aucun dépôt listé.")

    st.markdown("#### Ré-indexation")
    recreer = st.checkbox("Recréer la collection (destructif)", key="admin_recreer")
    if st.button("Lancer ré-indexation embeddings", type="primary"):
        with st.spinner("Ré-indexation en cours…"):
            ok, msg = admin_corpus.reindexer_collection(recreer=recreer)
        db.audit(admin["id"], "corpus_reindex", msg)
        if ok:
            st.success(msg)
        else:
            st.error(msg)

# ── Module Paramètres IA ────────────────────────────────────────
with modules[4]:
    _entete_module(
        "Configuration de l'IA",
        "Valeurs dans data/app/runtime_ia.json "
        "(redémarrer Streamlit pour recharger les modules déjà en mémoire).",
        "params_ia",
    )
    cfg = runtime_config.charger()
    with st.form("form_runtime_ia"):
        st.markdown("##### Modèle & génération")
        modele = st.text_input("Modèle LLM", value=str(cfg.get("LLM_MODEL", "")))
        vision = st.text_input(
            "Modèle vision", value=str(cfg.get("GROQ_VISION_MODEL", ""))
        )
        c1, c2 = st.columns(2)
        with c1:
            temp = st.slider(
                "Température",
                0.0,
                1.5,
                float(cfg.get("LLM_TEMPERATURE", 0.3)),
                0.05,
            )
            top_p = st.slider(
                "Top P", 0.0, 1.0, float(cfg.get("LLM_TOP_P", 0.95)), 0.05
            )
        with c2:
            max_tok = st.number_input(
                "Max tokens",
                min_value=256,
                max_value=8000,
                value=int(cfg.get("MAX_TOKENS", 3000)),
                step=100,
            )
            freq_p = st.slider(
                "Frequency penalty",
                0.0,
                2.0,
                float(cfg.get("LLM_FREQUENCY_PENALTY", 0.2)),
                0.05,
            )
        presence = st.slider(
            "Presence penalty",
            0.0,
            2.0,
            float(cfg.get("LLM_PRESENCE_PENALTY", 0.0)),
            0.05,
        )
        web_off = st.toggle(
            "Désactiver la recherche web",
            value=str(cfg.get("DESACTIVER_WEB_SEARCH", "false")).lower()
            in {"1", "true", "yes"},
        )

        st.markdown("##### Quotas (requêtes / jour)")
        q1, q2, q3 = st.columns(3)
        with q1:
            q_guest = st.number_input(
                "Invité", min_value=1, max_value=500, value=int(cfg.get("QUOTA_GUEST_REQ", 12))
            )
        with q2:
            q_email = st.number_input(
                "Email", min_value=1, max_value=2000, value=int(cfg.get("QUOTA_EMAIL_REQ", 80))
            )
        with q3:
            q_gh = st.number_input(
                "GitHub", min_value=1, max_value=5000, value=int(cfg.get("QUOTA_GITHUB_REQ", 200))
            )

        if st.form_submit_button("Enregistrer les paramètres", type="primary"):
            runtime_config.sauvegarder(
                {
                    "LLM_MODEL": modele.strip(),
                    "GROQ_VISION_MODEL": vision.strip(),
                    "LLM_TEMPERATURE": temp,
                    "LLM_TOP_P": top_p,
                    "MAX_TOKENS": int(max_tok),
                    "LLM_FREQUENCY_PENALTY": freq_p,
                    "LLM_PRESENCE_PENALTY": presence,
                    "DESACTIVER_WEB_SEARCH": "true" if web_off else "false",
                    "QUOTA_GUEST_REQ": int(q_guest),
                    "QUOTA_EMAIL_REQ": int(q_email),
                    "QUOTA_GITHUB_REQ": int(q_gh),
                }
            )
            db.audit(admin["id"], "runtime_config", "Paramètres IA mis à jour")
            st.success(
                "Paramètres enregistrés. Redémarrez Streamlit pour appliquer "
                "aux modules déjà chargés."
            )
            st.rerun()

    st.json(runtime_config.charger())

# ── Module Audit ────────────────────────────────────────────────
with modules[5]:
    _entete_module("Journal des actions admin", "Historique des actions admin.", "audit")
    for a in db.lister_audit(80):
        st.markdown(
            f"`{str(a.get('cree_le') or '')[:19]}` · **{_esc(a.get('action'))}** · "
            f"{_esc(a.get('details'))}"
        )
