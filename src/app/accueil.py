"""
Interface AssistDoc — Chat conversationnel avec upload de fichiers
ISI KOMUNIK · Master IAGE
"""

import sys, os, time, uuid, re, importlib
from datetime import date
from pathlib import Path
from typing import Optional
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from generation import generateur_reponse as _generateur_reponse

importlib.reload(_generateur_reponse)
GenerateurReponse = _generateur_reponse.GenerateurReponse
demande_code_explicite = _generateur_reponse.demande_code_explicite
demande_generation_image = _generateur_reponse.demande_generation_image
est_demande_projet = _generateur_reponse.est_demande_projet
est_cahier_des_charges = _generateur_reponse.est_cahier_des_charges
est_salutation = _generateur_reponse.est_salutation
# Orchestrateur / sentence-transformers : import différé dans charger() (~25s)
from app.gestionnaire_fichiers import (
    fichiers_de_rappel,
    formater_pour_prompt,
    necessite_preparation,
    taille_lisible,
    traiter_fichier,
    transcrire_audio,
)
from app.historique_sqlite import HistoriqueSQLite
from app.favoris_sqlite import FavorisSQLite
from app.identite import identite_session
from app.ui_composants import (
    afficher_avertissement,
    afficher_erreur,
    afficher_flux,
    annuler_confirmation,
    confirmation_en_attente,
    demander_confirmation,
    erreur_confirmation,
    executer_confirmation,
    message_erreur,
    notifier,
    pied_dialogue,
    texte_dialogue,
)
from app.edition_conversation import (
    appliquer_edition_contenu,
    appliquer_edition_prompt,
    edition_autorisee,
    resync_historique_llm,
)
from securite.acces import VueProprietaire
from app.auth_basique import (
    afficher_dialog_auth_si_besoin,
    barre_compte_sidebar,
    consommer_requete,
    deconnecter,
    est_admin_session,
    est_compte_connecte,
    exiger_auth,
    ouvrir_connexion,
    users_db as _users_db_auth,
    utilisateur_courant,
    utilisateur_session,
)
from securite.injection import LIBELLES as _LIBELLES_INJECTION, detecter as detecter_injection
from core.nettoyage_reponse import nettoyer_reponse
from app import export_conversation as _export_conversation

importlib.reload(_export_conversation)
export_markdown = _export_conversation.export_markdown
export_pdf = _export_conversation.export_pdf
from config import (
    DATE_COLLECTE_GITHUB,
    FICHIERS_MAX_PAR_MESSAGE,
    UPLOAD_EXTENSIONS_OK,
    UPLOAD_FORMATS_REFUSES,
    UPLOAD_MAX_BYTES,
)
from retrieval.citations import citation_courte, determiner_provenance, enrichir_document
from web.ressources import sources_web_reelles
import streamlit.components.v1 as components
import html as html_lib

_LOGO_FILE = ROOT / "assets" / "assistdoc_logo.png"
st.set_page_config(
    page_title="AssistDoc",
    page_icon=str(_LOGO_FILE) if _LOGO_FILE.exists() else "⬡",
    layout="wide",
    initial_sidebar_state="expanded",
)
# Logo tout en haut de la sidebar (au-dessus d'Accueil / Admin)
if _LOGO_FILE.exists():
    st.logo(str(_LOGO_FILE), size="small")

# Session invité automatique (style ChatGPT) — pas d'écran bloquant
exiger_auth()

# Persistance SQLite (connexions partagées ; chaque accès est lié au propriétaire courant)
@st.cache_resource
def _db_base() -> HistoriqueSQLite:
    return HistoriqueSQLite()


@st.cache_resource
def _favoris_base() -> FavorisSQLite:
    return FavorisSQLite()


def _owner() -> str:
    return identite_session().user_id


def _db() -> VueProprietaire:
    return VueProprietaire(_db_base(), _owner())


def _favoris() -> VueProprietaire:
    return VueProprietaire(_favoris_base(), _owner())


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,500;8..60,600&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    /* Full Black : surfaces principales ; les composants gardent leurs teintes */
    --bg: #000000;
    --bg-side: #050505;
    --bg-elev: #1a1a1a;
    --bg-input: #1a1a1a;
    --border: #2a2a2a;
    --text: #f5f4ef;
    --text-muted: #c4c2b8;
    --text-dim: #9a978c;
    --accent: #5b9fd4;
    --code-bg: #121820;
    --code-fg: #a8d4f0;
}

*, *::before, *::after { box-sizing: border-box; }
html, body, [data-testid="stAppViewContainer"], .stApp {
    background: var(--bg) !important;
    color: var(--text);
    font-family: 'Inter', system-ui, sans-serif;
}
.block-container { padding: 0 !important; max-width: 100% !important; }
[data-testid="stAppViewContainer"] > .main { background: var(--bg) !important; }
/* Évite le gros vide Streamlit au-dessus du contenu */
section.main > div {
    padding-top: 0 !important;
}

/* ── Sidebar Claude-like ── */
[data-testid="stSidebar"] {
    background: var(--bg-side) !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
    min-width: 260px !important;
}
[data-testid="stSidebar"] > div:first-child { padding: 0 10px 12px !important; }
/* Logo st.logo() collé en haut + nom AssistDoc */
[data-testid="stSidebarHeader"] {
    padding: 10px 8px 6px !important;
    margin: 0 !important;
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
    color: var(--text);
    letter-spacing: -0.2px;
    white-space: nowrap;
}
[data-testid="stSidebarHeader"] img {
    width: 32px !important;
    height: 32px !important;
    border-radius: 9px !important;
    object-fit: cover !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25);
}
[data-testid="stSidebarNav"] {
    padding: 2px 0 6px !important;
    margin: 0 !important;
}
[data-testid="stSidebarNav"] ul { gap: 0 !important; }
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {
    padding-top: 0 !important;
    margin-top: 0 !important;
}
.st-key-sb_export_box {
    margin: 6px 0 4px 0;
    padding: 8px 10px 10px;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    background: rgba(255,255,255,0.03);
    gap: 8px !important;
}
.st-key-sb_export_box [data-testid="stMarkdownContainer"] {
    margin-bottom: 0 !important;
}
.sb-export-title {
    font-size: 11px; font-weight: 600; color: var(--text-dim);
    letter-spacing: 0.04em; text-transform: uppercase;
}
.sb-promo {
    margin: 8px 0 10px 0;
    padding: 14px 14px 12px;
    border-radius: 14px;
    background: #111111;
    border: 1px solid rgba(255,255,255,0.10);
}
.sb-promo-title {
    font-size: 14px;
    font-weight: 600;
    color: #ececec;
    line-height: 1.3;
    margin-bottom: 8px;
}
.sb-promo-text {
    font-size: 12px;
    color: #b4b4b4;
    line-height: 1.45;
    margin-bottom: 0;
}
.sb-section { padding: 8px 10px 4px; }
.sb-section-title {
    font-size: 11px; font-weight: 500; color: var(--text-dim);
    margin-bottom: 6px; padding-left: 4px;
}
.sb-hist-item {
    font-size: 13px; color: var(--text-muted);
    padding: 9px 12px; margin-bottom: 2px; border-radius: 10px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    cursor: default;
}
.sb-hist-item:hover { background: rgba(255,255,255,0.04); color: var(--text); }

.sb-footer {
    padding: 16px 14px 8px; margin-top: 12px;
    border-top: 1px solid rgba(255,255,255,0.06);
    font-size: 11px; color: var(--text-dim);
}
.sb-footer strong {
    display: block; color: var(--text-muted); font-weight: 500;
    font-size: 12px; margin-bottom: 2px;
}

/* ── Topbar ── */
.topbar {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 28px 10px; background: var(--bg);
    position: sticky; top: 0; z-index: 100;
}
.topbar-l {
    font-size: 14px; font-weight: 500; color: var(--text);
    display: flex; align-items: center; gap: 6px;
}
.topbar-l .chev { color: var(--text-dim); font-size: 11px; }
.topbar-r { font-size: 13px; color: var(--text-dim); font-weight: 500; }

/* ── Chat ── */
.chat-wrap { max-width: 720px; margin: 0 auto; padding: 4px 24px 200px; }
@media (max-width: 768px) {
    .chat-wrap { padding: 4px 12px 180px; }
    .topbar { padding: 12px 14px 8px; }
    .wtitle { font-size: 26px; }
}
@media (max-width: 420px) {
    .chat-wrap { padding: 4px 8px 170px; }
    div[class*="st-key-msg_user_"] [data-testid="stChatMessageContent"] {
        max-width: min(520px, calc(100vw - 48px)) !important;
    }
}
.welcome {
    text-align: center; padding: 28px 20px 20px;
    max-width: 520px; margin: 0 auto;
}
.wicon {
    width: 52px; height: 52px; margin: 0 auto 20px; border-radius: 14px;
    object-fit: cover;
    display: block;
    box-shadow: 0 6px 20px rgba(0,0,0,0.28);
}
.wicon-fallback {
    width: 52px; height: 52px; margin: 0 auto 20px; border-radius: 14px;
    background: linear-gradient(145deg, #5b9fd4, #3b7eb0);
    display: flex; align-items: center; justify-content: center;
    font-size: 18px; color: #fff; font-weight: 700;
}
.wtitle {
    font-family: 'Source Serif 4', Georgia, serif;
    font-size: 34px; font-weight: 500; color: var(--text);
    margin-bottom: 12px; letter-spacing: -0.6px;
}
.wsub { font-size: 15px; color: var(--text-muted); line-height: 1.65; }

.msg-meta {
    display: flex; gap: 14px; margin-top: 14px;
    font-size: 12px; color: var(--text-dim); font-family: 'Inter', sans-serif;
}
.src-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.src-tag {
    font-size: 11px; font-family: 'JetBrains Mono', monospace;
    background: var(--bg-elev); border-radius: 6px;
    padding: 4px 9px; color: var(--text-muted); text-decoration: none;
}
.src-tag:hover { color: var(--accent); }

.tdots { display: flex; gap: 5px; align-items: center; padding: 2px 0; }
.tdots span {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--text-dim); animation: bounce 1.2s infinite;
}
.tdots span:nth-child(2) { animation-delay: 0.2s; }
.tdots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce { 0%,60%,100%{transform:translateY(0)} 30%{transform:translateY(-5px)} }
.tlabel { font-size: 13px; color: var(--text-dim); margin-top: 2px; }

/* Indicateur de réflexion compact — dans le bloc assistant uniquement */
.thinking-inline {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
    padding: 2px 0 6px;
    min-height: 0;
}

/* Messages — user à droite, IA à gauche (sans avatars) */
[data-testid="stChatMessage"] {
    background: transparent !important;
    padding: 10px 0 !important;
    max-width: 780px; margin: 0 auto;
    gap: 0 !important;
    display: flex !important;
    width: 100% !important;
    align-items: flex-start !important;
}
/* Masquer totalement les avatars Streamlit (espace réservé inclus) */
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"],
[data-testid="stChatMessage"] > div:has(> [data-testid="stChatMessageAvatarUser"]),
[data-testid="stChatMessage"] > div:has(> [data-testid="stChatMessageAvatarAssistant"]) {
    display: none !important;
    width: 0 !important;
    height: 0 !important;
    min-width: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    border: none !important;
    overflow: hidden !important;
}
/* Images jointes ou générées : taille réelle */
[data-testid="stChatMessageContent"] [data-testid="stImage"] img {
    width: auto !important; height: auto !important;
    max-width: 100% !important; max-height: 320px !important;
    border-radius: 10px !important; background: transparent !important;
}
[data-testid="stChatMessageContent"] {
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    padding: 0 !important;
    font-family: 'Source Serif 4', Georgia, serif !important;
    font-size: 16.5px !important;
    color: var(--text) !important;
    line-height: 1.7 !important;
    max-width: min(560px, 85%) !important;
    min-width: 0 !important;
}

/* Bloc utilisateur : bulle + actions regroupées à droite */
div[class*="st-key-msg_user_"] {
    display: flex !important;
    flex-direction: column !important;
    align-items: flex-end !important;
    width: 100% !important;
    max-width: 780px;
    margin: 0 auto 4px !important;
    gap: 0 !important;
}
div[class*="st-key-msg_user_"] [data-testid="stChatMessage"] {
    width: fit-content !important;
    max-width: min(640px, 100%) !important;
    margin: 0 !important;
    margin-left: auto !important;
    justify-content: flex-end !important;
}
div[class*="st-key-msg_user_"] > [data-testid="stElementContainer"],
div[class*="st-key-msg_user_"] > div {
    width: auto !important;
    max-width: 100% !important;
}

/* User → droite, bulle sans avatar */
div[class*="st-key-msg_user_"] [data-testid="stChatMessageContent"] {
    background: rgba(91,159,212,0.20) !important;
    border: 1px solid rgba(91,159,212,0.38) !important;
    border-radius: 16px 16px 4px 16px !important;
    padding: 12px 16px !important;
    color: #f7f6f2 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 15px !important;
    font-weight: 500 !important;
    line-height: 1.55 !important;
    flex: 0 1 auto !important;
    width: fit-content !important;
    max-width: min(520px, calc(100vw - 64px)) !important;
    min-width: 0 !important;
    margin-left: 0 !important;
    word-break: break-word !important;
    overflow-wrap: anywhere !important;
}
div[class*="st-key-msg_user_"] [data-testid="stChatMessageContent"] [data-testid="stVerticalBlock"],
div[class*="st-key-msg_user_"] [data-testid="stChatMessageContent"] [data-testid="stElementContainer"] {
    width: auto !important;
    gap: 2px !important;
}
div[class*="st-key-msg_user_"] [data-testid="stChatMessageContent"] p:last-child {
    margin-bottom: 0 !important;
}
div[class*="st-key-msg_user_"] [data-testid="stMarkdownContainer"] {
    margin-bottom: 0 !important;
}

/* Barre d'actions : compacte, collée au message */
div[class*="st-key-tbrow_"] {
    gap: 0 !important;
    margin: 2px 0 0 0 !important;
    width: fit-content !important;
    max-width: 100% !important;
}
div[class*="st-key-tbrow_user_"] {
    margin: 2px 0 0 0 !important;
    padding-right: 0 !important;
    align-self: flex-end !important;
}
div[class*="st-key-tbrow_assistant_"] {
    margin: 4px 0 0 0 !important;
}
div[class*="st-key-tbrow_"] [data-testid="stElementContainer"] {
    width: auto !important;
    flex: 0 0 auto !important;
}
div[class*="st-key-tbrow_"] iframe {
    width: 32px !important;
    max-width: 32px !important;
    display: block;
}
div[class*="st-key-tbrow_"] .stButton button {
    width: 28px !important; height: 28px !important;
    min-height: 28px !important; min-width: 28px !important;
    padding: 0 !important; margin: 0 !important;
    border: none !important; border-radius: 8px !important;
    background: transparent !important;
    color: #b0aea5 !important;
    justify-content: center !important;
}
div[class*="st-key-tbrow_"] .stButton button:hover:not(:disabled) {
    background: rgba(255,255,255,0.08) !important;
    color: #f5f4ef !important;
}
div[class*="st-key-tbrow_"] .stButton button [data-testid="stIconMaterial"] {
    font-size: 16px !important;
    margin: 0 !important;
}

/* Desktop : actions au survol ; mobile / tactile : toujours visibles */
@media (hover: hover) and (pointer: fine) {
    div[class*="st-key-msg_user_"] div[class*="st-key-tbrow_"],
    div[class*="st-key-msg_assistant_"] div[class*="st-key-tbrow_"] {
        opacity: 0;
        transition: opacity .15s ease;
    }
    div[class*="st-key-msg_user_"]:hover div[class*="st-key-tbrow_"],
    div[class*="st-key-msg_user_"]:focus-within div[class*="st-key-tbrow_"],
    div[class*="st-key-msg_assistant_"]:hover div[class*="st-key-tbrow_"],
    div[class*="st-key-msg_assistant_"]:focus-within div[class*="st-key-tbrow_"] {
        opacity: 1;
    }
}

/* Bloc IA → gauche, sans avatar */
div[class*="st-key-msg_assistant_"] {
    display: flex !important;
    flex-direction: column !important;
    align-items: flex-start !important;
    width: 100% !important;
    max-width: 780px;
    margin: 6px auto 14px !important;
    gap: 0 !important;
}
div[class*="st-key-msg_assistant_"] [data-testid="stChatMessage"] {
    flex-direction: row !important;
    justify-content: flex-start !important;
    margin: 0 !important;
    width: 100% !important;
}
div[class*="st-key-msg_assistant_"] [data-testid="stChatMessageContent"] {
    text-align: left !important;
    max-width: min(680px, 94%) !important;
    color: #f0eee8 !important;
}
[data-testid="stChatMessageContent"] p { margin: 0 0 0.95em !important; line-height: 1.75 !important; }
[data-testid="stChatMessageContent"] ul,
[data-testid="stChatMessageContent"] ol {
    margin: 0.35em 0 1em !important;
    padding-left: 1.35em !important;
}
[data-testid="stChatMessageContent"] li {
    margin: 0.28em 0 !important;
    line-height: 1.65 !important;
}
[data-testid="stChatMessageContent"] li > p { margin-bottom: 0.35em !important; }
[data-testid="stChatMessageContent"] blockquote {
    margin: 0.8em 0 !important;
    padding: 0.35em 0 0.35em 14px !important;
    border-left: 3px solid rgba(91,159,212,0.55) !important;
    color: var(--text-muted) !important;
}
[data-testid="stChatMessageContent"] table {
    width: 100% !important;
    max-width: 100% !important;
    border-collapse: collapse !important;
    margin: 0.85em 0 1.1em !important;
    font-size: 13.5px !important;
    font-family: 'Inter', sans-serif !important;
    display: block !important;
    overflow-x: auto !important;
}
[data-testid="stChatMessageContent"] th,
[data-testid="stChatMessageContent"] td {
    border: 1px solid rgba(255,255,255,0.12) !important;
    padding: 8px 12px !important;
    text-align: left !important;
    vertical-align: top !important;
}
[data-testid="stChatMessageContent"] th {
    background: rgba(255,255,255,0.06) !important;
    color: #f5f4ef !important;
    font-weight: 600 !important;
}
[data-testid="stChatMessageContent"] td { color: #e8e6df !important; }
[data-testid="stChatMessageContent"] tr:nth-child(even) td {
    background: rgba(255,255,255,0.025) !important;
}
[data-testid="stChatMessageContent"] hr {
    border: none !important;
    border-top: 1px solid rgba(255,255,255,0.10) !important;
    margin: 1.2em 0 !important;
}
[data-testid="stChatMessageContent"] pre {
    background: #0d0d0d !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 12px !important;
    padding: 16px !important;
    overflow-x: auto !important;
    font-size: 13px !important;
    font-family: 'JetBrains Mono', monospace !important;
    margin: 0.75em 0 1.1em !important;
}
[data-testid="stChatMessageContent"] code {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 13px !important;
    background: var(--code-bg) !important;
    border: none !important;
    border-radius: 5px !important;
    padding: 2px 6px !important;
    color: var(--code-fg) !important;
}
[data-testid="stChatMessageContent"] pre code {
    background: none !important; padding: 0 !important; color: #e8e6df !important;
}
[data-testid="stChatMessageContent"] a { color: #8ec4ea !important; text-decoration: none !important; }
[data-testid="stChatMessageContent"] a:hover { text-decoration: underline !important; color: #a8d4f0 !important; }
[data-testid="stChatMessageContent"] strong { color: #ffffff !important; font-weight: 600 !important; }
[data-testid="stChatMessageContent"] h1,
[data-testid="stChatMessageContent"] h2,
[data-testid="stChatMessageContent"] h3 {
    font-family: 'Source Serif 4', Georgia, serif !important;
    color: #ffffff !important;
    font-weight: 600 !important;
    margin: 1.25em 0 0.5em !important;
    line-height: 1.35 !important;
}
[data-testid="stChatMessageContent"] h1 { font-size: 1.4em !important; }
[data-testid="stChatMessageContent"] h2 { font-size: 1.22em !important; }
[data-testid="stChatMessageContent"] h3 { font-size: 1.1em !important; }
[data-testid="stChatMessageContent"] h1:first-child,
[data-testid="stChatMessageContent"] h2:first-child,
[data-testid="stChatMessageContent"] h3:first-child { margin-top: 0.15em !important; }

/* Éditeur inline d'un prompt utilisateur (st.form) — hauteur adaptive via JS */
div[class*="st-key-edit_box_"] {
    width: min(520px, 100%) !important;
    margin: 0 0 4px auto !important;
}
div[class*="st-key-edit_box_"] [data-testid="stForm"] {
    border: none !important;
    background: transparent !important;
    padding: 0 !important;
}
div[class*="st-key-edit_box_"] textarea {
    background: #121212 !important;
    border: 1px solid rgba(91,159,212,0.45) !important;
    border-radius: 14px !important;
    color: #f5f4ef !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 15px !important;
    line-height: 1.55 !important;
    min-height: 68px !important;
    max-height: 320px !important;
    overflow-y: auto !important;
    resize: none !important;
    field-sizing: content;
}
div[class*="st-key-edit_box_"] .stFormSubmitButton button,
div[class*="st-key-edit_box_"] .stButton button {
    min-height: 34px !important;
    border-radius: 10px !important;
}

/* ── Input flottant style Claude ── */
.input-zone {
    position: fixed; bottom: 28px; left: 0; right: 0;
    background: linear-gradient(transparent, var(--bg) 40%);
    padding: 20px 0 8px; z-index: 200;
    pointer-events: none;
}
.input-inner { max-width: 720px; margin: 0 auto; padding: 0 24px; }
.composer-hint {
    font-size: 11.5px; color: var(--text-dim);
    text-align: center; margin-top: 10px; letter-spacing: 0.1px;
}

/* Composer : st.chat_input (pièces jointes, audio et envoi intégrés) */
[data-testid="stChatInput"] {
    max-width: 720px;
    margin: 0 auto;
    width: 100%;
}
[data-testid="stChatInput"] > div {
    background: var(--bg-input) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 22px !important;
    box-shadow: 0 8px 32px rgba(0,0,0,0.28) !important;
    transition: border-color .12s ease;
}
[data-testid="stChatInput"] > div:focus-within {
    border-color: rgba(91,159,212,0.55) !important;
}
[data-testid="stChatInput"] [data-baseweb="textarea"],
[data-testid="stChatInput"] [data-baseweb="base-input"] {
    background: transparent !important;
    border: none !important;
}
[data-testid="stChatInputTextArea"] {
    font-family: 'Inter', sans-serif !important;
    font-size: 15px !important;
    color: var(--text) !important;
}
[data-testid="stChatInputTextArea"]::placeholder { color: var(--text-dim) !important; }
/* Le micro reste fonctionnel mais se déclenche depuis le menu « + » */
[data-testid="stChatInputMicButton"] { display: none !important; }

/* Outils au-dessus du composer (recherche web, connexion pour joindre) */
.st-key-composer_outils {
    max-width: 720px;
    margin: 0 auto 6px !important;
    gap: 6px !important;
}
.st-key-composer_outils .stButton button {
    min-height: 30px !important;
    padding: 2px 12px !important;
    border-radius: 999px !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    background: transparent !important;
    color: var(--text-muted) !important;
    font-size: 12.5px !important;
}
.st-key-composer_outils .stButton button:hover:not(:disabled) {
    background: rgba(255,255,255,0.06) !important;
    color: var(--text) !important;
}
.st-key-composer_outils .st-key-btn_web_on button {
    color: #9ec9e8 !important;
    background: rgba(91,159,212,0.14) !important;
    border-color: rgba(91,159,212,0.35) !important;
}
.st-key-composer_outils .stButton button [data-testid="stIconMaterial"] { font-size: 16px !important; }

/* Suggestions de l'écran d'accueil (clés sug_…) */
div[class*="st-key-sug_"] button {
    background: rgba(255,255,255,0.04) !important;
    color: var(--text-muted) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 14px !important;
    font-weight: 450 !important; font-size: 13.5px !important;
    padding: 14px 16px !important;
    height: auto !important; min-height: 48px !important; width: 100% !important;
    text-align: left !important; justify-content: flex-start !important;
}
div[class*="st-key-sug_"] button:hover {
    background: rgba(255,255,255,0.07) !important;
    border-color: rgba(255,255,255,0.14) !important;
    color: var(--text) !important;
}

/* Sidebar : boutons d'action à hauteur compacte commune */
section[data-testid="stSidebar"] .stButton button,
section[data-testid="stSidebar"] .stDownloadButton > button,
section[data-testid="stSidebar"] .stFormSubmitButton > button {
    min-height: var(--ui-btn-h-sm);
    font-size: var(--ui-fs-sm);
}
/* Nouvelle conversation */
div.st-key-btn_new_chat button {
    background: transparent !important; color: var(--text) !important;
    border: 1px solid rgba(255,255,255,0.14) !important;
    min-height: var(--ui-btn-h) !important; font-weight: 500 !important;
    padding: 0 14px !important; margin-bottom: 4px !important;
    justify-content: flex-start !important;
}
div.st-key-btn_new_chat button:hover { background: rgba(255,255,255,0.05) !important; }
/* Liste des discussions (clés disc_…) : éléments de liste, pas des boutons d'action */
div[class*="st-key-disc_"] button {
    background: transparent !important; color: var(--text-muted) !important;
    border: none !important; min-height: 34px !important;
    font-weight: 450 !important; padding: 6px 10px !important;
    justify-content: flex-start !important; text-align: left !important;
}
div[class*="st-key-disc_"] button > div {
    justify-content: flex-start !important; min-width: 0 !important; width: 100%;
}
div[class*="st-key-disc_"] button p {
    white-space: nowrap !important; overflow: hidden !important; text-overflow: ellipsis !important;
}
div[class*="st-key-disc_"] button:hover {
    background: rgba(255,255,255,0.05) !important; color: var(--text) !important;
}
div[class*="st-key-disc_actif_"] button { background: rgba(255,255,255,0.07) !important; color: var(--text) !important; }
/* Menu ⋯ des discussions — un seul petit bouton */
section[data-testid="stSidebar"] [data-testid="stPopover"] > button,
section[data-testid="stSidebar"] [data-testid="stPopover"] button {
    width: 28px !important;
    min-width: 28px !important;
    max-width: 28px !important;
    height: 28px !important;
    min-height: 28px !important;
    padding: 0 !important;
    font-size: 16px !important;
    line-height: 1 !important;
    border: none !important;
    border-radius: 6px !important;
    background: transparent !important;
    color: var(--text-dim) !important;
    justify-content: center !important;
}
/* Le chevron natif double l'icône ⋯ : un seul symbole par déclencheur */
section[data-testid="stSidebar"] [data-testid="stPopoverButton"] div[aria-hidden="true"]:has([data-testid="stIconMaterial"]) {
    display: none !important;
}
section[data-testid="stSidebar"] [data-testid="stPopover"] > button:hover,
section[data-testid="stSidebar"] [data-testid="stPopover"] button:hover {
    background: rgba(255,255,255,0.08) !important;
    color: var(--text) !important;
}
section[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-disc_"]) {
    flex-wrap: nowrap !important;
    align-items: center !important;
}
section[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-disc_"])
  > div:first-child {
    flex: 1 1 auto !important;
    min-width: 0 !important;
}
section[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-disc_"])
  > div:last-child {
    flex: 0 0 32px !important;
    width: 32px !important;
    min-width: 32px !important;
}

/* Upload / panneaux fichiers (hors menu +) */
[data-testid="stFileUploader"] {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    margin: 0 0 8px !important;
}
[data-testid="stFileUploader"] section,
[data-testid="stFileUploaderDropzone"] {
    background: rgba(255,255,255,0.03) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 12px !important;
    padding: 10px !important;
    min-height: 0 !important;
}
[data-testid="stFileUploader"] label {
    color: var(--text-muted) !important;
    font-size: 12px !important;
}
.stSelectbox > div > div {
    background: var(--bg-elev) !important;
    border-color: rgba(255,255,255,0.1) !important;
    color: var(--text) !important;
    border-radius: 10px !important;
}
.stSlider > div > div > div > div { background: var(--accent) !important; }

::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.12); border-radius: 3px; }

div[data-testid="stExpander"] {
    background: transparent !important;
    border: none !important;
}
div[data-testid="stExpander"] details {
    border: none !important;
    background: transparent !important;
}
div[data-testid="stExpander"] summary {
    color: var(--text-dim) !important;
    font-size: 12px !important;
}

/* Toolbar message Claude (iframe SVG) */
.msg-toolbar-host { margin: 0; padding: 0; }
section.main [data-testid="stChatMessage"] iframe {
    margin: 2px 0 0 0 !important;
    border: none !important;
}

/* Corps des popovers */
div[data-testid="stPopoverBody"],
[data-testid="stPopoverBody"] {
    background: #2c2c29 !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 10px !important;
    box-shadow: 0 12px 32px rgba(0,0,0,0.45) !important;
    /* Compact par défaut (menu ⋯ discussions) */
    padding: 4px !important;
    min-width: 168px !important;
    width: max-content !important;
    max-width: min(240px, calc(100vw - 24px)) !important;
}
[data-testid="stPopoverBody"] [data-testid="stVerticalBlock"] {
    gap: 0 !important;
}
[data-testid="stPopoverBody"] [data-testid="stElementContainer"],
[data-testid="stPopoverBody"] .stElementContainer {
    margin-bottom: 0 !important;
}
[data-testid="stPopoverBody"] .stButton button {
    background: transparent !important;
    color: var(--text) !important;
    border: none !important;
    border-radius: 6px !important;
    justify-content: flex-start !important;
    text-align: left !important;
    height: 32px !important;
    min-height: 32px !important;
    padding: 0 10px !important;
    font-size: 13px !important;
    font-weight: 450 !important;
    width: 100% !important;
    box-shadow: none !important;
}
[data-testid="stPopoverBody"] .stButton button > div,
[data-testid="stPopoverBody"] .stTooltipIcon,
[data-testid="stPopoverBody"] .stTooltipHoverTarget {
    width: 100%;
    justify-content: flex-start !important;
}
[data-testid="stPopoverBody"] div[class*="st-key-danger_"] button {
    color: #ec8b8b !important;
}
[data-testid="stPopoverBody"] div[class*="st-key-danger_"] button:hover {
    background: rgba(201,74,74,0.14) !important;
    color: #f3a3a3 !important;
}
[data-testid="stPopoverBody"] .stButton button:hover {
    background: rgba(255,255,255,0.06) !important;
    color: var(--text) !important;
    border: none !important;
    transform: none !important;
}
[data-testid="stPopoverBody"] .stButton button[kind="primary"] {
    background: rgba(91,159,212,0.14) !important;
    color: #c5e2f7 !important;
    border: none !important;
}
[data-testid="stPopoverBody"] hr {
    margin: 6px 8px !important;
    border-color: rgba(255,255,255,0.08) !important;
}

/* Focus clavier visible sur les déclencheurs de menus et la barre d'actions */
[data-testid="stPopover"] button:focus-visible,
div[class*="st-key-tbrow_"] .stButton button:focus-visible,
.st-key-composer_outils .stButton button:focus-visible {
    outline: 2px solid var(--accent) !important;
    outline-offset: 2px !important;
}

</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# Smart auto-scroll + flèche « revenir en bas » (injectés dans le parent Streamlit)
components.html(
    """
    <script>
    (function () {
      const doc = window.parent.document;
      const win = window.parent;
      const SCROLL_VERSION = 10;
      const NEAR_BOTTOM_PX = 96;

      // ── Smart scroll (singleton versionné : survit aux reruns sans fuite) ──
      (function initSmartScroll() {
        if (win._assistSmartScroll && win._assistSmartScroll.version === SCROLL_VERSION) {
          win._assistSmartScroll.refresh();
          return;
        }
        if (win._assistSmartScroll && typeof win._assistSmartScroll.destroy === 'function') {
          try { win._assistSmartScroll.destroy(); } catch (e) {}
        }

        // États : FOLLOWING_BOTTOM | READING_HISTORY | RETURNING_BOTTOM
        let mode = 'FOLLOWING_BOTTOM';
        let pinnedTop = 0;
        let suppressScrollEvent = false;
        let scrollEl = null;
        let returnTimer = null;
        let rafPending = false;
        let pinRaf = null;
        let lastScrollHeight = 0;
        let userScrollingUp = false;
        let userScrollUpTimer = null;
        let userIntentDown = false;
        let userIntentDownTimer = null;
        let pointerActive = false;
        let touchStartY = null;

        let style = doc.getElementById('assist-scroll-style');
        if (!style) {
          style = doc.createElement('style');
          style.id = 'assist-scroll-style';
          doc.head.appendChild(style);
        }
        style.textContent = `
          #assist-scroll-btn {
            position: fixed !important;
            left: 50%;
            bottom: max(124px, calc(env(safe-area-inset-bottom, 0px) + 112px)) !important;
            transform: translateX(-50%) translateY(6px) scale(0.96) !important;
            z-index: 2147483646 !important;
            width: 34px !important;
            height: 34px !important;
            border-radius: 50% !important;
            border: 1px solid rgba(255,255,255,0.14) !important;
            background: rgba(36,36,34,0.94) !important;
            color: #f5f4ef !important;
            cursor: pointer !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            box-shadow: 0 6px 20px rgba(0,0,0,0.42) !important;
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            padding: 0 !important;
            margin: 0 !important;
            opacity: 0;
            pointer-events: none;
            transition: opacity .18s ease, transform .18s ease, background .15s ease, border-color .15s ease !important;
          }
          #assist-scroll-btn.show {
            opacity: 1;
            pointer-events: auto;
            transform: translate(-50%, 0) scale(1) !important;
          }
          #assist-scroll-btn:hover {
            background: rgba(52,52,48,0.98) !important;
            border-color: rgba(255,255,255,0.24) !important;
          }
          #assist-scroll-btn:active {
            transform: translate(-50%, 1px) scale(0.97) !important;
          }
          #assist-scroll-btn:focus-visible {
            outline: 2px solid rgba(91,159,212,0.7) !important;
            outline-offset: 2px !important;
          }
          #assist-scroll-btn svg {
            width: 15px; height: 15px;
            stroke: #f5f4ef; fill: none;
            stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round;
          }
          @media (max-width: 768px) {
            #assist-scroll-btn {
              width: 32px !important;
              height: 32px !important;
              bottom: max(132px, calc(env(safe-area-inset-bottom, 0px) + 120px)) !important;
            }
          }
          @media (max-width: 420px) {
            #assist-scroll-btn {
              width: 30px !important;
              height: 30px !important;
              bottom: max(142px, calc(env(safe-area-inset-bottom, 0px) + 130px)) !important;
            }
          }
          /* Ancrage navigateur : la croissance du stream ne tire pas le viewport */
          [data-testid="stMain"],
          [data-testid="stMain"] [data-testid="stMainBlockContainer"],
          [data-testid="stMain"] [data-testid="stChatMessage"],
          [data-testid="stMain"] [data-testid="stMarkdownContainer"] {
            overflow-anchor: none !important;
          }
        `;

        let btn = doc.getElementById('assist-scroll-btn');
        if (!btn) {
          btn = doc.createElement('button');
          btn.id = 'assist-scroll-btn';
          btn.type = 'button';
          doc.body.appendChild(btn);
        }
        btn.title = 'Revenir en bas';
        btn.setAttribute('aria-label', 'Revenir en bas de la conversation');
        btn.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>';

        function getScrollEl() {
          // Conteneur réel Streamlit (overflow:auto) — pas stAppViewContainer (overflow:hidden)
          const preferred = doc.querySelector('[data-testid="stMain"]');
          if (preferred) return preferred;
          const candidates = [
            doc.querySelector('section.main'),
            doc.querySelector('.main'),
            doc.scrollingElement,
            doc.documentElement,
          ];
          for (const el of candidates) {
            if (el && el.scrollHeight > el.clientHeight + 40) return el;
          }
          return preferred || candidates[0] || doc.documentElement;
        }

        function gapFromBottom(el) {
          if (!el) return 0;
          return el.scrollHeight - el.scrollTop - el.clientHeight;
        }

        function nearBottom(el) {
          return gapFromBottom(el || getScrollEl()) < NEAR_BOTTOM_PX;
        }

        function setButtonVisible(visible) {
          if (visible) btn.classList.add('show');
          else btn.classList.remove('show');
        }

        function positionButton() {
          // Centre sur stMain ; bottom dynamique juste au-dessus du composer (s'il est visible)
          const main = doc.querySelector('[data-testid="stMain"]');
          const input = doc.querySelector('[data-testid="stChatInput"]');
          if (main) {
            const r = main.getBoundingClientRect();
            btn.style.setProperty('left', Math.round(r.left + r.width / 2) + 'px', 'important');
          } else {
            btn.style.setProperty('left', '50%', 'important');
          }
          const floor = win.matchMedia('(max-width: 420px)').matches ? 130
            : win.matchMedia('(max-width: 768px)').matches ? 120 : 112;
          if (input) {
            const ir = input.getBoundingClientRect();
            const vh = win.innerHeight || doc.documentElement.clientHeight || 0;
            if (ir.height > 8 && ir.top > 40 && ir.top < vh - 8) {
              const bottom = Math.round(vh - ir.top + 12);
              btn.style.setProperty('bottom', Math.max(bottom, floor) + 'px', 'important');
              return;
            }
          }
          btn.style.setProperty('bottom', floor + 'px', 'important');
        }

        function syncButton() {
          positionButton();
          setButtonVisible(mode !== 'FOLLOWING_BOTTOM' && !nearBottom());
        }

        function setMode(next) {
          if (mode === next) {
            syncButton();
            return;
          }
          mode = next;
          if (mode === 'FOLLOWING_BOTTOM') pinnedTop = 0;
          if (mode === 'READING_HISTORY') startPinLoop();
          else stopPinLoop();
          syncButton();
        }

        function withSuppressedScroll(fn) {
          suppressScrollEvent = true;
          try { fn(); }
          finally {
            // 2 frames : laisse passer les scroll events synthétiques Streamlit
            requestAnimationFrame(function () {
              requestAnimationFrame(function () {
                suppressScrollEvent = false;
              });
            });
          }
        }

        function stickToBottom(smooth) {
          const el = getScrollEl();
          if (!el) return;
          const top = el.scrollHeight + 200;
          withSuppressedScroll(function () {
            if (smooth) el.scrollTo({ top: top, behavior: 'smooth' });
            else el.scrollTop = top;
          });
        }

        function restorePinned() {
          const el = getScrollEl();
          if (!el || mode !== 'READING_HISTORY') return;
          if (Math.abs(el.scrollTop - pinnedTop) > 1) {
            withSuppressedScroll(function () {
              el.scrollTop = pinnedTop;
            });
          }
        }

        function startPinLoop() {
          if (pinRaf) return;
          function tick() {
            pinRaf = null;
            if (mode !== 'READING_HISTORY') return;
            restorePinned();
            pinRaf = win.requestAnimationFrame(tick);
          }
          pinRaf = win.requestAnimationFrame(tick);
        }

        function stopPinLoop() {
          if (pinRaf) {
            win.cancelAnimationFrame(pinRaf);
            pinRaf = null;
          }
        }

        function markScrollingUp() {
          userScrollingUp = true;
          userIntentDown = false;
          if (userIntentDownTimer) { clearTimeout(userIntentDownTimer); userIntentDownTimer = null; }
          if (userScrollUpTimer) clearTimeout(userScrollUpTimer);
          userScrollUpTimer = setTimeout(function () { userScrollingUp = false; }, 320);
        }

        function markUserDown() {
          userIntentDown = true;
          userScrollingUp = false;
          if (userScrollUpTimer) { clearTimeout(userScrollUpTimer); userScrollUpTimer = null; }
          if (userIntentDownTimer) clearTimeout(userIntentDownTimer);
          userIntentDownTimer = setTimeout(function () { userIntentDown = false; }, 450);
        }

        function pauseFollowForReading() {
          const el = getScrollEl();
          if (!el) return;
          pinnedTop = el.scrollTop;
          setMode('READING_HISTORY');
        }

        function onPointerDown() {
          pointerActive = true;
        }

        function onPointerUp() {
          const wasActive = pointerActive;
          pointerActive = false;
          if (!wasActive) return;
          const el = getScrollEl();
          if (!el) return;
          // Fin de drag scrollbar / trackpad press : bas atteint → reprendre le suivi
          if (nearBottom(el) && mode !== 'RETURNING_BOTTOM') {
            markUserDown();
            setMode('FOLLOWING_BOTTOM');
          }
        }

        function onKeyDown(ev) {
          if (!ev) return;
          const downKeys = { PageDown: 1, End: 1, ArrowDown: 1, ' ': 1 };
          const upKeys = { PageUp: 1, Home: 1, ArrowUp: 1 };
          if (downKeys[ev.key]) markUserDown();
          if (upKeys[ev.key]) {
            markScrollingUp();
            if (mode === 'FOLLOWING_BOTTOM') pauseFollowForReading();
          }
        }

        function onUserScroll() {
          if (suppressScrollEvent) return;
          const el = getScrollEl();
          if (!el) return;

          if (mode === 'RETURNING_BOTTOM') {
            if (nearBottom(el)) {
              if (returnTimer) { clearInterval(returnTimer); returnTimer = null; }
              userScrollingUp = false;
              userIntentDown = true;
              setMode('FOLLOWING_BOTTOM');
            }
            return;
          }

          if (nearBottom(el)) {
            // Reprendre le suivi seulement sur geste utilisateur (wheel/touch/pointer/keys),
            // jamais sur un scrollTop forcé par Streamlit pendant READING_HISTORY.
            if (mode === 'FOLLOWING_BOTTOM' || userIntentDown || pointerActive) {
              userScrollingUp = false;
              setMode('FOLLOWING_BOTTOM');
              return;
            }
            restorePinned();
            return;
          }

          pinnedTop = el.scrollTop;
          setMode('READING_HISTORY');
        }

        function onWheel(ev) {
          if (mode === 'RETURNING_BOTTOM') return;
          if (ev.deltaY < 0) {
            markScrollingUp();
            if (mode === 'FOLLOWING_BOTTOM') pauseFollowForReading();
          } else if (ev.deltaY > 0) {
            markUserDown();
          }
        }

        function onTouchStart(ev) {
          if (!ev.touches || !ev.touches.length) return;
          touchStartY = ev.touches[0].clientY;
        }

        function onTouchMove(ev) {
          if (touchStartY == null || !ev.touches || !ev.touches.length) return;
          const dy = ev.touches[0].clientY - touchStartY;
          // Doigt vers le bas = contenu vers le haut (lecture historique)
          if (dy > 8) {
            markScrollingUp();
            if (mode === 'FOLLOWING_BOTTOM') pauseFollowForReading();
          } else if (dy < -8) {
            markUserDown();
          }
        }

        function onContentGrowth() {
          const el = getScrollEl();
          if (!el) return;
          const grew = el.scrollHeight !== lastScrollHeight;
          lastScrollHeight = el.scrollHeight;
          if (mode === 'FOLLOWING_BOTTOM') {
            if (userScrollingUp) {
              pauseFollowForReading();
              return;
            }
            stickToBottom(false);
          } else if (mode === 'READING_HISTORY') {
            restorePinned();
            if (grew) syncButton();
          } else if (mode === 'RETURNING_BOTTOM' && grew) {
            stickToBottom(false);
          }
        }

        function scheduleGrowthCheck() {
          if (rafPending) return;
          rafPending = true;
          requestAnimationFrame(function () {
            rafPending = false;
            onContentGrowth();
          });
        }

        function returnToBottom() {
          const el = getScrollEl();
          if (!el) return;
          userIntentDown = true;
          userScrollingUp = false;
          setMode('RETURNING_BOTTOM');
          stickToBottom(true);
          if (returnTimer) clearInterval(returnTimer);
          let tries = 0;
          returnTimer = setInterval(function () {
            tries += 1;
            stickToBottom(false);
            if (nearBottom(el) || tries > 24) {
              clearInterval(returnTimer);
              returnTimer = null;
              setMode('FOLLOWING_BOTTOM');
              stickToBottom(false);
            }
          }, 40);
        }

        function unbindScrollEl(el) {
          if (!el) return;
          el.removeEventListener('scroll', onUserScroll);
          el.removeEventListener('wheel', onWheel);
          el.removeEventListener('touchstart', onTouchStart);
          el.removeEventListener('touchmove', onTouchMove);
          el.removeEventListener('pointerdown', onPointerDown);
          el.removeEventListener('keydown', onKeyDown);
        }

        function bindScrollEl() {
          const el = getScrollEl();
          if (!el) return null;
          if (scrollEl && scrollEl !== el) unbindScrollEl(scrollEl);
          if (el !== scrollEl) {
            el.addEventListener('scroll', onUserScroll, { passive: true });
            el.addEventListener('wheel', onWheel, { passive: true });
            el.addEventListener('touchstart', onTouchStart, { passive: true });
            el.addEventListener('touchmove', onTouchMove, { passive: true });
            el.addEventListener('pointerdown', onPointerDown, { passive: true });
            el.addEventListener('keydown', onKeyDown, { passive: true });
            if (!el.hasAttribute('tabindex')) el.setAttribute('tabindex', '-1');
            scrollEl = el;
            lastScrollHeight = el.scrollHeight;
          }
          return el;
        }

        // CRITIQUE : patcher Element du PARENT (pas celui de l'iframe components.html)
        const ParentElement = win.Element;
        if (ParentElement && !ParentElement.prototype._assistScrollIntoViewPatchedV10) {
          const orig = ParentElement.prototype.scrollIntoView;
          ParentElement.prototype._assistScrollIntoViewOrig = orig;
          ParentElement.prototype.scrollIntoView = function () {
            const state = win._assistSmartScroll;
            if (state && state.getMode && state.getMode() === 'READING_HISTORY') {
              const main = doc.querySelector('[data-testid="stMain"]');
              if (main && (this === main || main.contains(this))) return;
            }
            return orig.apply(this, arguments);
          };
          ParentElement.prototype._assistScrollIntoViewPatchedV10 = true;
        }

        // Neutralise le helper Streamlit s'il est exposé
        if (typeof win.scrollElementIntoContainer === 'function' && !win._assistScrollHelperPatched) {
          const origHelper = win.scrollElementIntoContainer;
          win.scrollElementIntoContainer = function () {
            const state = win._assistSmartScroll;
            if (state && state.getMode && state.getMode() === 'READING_HISTORY') return;
            return origHelper.apply(this, arguments);
          };
          win._assistScrollHelperPatched = true;
        }

        const mo = new MutationObserver(scheduleGrowthCheck);
        const ro = new ResizeObserver(scheduleGrowthCheck);

        function observe() {
          const el = bindScrollEl();
          if (!el) return;
          // Pas de characterData : trop coûteux pendant le streaming token-par-token
          try { mo.observe(el, { childList: true, subtree: true }); } catch (e) {}
          try { ro.observe(el); } catch (e) {}
          if (mode === 'RETURNING_BOTTOM') {
            positionButton();
            return;
          }
          if (mode === 'READING_HISTORY') {
            restorePinned();
            syncButton();
            return;
          }
          // FOLLOWING_BOTTOM
          if (nearBottom(el)) stickToBottom(false);
          else {
            pinnedTop = el.scrollTop;
            setMode('READING_HISTORY');
          }
          syncButton();
        }

        function refresh() {
          observe();
          scheduleGrowthCheck();
        }

        function destroy() {
          if (returnTimer) { clearInterval(returnTimer); returnTimer = null; }
          if (userScrollUpTimer) { clearTimeout(userScrollUpTimer); userScrollUpTimer = null; }
          if (userIntentDownTimer) { clearTimeout(userIntentDownTimer); userIntentDownTimer = null; }
          stopPinLoop();
          if (scrollEl) {
            unbindScrollEl(scrollEl);
            scrollEl = null;
          }
          try { mo.disconnect(); } catch (e) {}
          try { ro.disconnect(); } catch (e) {}
          doc.removeEventListener('pointerup', onPointerUp);
          doc.removeEventListener('pointercancel', onPointerUp);
          btn.onclick = null;
        }

        btn.onclick = function (ev) {
          if (ev) { ev.preventDefault(); ev.stopPropagation(); }
          returnToBottom();
        };

        function onWinResize() { positionButton(); }
        win.addEventListener('resize', onWinResize, { passive: true });
        doc.addEventListener('pointerup', onPointerUp, { passive: true });
        doc.addEventListener('pointercancel', onPointerUp, { passive: true });

        observe();
        // Filet léger : rebind + sync. Le pin serré est géré par startPinLoop en READING.
        const pollId = setInterval(function () {
          bindScrollEl();
          const el = getScrollEl();
          if (!el) return;
          if (mode === 'READING_HISTORY') {
            restorePinned();
            syncButton();
          } else if (mode === 'FOLLOWING_BOTTOM') {
            const gap = gapFromBottom(el);
            if (gap > 8 && gap < 48 && !userScrollingUp) stickToBottom(false);
            syncButton();
          } else {
            positionButton();
          }
        }, 400);

        win._assistSmartScroll = {
          version: SCROLL_VERSION,
          refresh: refresh,
          destroy: function () {
            clearInterval(pollId);
            win.removeEventListener('resize', onWinResize);
            destroy();
            win._assistSmartScroll = null;
          },
          getMode: function () { return mode; },
        };
      })();

      // Composer : rendre le focus au champ à la fin d'une réponse (placeholder « Génération… »).
      // Streamlit désactive aussi le champ pendant chaque rerun : ce cas ne doit pas voler le focus.
      // Pas sur écran tactile (ouvrirait le clavier) ni sous une fenêtre modale.
      const tactile = window.parent.matchMedia && window.parent.matchMedia('(pointer: coarse)').matches;
      if (!win._assistComposerFocusBound) {
        win._assistComposerFocusBound = true;
        let composerReflechissait = false;
        setInterval(function () {
          const ta = doc.querySelector('[data-testid="stChatInputTextArea"]');
          if (!ta) return;
          const ph = ta.placeholder || '';
          const reflechit = ph.indexOf('Génération') === 0 || ph.indexOf('Réflexion') === 0;
          const libre = !doc.activeElement || doc.activeElement === doc.body;
          const modale = doc.querySelector('[role="dialog"]');
          if (composerReflechissait && !reflechit && !ta.disabled && !tactile && libre && !modale) {
            ta.focus();
          }
          if (reflechit || !ta.disabled) composerReflechissait = reflechit;
        }, 300);
      }

      // Édition de prompt (st.form) : Entrée = Envoyer, Maj+Entrée = ligne, Échap = Annuler.
      // Binding versionné : remplace l'ancien listener sans doublon.
      (function installEditKeys() {
        const EDIT_KEYS_VERSION = 4;
        if (doc._assistEditKeysVersion === EDIT_KEYS_VERSION && doc._assistEditKeysHandler) return;
        if (doc._assistEditKeysHandler) {
          try { doc.removeEventListener('keydown', doc._assistEditKeysHandler, true); } catch (err) {}
        }
        if (doc._assistEditClickHandler) {
          try { doc.removeEventListener('pointerdown', doc._assistEditClickHandler, true); } catch (err) {}
        }
        function editBox() {
          return doc.querySelector('[class*="st-key-edit_box_"]');
        }
        function masquerEditImmediat(box) {
          // Perception instantanée : masque avant le round-trip Streamlit
          if (!box) return;
          try {
            box.style.display = 'none';
            box.style.visibility = 'hidden';
            box.style.pointerEvents = 'none';
          } catch (err) {}
        }
        function boutonForm(box, primary) {
          const testid = primary
            ? 'stBaseButton-primaryFormSubmit'
            : 'stBaseButton-secondaryFormSubmit';
          return box.querySelector('[data-testid="' + testid + '"]')
            || box.querySelector('button[kind="' + (primary ? 'primaryFormSubmit' : 'secondaryFormSubmit') + '"]');
        }
        function dansEditBox(el) {
          return !!(el && el.closest && el.closest('[class*="st-key-edit_box_"]'));
        }
        function onEditKeys(ev) {
          const box = editBox();
          if (!box) return;
          const ta = box.querySelector('textarea');
          if (!ta) return;
          // Échap : annule dès que l'éditeur est ouvert (focus non requis sur le textarea)
          if (ev.key === 'Escape') {
            ev.preventDefault();
            try { ta.blur(); } catch (err) {}
            masquerEditImmediat(box);
            const btn = boutonForm(box, false);
            if (btn && !btn.disabled) btn.click();
            return;
          }
          const cible = ev.target;
          const focusEdit = cible === ta || dansEditBox(cible) || doc.activeElement === ta;
          if (!focusEdit) return;
          if (ev.key === 'Enter' && !ev.shiftKey && !ev.altKey && !ev.ctrlKey && !ev.metaKey) {
            if (cible !== ta && !(cible && cible.tagName === 'TEXTAREA')) return;
            ev.preventDefault();
            try { ta.blur(); } catch (err) {}
            const btn = boutonForm(box, true);
            if (btn && !btn.disabled) {
              // Masquer dès Envoyer pour fluidité (le contenu part déjà via le form)
              masquerEditImmediat(box);
              btn.click();
            }
          }
        }
        // Annuler / Envoyer : masquage immédiat au pointerdown (avant le rerun Streamlit)
        function onEditPointer(ev) {
          const t = ev.target;
          if (!t || !t.closest) return;
          const box = t.closest('[class*="st-key-edit_box_"]');
          if (!box) return;
          const btn = t.closest('button');
          if (!btn) return;
          const kind = btn.getAttribute('kind') || '';
          const testid = btn.getAttribute('data-testid') || '';
          const isSubmit = kind.indexOf('FormSubmit') >= 0 || testid.indexOf('FormSubmit') >= 0;
          if (isSubmit) masquerEditImmediat(box);
        }
        doc._assistEditKeysHandler = onEditKeys;
        doc._assistEditClickHandler = onEditPointer;
        doc._assistEditKeysVersion = EDIT_KEYS_VERSION;
        doc._assistEditKeysBound = true;
        doc.addEventListener('keydown', onEditKeys, true);
        doc.addEventListener('pointerdown', onEditPointer, true);
      })();
      // Focus auto + hauteur adaptive du textarea d'édition
      (function () {
        const box = doc.querySelector('[class*="st-key-edit_box_"]');
        if (!box) return;
        const ta = box.querySelector('textarea');
        if (!ta) return;
        function fitEditHeight() {
          const minH = 68;
          const maxH = 320;
          ta.style.height = 'auto';
          const next = Math.min(maxH, Math.max(minH, ta.scrollHeight));
          ta.style.height = next + 'px';
        }
        if (!ta._assistAutoResize) {
          ta.addEventListener('input', fitEditHeight);
          ta._assistAutoResize = true;
        }
        fitEditHeight();
        if (!box._assistFocused && !tactile) {
          ta.focus();
          try {
            const n = ta.value.length;
            ta.setSelectionRange(n, n);
          } catch (err) {}
          box._assistFocused = true;
        }
      })();

      // Fenêtre modale : focus — singleton (évite un setInterval par rerun Streamlit)
      if (!win._assistModalFocusBound) {
        win._assistModalFocusBound = true;
        let champModaleVu = null;
        setInterval(function () {
          const champ = doc.querySelector(
            '[role="dialog"] input:not([type="hidden"]):not([disabled]), [role="dialog"] textarea:not([disabled])'
          );
          if (champ && champ !== champModaleVu) {
            const dansModale = doc.activeElement && doc.activeElement.closest('[role="dialog"]');
            const surChamp = dansModale && /^(INPUT|TEXTAREA)$/.test(doc.activeElement.tagName);
            if (!surChamp) champ.focus();
          }
          champModaleVu = champ;
        }, 400);
      }

      // Noms accessibles — singleton (évite la fuite d'intervalles à chaque remount)
      if (!win._assistAriaLabelsBound) {
        win._assistAriaLabelsBound = true;
        const NOMS = [
          ['[class*="st-key-fb_up_"] button', 'Réponse utile'],
          ['[class*="st-key-fb_dn_"] button', 'Réponse pas utile'],
          ['[class*="st-key-edit_btn_"] button', 'Modifier'],
          ['section[data-testid="stSidebar"] [data-testid="stPopoverButton"]', 'Actions de la discussion'],
        ];
        setInterval(function () {
          NOMS.forEach(function (n) {
            doc.querySelectorAll(n[0]).forEach(function (b) {
              if (!b.getAttribute('aria-label')) b.setAttribute('aria-label', n[1]);
            });
          });
          doc.querySelectorAll('[data-testid="stFileChipDeleteBtn"] button[aria-label^="Remove "]').forEach(function (b) {
            b.setAttribute('aria-label', 'Retirer ' + b.getAttribute('aria-label').slice(7));
            b.title = b.getAttribute('aria-label');
          });
        }, 1500);
      }

      // Menu « + » du composer : exécuté dans la page parente (caméra/micro y sont autorisés)
      function assistPlusMenu() {
        if (window._assistPlusMenu) return;
        window._assistPlusMenu = true;
        const doc = document;
        const tactile = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
        const svg = function (p) { return '<svg viewBox="0 0 24 24" aria-hidden="true">' + p + '</svg>'; };
        const ENTREES = [
          ['fichiers', 'Ajouter des fichiers ou images', svg('<path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/>')],
          ['photo', 'Prendre une photo', svg('<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/><circle cx="12" cy="13" r="3"/>')],
          ['audio', 'Enregistrer un audio', svg('<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><path d="M12 19v3"/>')],
        ];

        const style = doc.createElement('style');
        style.textContent = `
          #assist-plus-menu {
            position: fixed; z-index: 2147483646; min-width: 250px;
            background: #2b2a27; border: 1px solid rgba(255,255,255,0.1); border-radius: 14px;
            padding: 6px; box-shadow: 0 12px 40px rgba(0,0,0,0.45);
            display: flex; flex-direction: column; gap: 2px; font-family: 'Inter', sans-serif;
          }
          #assist-plus-menu button {
            display: flex; align-items: center; gap: 12px; width: 100%;
            padding: 9px 12px; border: none; border-radius: 9px; background: transparent;
            color: #ecebe6; font: 500 14px 'Inter', sans-serif; text-align: left; cursor: pointer;
          }
          #assist-plus-menu button:hover, #assist-plus-menu button:focus { background: rgba(255,255,255,0.08); outline: none; }
          #assist-plus-menu button:focus-visible { box-shadow: inset 0 0 0 2px #5b9fd4; }
          #assist-plus-menu svg, #assist-cam svg {
            width: 18px; height: 18px; flex: 0 0 18px; stroke: #b0aea5; fill: none;
            stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round;
          }
          #assist-cam {
            position: fixed; inset: 0; z-index: 2147483646; background: rgba(0,0,0,0.6);
            display: flex; align-items: center; justify-content: center; font-family: 'Inter', sans-serif;
          }
          #assist-cam .cam-box {
            background: #2b2a27; border: 1px solid rgba(255,255,255,0.1); border-radius: 16px;
            padding: 16px; width: min(520px, 92vw); display: flex; flex-direction: column; gap: 12px;
          }
          #assist-cam video { width: 100%; border-radius: 10px; background: #000; transform: scaleX(-1); }
          #assist-cam .cam-msg { margin: 0; color: #d6d4cc; font-size: 14px; }
          #assist-cam .cam-actions { display: flex; justify-content: flex-end; gap: 8px; }
          #assist-cam .cam-actions button {
            padding: 8px 16px; border-radius: 10px; font: 500 14px 'Inter', sans-serif; cursor: pointer;
            border: 1px solid rgba(255,255,255,0.14); background: transparent; color: #ecebe6;
          }
          #assist-cam .cam-actions .cam-ok { background: #5b9fd4; border-color: #5b9fd4; color: #0f1b26; }
          #assist-cam .cam-actions button:disabled { opacity: 0.4; cursor: not-allowed; }
          #assist-cam .cam-actions button:focus-visible { outline: 2px solid #5b9fd4; outline-offset: 2px; }
          #assist-toast {
            position: fixed; left: 50%; bottom: 120px; transform: translateX(-50%); z-index: 2147483646;
            background: #3a2626; color: #f3d6d6; border: 1px solid rgba(220,90,90,0.4); border-radius: 10px;
            padding: 10px 14px; font: 14px 'Inter', sans-serif; max-width: 90vw;
          }
        `;
        doc.head.appendChild(style);

        let menu = null;
        const zone = function () { return doc.querySelector('[data-testid="stChatInputFileUploadButton"]'); };
        const boutonPlus = function () { const z = zone(); return z && z.querySelector('button'); };
        const inputFichiers = function () { const z = zone(); return z && z.querySelector('input[type="file"]'); };
        const champTexte = function () { return doc.querySelector('[data-testid="stChatInputTextArea"]'); };

        function avertir(texte) {
          let t = doc.getElementById('assist-toast');
          if (!t) {
            t = doc.createElement('div');
            t.id = 'assist-toast';
            t.setAttribute('role', 'alert');
            doc.body.appendChild(t);
          }
          t.textContent = texte;
          clearTimeout(t._minuteur);
          t._minuteur = setTimeout(function () { t.remove(); }, 6000);
        }

        function joindre(fichiers) {
          const inp = inputFichiers();
          if (!inp || !fichiers.length) return;
          const dt = new DataTransfer();
          fichiers.forEach(function (f) { dt.items.add(f); });
          inp.files = dt.files;
          inp.dispatchEvent(new Event('change', { bubbles: true }));
        }

        function fermer(rendreFocus) {
          if (!menu) return;
          menu.remove();
          menu = null;
          const b = boutonPlus();
          if (b) {
            b.setAttribute('aria-expanded', 'false');
            if (rendreFocus) b.focus();
          }
        }

        function ouvrir() {
          const b = boutonPlus();
          if (!b) return;
          menu = doc.createElement('div');
          menu.id = 'assist-plus-menu';
          menu.setAttribute('role', 'menu');
          menu.setAttribute('aria-label', 'Joindre');
          ENTREES.forEach(function (e) {
            const item = doc.createElement('button');
            item.type = 'button';
            item.setAttribute('role', 'menuitem');
            item.innerHTML = e[2] + '<span>' + e[1] + '</span>';
            item.addEventListener('click', function (ev) {
              ev.stopPropagation();
              fermer(false);
              agir(e[0]);
            });
            menu.appendChild(item);
          });
          menu.addEventListener('keydown', function (ev) {
            const items = Array.from(menu.querySelectorAll('button'));
            const i = items.indexOf(doc.activeElement);
            if (ev.key === 'ArrowDown') { ev.preventDefault(); items[(i + 1) % items.length].focus(); }
            else if (ev.key === 'ArrowUp') { ev.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
            else if (ev.key === 'Home') { ev.preventDefault(); items[0].focus(); }
            else if (ev.key === 'End') { ev.preventDefault(); items[items.length - 1].focus(); }
            else if (ev.key === 'Escape') { ev.preventDefault(); fermer(true); }
            else if (ev.key === 'Tab') { fermer(false); }
          });
          doc.body.appendChild(menu);
          const r = b.getBoundingClientRect();
          menu.style.left = Math.max(8, Math.min(r.left, window.innerWidth - menu.offsetWidth - 8)) + 'px';
          menu.style.bottom = (window.innerHeight - r.top + 8) + 'px';
          b.setAttribute('aria-haspopup', 'menu');
          b.setAttribute('aria-expanded', 'true');
          menu.querySelector('button').focus();
        }

        function agir(action) {
          if (action === 'fichiers') {
            // Appel synchrone dans le geste utilisateur, sinon le navigateur refuse le sélecteur natif
            const inp = inputFichiers();
            if (inp) { inp.value = ''; inp.click(); }
            else avertir('Import de fichiers indisponible pour le moment.');
          } else if (action === 'photo') {
            if (tactile) photoMobile(); else photoWebcam();
          } else if (action === 'audio') {
            enregistrer();
          }
        }

        function photoMobile() {
          const inp = doc.createElement('input');
          inp.type = 'file';
          inp.accept = 'image/*';
          inp.setAttribute('capture', 'environment');
          inp.addEventListener('change', function () { joindre(Array.from(inp.files || [])); });
          inp.click();
        }

        function photoWebcam() {
          const ov = doc.createElement('div');
          ov.id = 'assist-cam';
          ov.setAttribute('role', 'dialog');
          ov.setAttribute('aria-modal', 'true');
          ov.setAttribute('aria-label', 'Prendre une photo');
          ov.innerHTML = '<div class="cam-box"><video autoplay playsinline muted></video>'
            + '<p class="cam-msg">Autorisez l\\u2019accès à la caméra si le navigateur le demande.</p>'
            + '<div class="cam-actions"><button type="button" class="cam-annuler">Annuler</button>'
            + '<button type="button" class="cam-ok" disabled>Prendre la photo</button></div></div>';
          doc.body.appendChild(ov);
          const video = ov.querySelector('video');
          const msg = ov.querySelector('.cam-msg');
          const ok = ov.querySelector('.cam-ok');
          const annuler = ov.querySelector('.cam-annuler');
          let flux = null;
          annuler.focus();

          function fermerCam() {
            if (flux) flux.getTracks().forEach(function (t) { t.stop(); });
            ov.remove();
            const ta = champTexte();
            if (ta) ta.focus();
          }
          annuler.addEventListener('click', fermerCam);
          ov.addEventListener('click', function (ev) { if (ev.target === ov) fermerCam(); });
          ov.addEventListener('keydown', function (ev) {
            if (ev.key === 'Escape') { ev.preventDefault(); fermerCam(); }
            else if (ev.key === 'Tab') {
              const btns = [annuler, ok].filter(function (b) { return !b.disabled; });
              const i = btns.indexOf(doc.activeElement);
              ev.preventDefault();
              btns[(i + (ev.shiftKey ? btns.length - 1 : 1)) % btns.length].focus();
            }
          });
          ok.addEventListener('click', function () {
            const c = doc.createElement('canvas');
            c.width = video.videoWidth;
            c.height = video.videoHeight;
            c.getContext('2d').drawImage(video, 0, 0);
            c.toBlob(function (blob) {
              if (blob) joindre([new File([blob], 'photo-' + Date.now() + '.jpg', { type: 'image/jpeg' })]);
              fermerCam();
            }, 'image/jpeg', 0.9);
          });

          if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            video.style.display = 'none';
            msg.textContent = 'Caméra non disponible dans ce navigateur. Utilisez « Ajouter des fichiers ou images ».';
            return;
          }
          navigator.mediaDevices.getUserMedia({ video: true }).then(function (s) {
            if (!ov.isConnected) { s.getTracks().forEach(function (t) { t.stop(); }); return; }
            flux = s;
            video.srcObject = s;
            msg.textContent = 'Cadrez puis prenez la photo : elle sera jointe à votre message.';
            ok.disabled = false;
            ok.focus();
          }).catch(function () {
            video.style.display = 'none';
            msg.textContent = 'Caméra inaccessible : autorisez son accès dans le navigateur ou vérifiez qu\\u2019une caméra est branchée.';
          });
        }

        function enregistrer() {
          const mic = doc.querySelector('[data-testid="stChatInputMicButton"]');
          if (!mic || mic.disabled) { avertir('Enregistrement audio indisponible pour le moment.'); return; }
          const lancer = function () { mic.click(); };
          if (navigator.permissions && navigator.permissions.query) {
            navigator.permissions.query({ name: 'microphone' }).then(function (p) {
              if (p.state === 'denied') avertir('Micro bloqué : autorisez son accès dans les réglages du navigateur.');
              else lancer();
            }).catch(lancer);
          } else {
            lancer();
          }
        }

        // Le clic (ou Entrée/Espace) sur « + » ouvre le menu au lieu du sélecteur de fichiers.
        // Les clics sur l'<input type="file"> lui-même doivent passer : un preventDefault() y annule le dialogue natif.
        doc.addEventListener('click', function (ev) {
          const z = zone();
          if (z && z.contains(ev.target)) {
            if (ev.target.matches && ev.target.matches('input[type="file"]')) return;
            ev.preventDefault();
            ev.stopPropagation();
            if (menu) fermer(true); else ouvrir();
            return;
          }
          if (menu && !menu.contains(ev.target)) fermer(false);
        }, true);
        doc.addEventListener('keydown', function (ev) {
          const z = zone();
          if (z && z.contains(ev.target) && (ev.key === 'Enter' || ev.key === ' ')) {
            ev.preventDefault();
            ev.stopPropagation();
            if (menu) fermer(true); else ouvrir();
          }
        }, true);
        // L'infobulle Streamlit « Upload or drag and drop… » recouvrirait le menu
        ['mouseover', 'mouseout', 'pointerover', 'pointerout'].forEach(function (type) {
          doc.addEventListener(type, function (ev) {
            const z = zone();
            if (z && z.contains(ev.target)) ev.stopPropagation();
          }, true);
        });
        window.addEventListener('resize', function () { fermer(false); });
        setInterval(function () {
          const b = boutonPlus();
          if (b && b.getAttribute('aria-haspopup') !== 'menu') {
            b.setAttribute('aria-label', 'Joindre un fichier, une photo ou un audio');
            b.setAttribute('aria-haspopup', 'menu');
            b.setAttribute('aria-expanded', 'false');
          }
        }, 1000);
      }
      if (!doc.getElementById('assist-plus-script')) {
        const s = doc.createElement('script');
        s.id = 'assist-plus-script';
        s.textContent = '(' + assistPlusMenu.toString() + ')();';
        doc.head.appendChild(s);
      }

      // Pont toolbar v5 : plus de location.assign pour Edit (géré en bouton Streamlit).
      // Conservé uniquement pour d'éventuels messages fb legacy — sans navigation lourde.
      const BRIDGE_ID = 'assist-toolbar-bridge-v5';
      if (!doc.getElementById(BRIDGE_ID)) {
        const prev = doc.querySelectorAll('script[id^="assist-toolbar-bridge"]');
        prev.forEach(function (n) { n.remove(); });
        if (window.parent._assistToolbarHandler) {
          try { window.parent.removeEventListener('message', window.parent._assistToolbarHandler); } catch (err) {}
          window.parent._assistToolbarHandler = null;
        }
        const s = doc.createElement('script');
        s.id = BRIDGE_ID;
        s.textContent = '(' + function () {
          const VERSION = 'v5';
          if (window._assistToolbarBridgeVersion === VERSION && window._assistToolbarHandler) return;
          if (window._assistToolbarHandler) {
            try { window.removeEventListener('message', window._assistToolbarHandler); } catch (err) {}
          }
          function onToolbarMessage(e) {
            try {
              const d = e && e.data;
              if (!d || d.source !== 'assistdoc-toolbar') return;
              // Edit : ignoré ici (bouton Streamlit → session_state + rerun, sans reload).
              if (d.action === 'edit') return;
              if (d.action !== 'fb') return;
              // Feedback legacy uniquement : query params sans assign si déjà présents
              const url = new URL(window.location.href);
              url.searchParams.set('fb', String(d.note));
              url.searchParams.set('fb_idx', String(d.idx));
              window.history.replaceState({}, '', url.toString());
              window.dispatchEvent(new PopStateEvent('popstate'));
            } catch (err) {}
          }
          window._assistToolbarHandler = onToolbarMessage;
          window._assistToolbarBridgeVersion = VERSION;
          window._assistToolbarBound = true;
          window.addEventListener('message', onToolbarMessage);
        }.toString() + ')();';
        doc.head.appendChild(s);
      }
    })();
    </script>
    """,
    height=0,
)


def _titre_discussion(messages: list) -> str:
    for m in messages:
        if m.get("role") == "user" and m.get("content", "").strip():
            t = m["content"].strip().replace("\n", " ")
            return t[:52] + ("…" if len(t) > 52 else "")
    return "Nouvelle discussion"


def _creer_discussion() -> dict:
    return {
        "id": str(uuid.uuid4()),
        "titre": "Nouvelle discussion",
        "messages": [],
        "historique_llm": [],
        "figee": False,
        "titre_manuel": False,
    }


def _trouver_discussion(cid: str) -> Optional[dict]:
    for c in st.session_state.conversations:
        if c["id"] == cid:
            return c
    return None


def _discussion_figee(cid: Optional[str] = None) -> bool:
    cid = cid or st.session_state.conversation_id
    c = _trouver_discussion(cid)
    return bool(c and c.get("figee"))


def sync_discussion():
    """Persiste l'état courant en session + SQLite."""
    cid = st.session_state.conversation_id
    for c in st.session_state.conversations:
        if c["id"] == cid:
            c["messages"] = list(st.session_state.messages)
            c["historique_llm"] = list(st.session_state.historique_llm)
            # Titre auto seulement si non figée et non renommée manuellement
            if not c.get("figee") and not c.get("titre_manuel"):
                c["titre"] = _titre_discussion(c["messages"])
            try:
                _db().sauvegarder_conversation(
                    cid, c["titre"], c["messages"], figee=bool(c.get("figee"))
                )
            except Exception:
                pass
            return
    d = _creer_discussion()
    d["id"] = cid
    d["messages"] = list(st.session_state.messages)
    d["historique_llm"] = list(st.session_state.historique_llm)
    d["titre"] = _titre_discussion(d["messages"])
    st.session_state.conversations.insert(0, d)
    try:
        _db().sauvegarder_conversation(cid, d["titre"], d["messages"], figee=False)
    except Exception:
        pass


def renommer_discussion(cid: str, nouveau_titre: str) -> bool:
    titre = (nouveau_titre or "").strip()
    if not titre:
        return False
    c = _trouver_discussion(cid)
    if not c or c.get("figee"):
        return False
    c["titre"] = titre[:120]
    c["titre_manuel"] = True
    try:
        ok = _db().renommer_conversation(cid, c["titre"])
        if not ok:
            _db().sauvegarder_conversation(cid, c["titre"], c.get("messages", []), figee=False)
    except Exception:
        pass
    return True


def basculer_figee(cid: str) -> bool:
    c = _trouver_discussion(cid)
    if not c:
        return False
    c["figee"] = not bool(c.get("figee"))
    try:
        _db().figer_conversation(cid, bool(c["figee"]))
    except Exception:
        pass
    # Remonter les figées en tête
    st.session_state.conversations.sort(
        key=lambda x: (0 if x.get("figee") else 1, x.get("titre") or "")
    )
    return True


def supprimer_discussion(cid: str) -> bool:
    c = _trouver_discussion(cid)
    if not c:
        return False
    if c.get("figee"):
        return False
    db = _db()
    if db.obtenir_conversation(cid) is not None:
        if not db.supprimer_conversation(cid):
            return False
    # Sinon : discussion jamais enregistrée (présente seulement dans cette session)

    st.session_state.conversations = [
        x for x in st.session_state.conversations if x["id"] != cid
    ]
    if st.session_state.conversation_id == cid:
        if st.session_state.conversations:
            autre = st.session_state.conversations[0]
            st.session_state.conversation_id = autre["id"]
            st.session_state.messages = list(autre.get("messages", []))
            st.session_state.historique_llm = list(autre.get("historique_llm", []))
        else:
            d = _creer_discussion()
            st.session_state.conversations = [d]
            st.session_state.conversation_id = d["id"]
            st.session_state.messages = []
            st.session_state.historique_llm = []
            try:
                _db().sauvegarder_conversation(d["id"], d["titre"], [])
            except Exception:
                pass
        st.session_state.fichiers_en_attente = []
        st.session_state.en_cours = False
        st.session_state.input_key += 1
    return True


CLE_SUPPR_DISCUSSION = "confirm_del_id"
CLE_RENOMMER_DISCUSSION = "edit_titre_id"
CLE_SUPPR_COLLECTION = "confirm_del_collection"


def _fermer_confirm_suppression() -> None:
    annuler_confirmation(CLE_SUPPR_DISCUSSION)


@st.dialog("Supprimer cette conversation ?", width="small", on_dismiss=_fermer_confirm_suppression)
def _dialog_confirm_suppression() -> None:
    del_id = confirmation_en_attente(CLE_SUPPR_DISCUSSION)
    cible = _trouver_discussion(del_id) if del_id else None
    if not cible or cible.get("figee"):
        _fermer_confirm_suppression()
        st.rerun()
        return

    titre = (cible.get("titre") or "Nouvelle discussion").strip() or "Nouvelle discussion"
    texte_dialogue(
        "La conversation {nom} sera supprimée de votre historique.",
        nom=f"« {titre[:80]} »",
        note="Cette action ne pourra pas être annulée.",
    )
    erreur = erreur_confirmation(CLE_SUPPR_DISCUSSION)
    if erreur:
        afficher_erreur(erreur)
    annuler, confirmer = pied_dialogue("suppr_conv", "Supprimer", danger=True)
    if annuler:
        _fermer_confirm_suppression()
        st.rerun()
    if confirmer:
        with st.spinner("Suppression…"):
            ok = executer_confirmation(
                CLE_SUPPR_DISCUSSION,
                del_id,
                lambda: supprimer_discussion(del_id),
                succes="Conversation supprimée.",
                echec="La conversation n'a pas pu être supprimée. Réessayez dans un instant.",
            )
        if ok is not None:
            st.rerun()


def _fermer_renommage() -> None:
    annuler_confirmation(CLE_RENOMMER_DISCUSSION)


@st.dialog("Renommer la conversation", width="small", on_dismiss=_fermer_renommage)
def _dialog_renommer() -> None:
    cid = confirmation_en_attente(CLE_RENOMMER_DISCUSSION)
    cible = _trouver_discussion(cid) if cid else None
    if not cible or cible.get("figee"):
        _fermer_renommage()
        st.rerun()
        return
    with st.form(f"form_rename_{cid}", clear_on_submit=False, border=False):
        nouveau = st.text_input(
            "Nouveau titre",
            value=cible.get("titre") or "",
            max_chars=120,
            placeholder="Ex. : Déploiement Docker",
        )
        zone_erreur = st.empty()
        g, d = st.columns(2, gap="small")
        with g:
            annuler = st.form_submit_button("Annuler", use_container_width=True)
        with d:
            enregistrer = st.form_submit_button("Enregistrer", type="primary", use_container_width=True)
    if annuler:
        _fermer_renommage()
        st.rerun()
    if enregistrer:
        if not (nouveau or "").strip():
            with zone_erreur:
                afficher_erreur("Le titre ne peut pas être vide.")
        elif renommer_discussion(cid, nouveau):
            _fermer_renommage()
            notifier("Titre mis à jour.")
            st.rerun()
        else:
            with zone_erreur:
                afficher_erreur("Le titre n'a pas pu être enregistré. Réessayez.")


def _fermer_suppr_collection() -> None:
    annuler_confirmation(CLE_SUPPR_COLLECTION)


@st.dialog("Supprimer cette collection ?", width="small", on_dismiss=_fermer_suppr_collection)
def _dialog_suppr_collection() -> None:
    demande = confirmation_en_attente(CLE_SUPPR_COLLECTION)
    if not demande:
        st.rerun()
        return
    col_id, nom = demande
    try:
        nb = len(_favoris().lister_favoris(col_id))
    except Exception as exc:
        nb = 0
        message_erreur("Lecture des favoris de la collection impossible", exc)
    texte_dialogue(
        "Vous êtes sur le point de supprimer la collection {nom}"
        + (f" et les {nb} favori(s) qu'elle contient." if nb else " (elle ne contient aucun favori)."),
        nom=f"« {nom} »",
        note="Les conversations ne sont pas concernées. Cette action ne pourra pas être annulée.",
    )
    erreur = erreur_confirmation(CLE_SUPPR_COLLECTION)
    if erreur:
        afficher_erreur(erreur)
    annuler, confirmer = pied_dialogue("suppr_coll", "Supprimer", danger=True)
    if annuler:
        _fermer_suppr_collection()
        st.rerun()
    if confirmer:
        ok = executer_confirmation(
            CLE_SUPPR_COLLECTION,
            demande,
            lambda: _favoris().supprimer_collection(col_id),
            succes="Collection supprimée.",
            echec="La collection n'a pas pu être supprimée. Réessayez dans un instant.",
        )
        if ok is not None:
            st.session_state.pop("sel_collection_fav", None)
            st.rerun()


def afficher_dialog_suppression_si_besoin() -> None:
    """Une seule fenêtre à la fois (Streamlit n'en affiche qu'une par run)."""
    if confirmation_en_attente(CLE_SUPPR_DISCUSSION):
        _dialog_confirm_suppression()
    elif confirmation_en_attente(CLE_RENOMMER_DISCUSSION):
        _dialog_renommer()
    elif confirmation_en_attente(CLE_SUPPR_COLLECTION):
        _dialog_suppr_collection()


def modifier_message(idx: int, nouveau_contenu: str) -> bool:
    """Met à jour le texte d'un message sans relancer la génération."""
    if _discussion_figee():
        return False
    maj = appliquer_edition_contenu(st.session_state.messages, idx, nouveau_contenu)
    if maj is None:
        return False
    st.session_state.messages = maj
    st.session_state.historique_llm = resync_historique_llm(maj)
    sync_discussion()
    return True


def modifier_prompt_et_regenerer(idx: int, nouveau_contenu: str) -> bool:
    """Édite un message utilisateur (style ChatGPT) : tronque la suite et relance l'IA.

    Conserve les messages précédents, remplace le prompt, supprime les réponses
    devenues obsolètes (branche après idx), puis démarre une nouvelle génération.
    """
    if not edition_autorisee(st.session_state, figee=_discussion_figee()):
        return False
    role_origine = (st.session_state.messages[idx] or {}).get("role")
    resultat = appliquer_edition_prompt(st.session_state.messages, idx, nouveau_contenu)
    if resultat is None:
        return False
    messages, historique = resultat
    # Édition d'un message assistant : mise à jour simple, pas de régénération
    if role_origine != "user":
        st.session_state.messages = messages
        st.session_state.historique_llm = historique
        sync_discussion()
        return True

    # Tour déjà affiché : ne pas redébiter le quota invité sur une régénération Edit
    if 0 <= idx < len(messages) and messages[idx].get("role") == "user":
        messages[idx]["quota_decompte"] = True

    st.session_state.messages = messages
    st.session_state.historique_llm = historique
    st.session_state.edit_msg_idx = None
    st.session_state.en_cours = True
    st.session_state.input_key += 1
    sync_discussion()
    return True


def supprimer_message(idx: int) -> bool:
    if _discussion_figee():
        return False
    if idx < 0 or idx >= len(st.session_state.messages):
        return False
    st.session_state.messages.pop(idx)
    st.session_state.historique_llm = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages
        if m.get("role") in ("user", "assistant")
    ]
    sync_discussion()
    return True


def nouvelle_discussion():
    """Archive la discussion courante et en démarre une nouvelle."""
    sync_discussion()
    st.session_state.conversations = [
        c for c in st.session_state.conversations if c.get("messages") or c.get("figee")
    ]
    d = _creer_discussion()
    st.session_state.conversations.insert(0, d)
    st.session_state.conversation_id = d["id"]
    st.session_state.messages = []
    st.session_state.historique_llm = []
    st.session_state.fichiers_en_attente = []
    st.session_state.en_cours = False
    st.session_state.contexte_projet = {}
    st.session_state.input_key += 1
    try:
        _db().sauvegarder_conversation(d["id"], d["titre"], [])
    except Exception:
        pass


def charger_discussion(cid: str):
    """Charge une discussion existante depuis l'historique."""
    if cid == st.session_state.conversation_id:
        return
    sync_discussion()
    for c in st.session_state.conversations:
        if c["id"] == cid:
            st.session_state.conversation_id = cid
            st.session_state.messages = list(c.get("messages", []))
            st.session_state.historique_llm = list(c.get("historique_llm", []))
            st.session_state.fichiers_en_attente = []
            st.session_state.en_cours = False
            st.session_state.input_key += 1
            return
    # Fallback SQLite
    try:
        msgs = _db().charger_messages(cid)
        meta = _db().obtenir_conversation(cid) or {}
        if msgs or meta:
            st.session_state.conversation_id = cid
            st.session_state.messages = msgs
            st.session_state.historique_llm = [
                {"role": m["role"], "content": m["content"]}
                for m in msgs
                if m.get("role") in ("user", "assistant")
            ]
            st.session_state.input_key += 1
    except Exception:
        pass


def init():
    d = {
        "moteur": None, "generateur": None, "orchestrateur": None, "pret": False,
        "messages": [], "historique_llm": [],
        "input_key": 0, "en_cours": False,
        "filtre_lang": "Tous", "top_k": 5,
        "filtre_repo": "", "filtre_stars": 0, "filtre_date": "",
        "fichiers_en_attente": [],
        "conversations": None,
        "conversation_id": None,
        "web_search_actif": False,
        "utiliser_corpus_avec_fichier": True,
        "edit_msg_idx": None,
        "contexte_projet": {},
    }
    for k, v in d.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # Changement d'identité (connexion, déconnexion, session expirée) : rien de l'état
    # précédent (conversation ouverte, messages, fichiers, contexte) ne doit être réutilisé.
    owner = _owner()
    if st.session_state.get("conversations_owner") != owner:
        for k in (
            "messages", "historique_llm", "conversations", "conversation_id",
            "fichiers_en_attente", "contexte_projet", "edit_msg_idx",
        ):
            st.session_state[k] = d[k] if not isinstance(d[k], (list, dict)) else type(d[k])()
        for k in list(st.session_state.keys()):
            if str(k).startswith(("feedback_envoye", "confirm_del_id", "edit_titre_id")):
                st.session_state.pop(k, None)
        st.session_state.conversations_owner = owner
        st.session_state.input_key += 1

    # Charger l'historique SQLite du propriétaire courant si session vide
    if not st.session_state.conversations:
        try:
            rows = _db().lister_conversations(40)
            convs = []
            for r in rows:
                msgs = _db().charger_messages(r["id"])
                convs.append({
                    "id": r["id"],
                    "titre": r.get("titre") or "Nouvelle discussion",
                    "messages": msgs,
                    "historique_llm": [
                        {"role": m["role"], "content": m["content"]}
                        for m in msgs
                        if m.get("role") in ("user", "assistant")
                    ],
                    "figee": bool(r.get("figee")),
                    "titre_manuel": True,  # titre issu de la DB
                })
            if convs:
                st.session_state.conversations = convs
                st.session_state.conversation_id = convs[0]["id"]
                st.session_state.messages = list(convs[0].get("messages", []))
                st.session_state.historique_llm = list(convs[0].get("historique_llm", []))
        except Exception:
            pass

    if not st.session_state.conversations:
        disc = _creer_discussion()
        if st.session_state.messages:
            disc["messages"] = list(st.session_state.messages)
            disc["historique_llm"] = list(st.session_state.historique_llm)
            disc["titre"] = _titre_discussion(disc["messages"])
        st.session_state.conversations = [disc]
        st.session_state.conversation_id = disc["id"]
    elif not st.session_state.conversation_id:
        st.session_state.conversation_id = st.session_state.conversations[0]["id"]

init()


def construire_filtres():
    filtres = {}
    if st.session_state.filtre_lang and st.session_state.filtre_lang != "Tous":
        filtres["langage"] = st.session_state.filtre_lang
    if st.session_state.get("filtre_repo", "").strip():
        filtres["repo"] = st.session_state.filtre_repo.strip()
    if st.session_state.get("filtre_stars", 0):
        filtres["stars_min"] = int(st.session_state.filtre_stars)
    if st.session_state.get("filtre_date", "").strip():
        filtres["date_min"] = st.session_state.filtre_date.strip()
    return filtres or None


def activer_recherche_web(actif: bool) -> None:
    """Active/désactive la recherche web (env + searchers en session)."""
    st.session_state.web_search_actif = bool(actif)
    os.environ["DESACTIVER_WEB_SEARCH"] = "false" if actif else "true"
    try:
        import generation.generateur_reponse as gr_mod
        gr_mod.WEB_SEARCH_DESACTIVE = not actif
    except Exception:
        pass
    for obj_name in ("generateur", "orchestrateur"):
        obj = st.session_state.get(obj_name)
        if obj is not None and getattr(obj, "searcher", None) is not None:
            try:
                obj.searcher.set_actif(actif)
            except Exception:
                try:
                    obj.searcher._desactive_runtime = not actif
                except Exception:
                    pass


def _est_source_enrichie(doc: dict) -> bool:
    return determiner_provenance(doc) != "github"


def afficher_sources(docs: list, msg_idx: int = 0):
    """Citations expert : [fichier:ligne], commits, score de confiance + favoris."""
    if not docs:
        return
    cols_fav = _favoris().lister_collections()
    col_ids = {c["nom"]: c["id"] for c in cols_fav}
    col_noms = list(col_ids.keys()) or ["Général"]
    for i, raw in enumerate(docs[:6], 1):
        doc = enrichir_document(raw)
        interne = _est_source_enrichie(doc)
        repo = (doc.get("section_titre") or "Guide interne") if interne else (doc.get("nom_complet") or "source")
        cite = doc.get("citation_courte") or citation_courte(doc)
        conf = doc.get("score_confiance")
        date = (doc.get("mis_a_jour_le") or "")[:10]
        conf_txt = f"{conf:.0%}" if isinstance(conf, (int, float)) else "—"
        blob = doc.get("url_blob") or ""
        commits = doc.get("url_commits") or ""
        label = f"**[{i}] {repo}**" if interne else f"**[{i}] {repo}** `{cite}`"
        meta_bits = [f"confiance {conf_txt}"]
        if interne:
            meta_bits.append("guide interne AssistDoc, hors GitHub")
        else:
            try:
                etoiles = int(doc.get("etoiles") or 0)
            except (TypeError, ValueError):
                etoiles = 0
            if etoiles:
                meta_bits.append(f"★ {etoiles:,} (GitHub, {DATE_COLLECTE_GITHUB})")
        if date:
            meta_bits.append(date)
        liens = []
        if blob:
            liens.append(f"[fichier]({blob})")
        if commits:
            liens.append(f"[commits]({commits})")
        lien_txt = (" · " + " · ".join(liens)) if liens else ""
        st.markdown(f"{label}{lien_txt}  \n`{' · '.join(meta_bits)}`")
        c1, c2 = st.columns([3, 2])
        with c1:
            cible = st.selectbox(
                "Collection",
                col_noms,
                key=f"fav_col_{msg_idx}_{i}",
                label_visibility="collapsed",
                disabled=not est_compte_connecte(),
            )
        with c2:
            if not est_compte_connecte():
                if st.button(
                    "★ Favori",
                    key=f"fav_btn_{msg_idx}_{i}",
                    use_container_width=True,
                ):
                    ouvrir_connexion()
                    notifier("Connectez-vous pour enregistrer un favori.", "info")
                    st.rerun()
            else:
                deja = _favoris().est_deja_favori(
                    repo, doc.get("source_file") or "", doc.get("section_titre") or ""
                )
                if st.button(
                    "★ Favori" if not deja else "★ OK",
                    key=f"fav_btn_{msg_idx}_{i}",
                    disabled=deja,
                    use_container_width=True,
                ):
                    try:
                        _favoris().ajouter_favori(doc, collection_id=col_ids.get(cible))
                    except Exception as exc:
                        message_erreur("Ajout du favori impossible", exc)
                        notifier("Le favori n'a pas pu être enregistré.", "erreur")
                    else:
                        notifier(f"Ajouté à « {cible} ».")
                    st.rerun()


@st.cache_resource(show_spinner=False)
def charger():
    # Import lourd différé : permet d'afficher l'UI « Initialisation… » avant torch/ST
    from core.orchestrateur import OrchestrateurAssistant

    orchestrateur = OrchestrateurAssistant()
    return orchestrateur.retrieval, orchestrateur, orchestrateur


def icone_fichier(nom: str) -> str:
    ext = Path(nom).suffix.lower()
    if ext == ".pdf":                          return "📄"
    if ext in {".docx", ".doc"}:               return "📘"
    if ext in {".xlsx",".xls",".csv",".tsv"}: return "📊"
    if ext in {".pptx"}:                      return "📽️"
    if ext in {".png",".jpg",".jpeg",".gif",".webp",".bmp"}: return "🖼️"
    if ext in {".wav",".mp3",".m4a",".ogg",".webm"}: return "🎤"
    if ext in {".py"}:                        return "🐍"
    if ext in {".js",".ts"}:                  return "🟨"
    if ext in {".java"}:                      return "☕"
    if ext in {".c",".cpp",".h"}:             return "⚙️"
    if ext in {".go"}:                        return "🐹"
    if ext in {".rs"}:                        return "🦀"
    if ext in {".md",".txt",".rst"}:          return "📝"
    if ext in {".json",".yaml",".yml",".toml"}: return "⚙️"
    return "📎"


def _afficher_piece_jointe(f: dict) -> None:
    """Pièce jointe dans la bulle utilisateur : aperçu, type, taille, avertissements."""
    infos = [p for p in (f.get("resume"), taille_lisible(f["taille"]) if f.get("taille") else "") if p]
    if f.get("type") == "image" and f.get("image_b64"):
        try:
            import base64 as _b64img

            st.image(_b64img.b64decode(f["image_b64"]), caption=f.get("nom") or "image",
                     use_container_width=True)
        except Exception:
            st.caption(f"🖼 {f.get('nom')}")
    if f.get("image_omise"):
        infos.append("image non conservée après rechargement")

    def _neutre(t: str) -> str:
        return re.sub(r"[\[\]`*_<>#|\\]", " ", str(t))

    lignes = []
    if not (f.get("type") == "image" and f.get("image_b64")):
        nom = str(f.get("nom", "fichier")).replace("`", "'")
        lignes.append(f"`{icone_fichier(nom)} {nom}`")
    if infos:
        lignes.append(f":gray[{_neutre(' · '.join(infos))}]")
    lignes += [f":orange[⚠ {_neutre(a)}]" for a in f.get("avertissements") or []]
    if lignes:
        st.markdown("  \n".join(lignes))


def _question_precedente(messages: list, idx: int) -> str:
    """Dernière question utilisateur avant le message idx (pour snapshot Admin)."""
    for i in range(idx - 1, -1, -1):
        m = messages[i] if 0 <= i < len(messages) else None
        if m and m.get("role") == "user" and (m.get("content") or "").strip():
            return str(m["content"]).strip()
    return ""


def _enregistrer_feedback_msg(msg_idx: int, note: int, commentaire: str = "") -> bool:
    """Enregistre 👍/👎 / signalement pour l'Admin (snapshot question + réponse)."""
    msgs = st.session_state.get("messages") or []
    if msg_idx < 0 or msg_idx >= len(msgs):
        return False
    msg = msgs[msg_idx] or {}
    question = (
        msg.get("question_origine")
        or _question_precedente(msgs, msg_idx)
        or ""
    )
    try:
        _db().enregistrer_feedback(
            st.session_state.conversation_id,
            msg_idx,
            note,
            commentaire,
            user_label=utilisateur_courant() or "invité",
            question=question,
            extrait_reponse=str(msg.get("content") or ""),
            mode=str(msg.get("mode") or ""),
        )
    except Exception:
        return False
    try:
        orch = st.session_state.get("orchestrateur")
        if orch is not None:
            orch.journaliser_feedback(
                question=question,
                mode=msg.get("mode") or "",
                note=note,
                score_rag=float(msg.get("score_rag") or 0),
                meta={"message_idx": msg_idx, "signalement": bool(commentaire)},
            )
    except Exception:
        pass
    return True


def _cle_widget_edition(role: str, msg_idx: int) -> str:
    return f"inline_edit_{role}_{msg_idx}"


def _ouvrir_edition_message(idx: int) -> bool:
    """Active le mode EDITING et précharge le texte dans session_state (pas via value=)."""
    msgs = st.session_state.get("messages") or []
    if idx < 0 or idx >= len(msgs):
        return False
    if _discussion_figee() or st.session_state.get("en_cours"):
        return False
    msg = msgs[idx]
    role = msg.get("role") or "user"
    if role != "user":
        # Édition assistant : correction locale uniquement
        pass
    cle = _cle_widget_edition(role, idx)
    st.session_state[cle] = msg.get("content") or ""
    st.session_state.edit_msg_idx = idx
    st.session_state["edit_draft_backup"] = msg.get("content") or ""
    return True


def _fermer_edition_message(*, restaurer: bool = False) -> None:
    idx = st.session_state.get("edit_msg_idx")
    msgs = st.session_state.get("messages") or []
    role = "user"
    if isinstance(idx, int) and 0 <= idx < len(msgs):
        role = msgs[idx].get("role") or "user"
        _vider_widget_edition(role, idx)
    st.session_state.edit_msg_idx = None
    st.session_state.pop("edit_draft_backup", None)
    if restaurer:
        # Le texte original reste dans messages[] ; le widget est vidé.
        pass


def _traiter_actions_url() -> None:
    """Lit ?edit_msg= / ?fb= envoyés par la toolbar HTML (postMessage)."""
    try:
        qp = st.query_params
    except Exception:
        return
    changed = False
    if "edit_msg" in qp:
        raw = qp.get("edit_msg")
        try:
            idx = int(raw if not isinstance(raw, list) else raw[0])
            if 0 <= idx < len(st.session_state.get("messages") or []):
                if st.session_state.get("edit_msg_idx") == idx:
                    _fermer_edition_message()
                else:
                    _ouvrir_edition_message(idx)
                changed = True
        except (TypeError, ValueError):
            pass
        try:
            del st.query_params["edit_msg"]
        except Exception:
            pass
    if "fb" in qp and "fb_idx" in qp:
        try:
            note_raw = qp.get("fb")
            idx_raw = qp.get("fb_idx")
            note = int(note_raw if not isinstance(note_raw, list) else note_raw[0])
            idx = int(idx_raw if not isinstance(idx_raw, list) else idx_raw[0])
            if note < 0:
                st.session_state["feedback_neg_idx"] = idx
                changed = True
            elif _enregistrer_feedback_msg(idx, note):
                notifier("Merci pour votre retour positif.")
                changed = True
        except Exception:
            pass
        for k in ("fb", "fb_idx"):
            try:
                del st.query_params[k]
            except Exception:
                pass
    if changed:
        st.rerun()


def _afficher_actions_message(msg_idx: int, contenu: str, role: str) -> None:
    """Toolbar : Copier (HTML) + Modifier (Streamlit, sans reload) + Feedback."""
    import json as _json

    figee = _discussion_figee()
    en_edition = st.session_state.get("edit_msg_idx") == msg_idx
    js_texte = _json.dumps(contenu or "")
    safe = f"{role}_{msg_idx}_{st.session_state.input_key}"
    safe = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in safe)
    align = "flex-end" if role == "user" else "flex-start"
    edit_bloque = figee or bool(st.session_state.get("en_cours"))

    ico_copy = (
        '<svg viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>'
        '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
    )
    ico_ok = '<svg viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></svg>'

    # En édition : pas de barre (Annuler / Envoyer suffisent).
    if not en_edition:
        rangee = st.container(
            horizontal=True,
            gap=None,
            vertical_alignment="center",
            horizontal_alignment="right" if role == "user" else "left",
            key=f"tbrow_{safe}",
        )
        with rangee:
            _toolbar_copie_html(safe, align, ico_copy, ico_ok, js_texte)
            if role == "user":
                if st.button(
                    "",
                    icon=":material/edit:",
                    key=f"edit_btn_{safe}",
                    help="Modifier",
                    type="tertiary",
                    disabled=edit_bloque,
                ):
                    if _ouvrir_edition_message(msg_idx):
                        st.rerun()
            if role == "assistant":
                _boutons_feedback(msg_idx, safe)

    _edition_inline(msg_idx, contenu, role, en_edition, figee)


def _toolbar_copie_html(safe, align, ico_copy, ico_ok, js_texte) -> None:
    """Bouton Copier seul (iframe) — Edit est un bouton Streamlit pour éviter le reload."""
    components.html(
        f"""
        <style>
          html, body {{
            margin: 0; padding: 0;
            background: transparent !important;
            overflow: hidden;
          }}
          .tb-{safe} {{
            display: flex;
            align-items: center;
            justify-content: {align};
            gap: 0;
            margin: 0;
            padding: 0;
            height: 28px;
            width: fit-content;
            max-width: 100%;
          }}
          .tb-{safe} .tb-btn {{
            width: 28px; height: 28px;
            padding: 0; margin: 0;
            border: none; border-radius: 8px;
            background: transparent;
            color: #b0aea5;
            display: inline-flex;
            align-items: center; justify-content: center;
            cursor: pointer;
            flex: 0 0 28px;
          }}
          .tb-{safe} .tb-btn:hover {{
            background: rgba(255,255,255,0.08);
            color: #f5f4ef;
          }}
          .tb-{safe} .tb-btn svg {{
            width: 15px; height: 15px;
            stroke: currentColor; fill: none;
            stroke-width: 1.75;
            stroke-linecap: round; stroke-linejoin: round;
            display: block;
          }}
        </style>
        <div class="tb-{safe}">
          <button class="tb-btn" id="cpy_{safe}" title="Copier" type="button">{ico_copy}</button>
        </div>
        <script>
        (function() {{
          const cpy = document.getElementById("cpy_{safe}");
          const okIcon = `{ico_ok}`;
          const copyIcon = `{ico_copy}`;
          if (cpy) {{
            cpy.onclick = async function() {{
              try {{
                await navigator.clipboard.writeText({js_texte});
                cpy.innerHTML = okIcon;
                cpy.style.color = "#7dcea0";
                setTimeout(function() {{
                  cpy.innerHTML = copyIcon;
                  cpy.style.color = "";
                }}, 1100);
              }} catch (e) {{
                cpy.title = "Copie impossible";
              }}
            }};
          }}
        }})();
        </script>
        """,
        width=32,
        height=30,
    )


def _boutons_feedback(msg_idx: int, safe: str) -> None:
    deja = st.session_state.setdefault("feedback_envoye", [])
    if not isinstance(deja, list):
        deja = list(deja)
        st.session_state.feedback_envoye = deja
    fb_key = f"{st.session_state.conversation_id}:{msg_idx}"
    disabled = fb_key in deja
    if st.button(
        "",
        icon=":material/thumb_up:",
        key=f"fb_up_{safe}",
        help="Utile — visible dans Admin",
        type="tertiary",
        disabled=disabled,
    ):
        if _enregistrer_feedback_msg(msg_idx, 1):
            deja.append(fb_key)
            notifier("Merci pour votre retour positif.")
            st.rerun()
        else:
            notifier("Votre avis n'a pas pu être enregistré.", "erreur")
            st.rerun()
    if st.button(
        "",
        icon=":material/thumb_down:",
        key=f"fb_dn_{safe}",
        help="Pas utile — précisez le problème",
        type="tertiary",
        disabled=disabled,
    ):
        st.session_state["feedback_neg_idx"] = msg_idx
        st.rerun()


def _fermer_dialog_feedback_neg() -> None:
    st.session_state.pop("feedback_neg_idx", None)


@st.dialog("Qu’est-ce qui n’a pas convenu ?", width="small", on_dismiss=_fermer_dialog_feedback_neg)
def _dialog_feedback_negatif() -> None:
    idx = st.session_state.get("feedback_neg_idx")
    if not isinstance(idx, int):
        st.session_state.pop("feedback_neg_idx", None)
        st.rerun()
        return
    st.caption("Votre retour aide à améliorer AssistDoc. Le détail reste visible côté administration.")
    commentaire = st.text_area(
        "Précisez le problème (optionnel)",
        key=f"fb_neg_comment_{idx}",
        height=100,
        placeholder="Ex. : réponse incomplète, mauvaise source, hors sujet…",
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Annuler", key=f"fb_neg_cancel_{idx}", use_container_width=True):
            _fermer_dialog_feedback_neg()
            st.rerun()
    with c2:
        if st.button("Envoyer", key=f"fb_neg_ok_{idx}", type="primary", use_container_width=True):
            deja = st.session_state.setdefault("feedback_envoye", [])
            fb_key = f"{st.session_state.conversation_id}:{idx}"
            if _enregistrer_feedback_msg(idx, -1, (commentaire or "").strip()):
                if fb_key not in deja:
                    deja.append(fb_key)
                _fermer_dialog_feedback_neg()
                notifier("Merci, votre retour a été enregistré.")
                st.rerun()
            else:
                notifier("Votre avis n'a pas pu être enregistré.", "erreur")


def afficher_dialog_feedback_si_besoin() -> None:
    if isinstance(st.session_state.get("feedback_neg_idx"), int):
        _dialog_feedback_negatif()


def _vider_widget_edition(role: str, msg_idx: int) -> None:
    prefix = _cle_widget_edition(role, msg_idx)
    for k in list(st.session_state.keys()):
        if str(k) == prefix or str(k).startswith(prefix + "_"):
            del st.session_state[k]
        if str(k).startswith(f"edit_form_{role}_{msg_idx}"):
            del st.session_state[k]


def _lire_texte_edition(role: str, msg_idx: int) -> str:
    """Lit la valeur réelle du widget (session_state), pas une copie obsolète."""
    cle = _cle_widget_edition(role, msg_idx)
    return str(st.session_state.get(cle) or "").strip()


def _hauteur_editeur(contenu: str, *, regenerer: bool = True) -> int:
    """Hauteur initiale proportionnelle au texte (le JS affine ensuite)."""
    texte = contenu or ""
    lignes = 1
    for ligne in texte.splitlines() or [""]:
        lignes += max(1, (len(ligne) // 52) + 1)
    if not texte:
        lignes = 1
    lignes = max(1, min(lignes, 12))
    base = 40 + lignes * 22
    return int(min(320, max(68 if regenerer else 88, base)))


def _edition_inline(msg_idx: int, contenu: str, role: str, en_edition: bool, figee: bool) -> None:
    """Éditeur inline via st.form : text_area + boutons soumis atomiquement.

    Cause racine corrigée : ne plus passer value= en parallèle de key= (réinitialise /
    désynchronise le widget), et soumettre via form pour que Streamlit envoie
    impérativement la dernière saisie avec le clic Envoyer / Entrée.
    """
    if not en_edition or figee or st.session_state.get("en_cours"):
        return

    regenerer = role == "user"
    cle = _cle_widget_edition(role, msg_idx)
    if cle not in st.session_state:
        st.session_state[cle] = contenu or ""
    hauteur = _hauteur_editeur(str(st.session_state.get(cle) or contenu or ""), regenerer=regenerer)

    with st.container(key=f"edit_box_{role}_{msg_idx}"):
        with st.form(key=f"edit_form_{role}_{msg_idx}", border=False):
            st.text_area(
                "Modifier le prompt" if regenerer else "Éditer le message",
                height=hauteur,
                key=cle,
                label_visibility="collapsed",
                placeholder="Modifiez votre message… Entrée pour envoyer, Maj+Entrée pour une nouvelle ligne.",
            )
            s_annuler, s_ok = st.columns(2, gap="small")
            with s_annuler:
                annuler = st.form_submit_button(
                    "Annuler",
                    use_container_width=True,
                )
            with s_ok:
                valider = st.form_submit_button(
                    "Envoyer" if regenerer else "Enregistrer",
                    type="primary",
                    use_container_width=True,
                )

        if annuler:
            _fermer_edition_message(restaurer=True)
            st.rerun()

        if valider:
            texte = _lire_texte_edition(role, msg_idx)
            if not texte:
                # Restaurer le brouillon pour ne pas perdre la saisie à l'écran
                if cle not in st.session_state or not str(st.session_state.get(cle) or "").strip():
                    st.session_state[cle] = st.session_state.get("edit_draft_backup") or contenu or ""
                afficher_erreur("Le message ne peut pas être vide.")
            elif regenerer:
                if modifier_prompt_et_regenerer(msg_idx, texte):
                    _vider_widget_edition(role, msg_idx)
                    st.session_state.pop("edit_draft_backup", None)
                    st.rerun()
                else:
                    afficher_erreur("Le prompt n'a pas pu être modifié. Réessayez.")
            elif modifier_message(msg_idx, texte):
                _fermer_edition_message()
                notifier("Message mis à jour.")
                st.rerun()
            else:
                afficher_erreur("Le message n'a pas pu être modifié.")


def url_valide(doc: dict) -> bool:
    """Vrai seulement si le doc a une URL GitHub exploitable."""
    url = doc.get("url", "")
    return isinstance(url, str) and url.startswith("http")


# ── SIDEBAR ───────────────────────────────────────────────────────
# Branding : st.logo() en tête de page (tout en haut de la sidebar)
with st.sidebar:
    barre_compte_sidebar()

    if st.button(
        "Nouvelle conversation",
        icon=":material/add:",
        use_container_width=True,
        key="btn_new_chat",
        type="primary",
    ):
        nouvelle_discussion()
        st.rerun()

    # Outils en haut (Paramètres / Favoris / Export) — avant la liste des discussions
    with st.expander("Paramètres", expanded=False):
        st.session_state.filtre_lang = st.selectbox(
            "Langage",
            ["Tous","Python","JavaScript","TypeScript","Java","Go","Rust","C","C++","PHP","Ruby"],
            key="sel_lang"
        )
        st.session_state.filtre_repo = st.text_input(
            "Dépôt (ex. tiangolo/fastapi)",
            value=st.session_state.get("filtre_repo", ""),
            key="sel_repo",
        )
        st.session_state.filtre_stars = st.number_input(
            "Étoiles minimum", min_value=0, max_value=500000,
            value=int(st.session_state.get("filtre_stars", 0) or 0),
            step=100, key="sel_stars",
        )
        try:
            _date_init = date.fromisoformat(st.session_state.get("filtre_date") or "")
        except ValueError:
            _date_init = None
        _date_min = st.date_input(
            "Mis à jour après",
            value=_date_init,
            min_value=date(2008, 1, 1),
            max_value=date.today(),
            format="YYYY-MM-DD",
            key="sel_date_min",
            help="Laisser vide pour ne pas filtrer par date",
        )
        st.session_state.filtre_date = _date_min.isoformat() if isinstance(_date_min, date) else ""
        st.session_state.top_k = st.slider("Nombre de sources", 3, 10, 5, key="topk")
        st.session_state.utiliser_corpus_avec_fichier = st.toggle(
            "Fichier + corpus ensemble",
            value=st.session_state.get("utiliser_corpus_avec_fichier", True),
            key="tog_corpus_fichier",
        )

    with st.expander("Favoris & collections", expanded=False):
        if not est_compte_connecte():
            st.caption("Connectez-vous pour enregistrer des favoris et collections.")
        else:
            cols = _favoris().lister_collections()
            par_id = {c["id"]: c for c in cols}
            defaut_id = _favoris().collection_defaut_id()
            if st.session_state.get("sel_collection_fav") not in par_id:
                st.session_state.pop("sel_collection_fav", None)
            choix_id = st.selectbox(
                "Collection",
                list(par_id),
                format_func=lambda i: f"{par_id[i]['nom']} ({par_id[i]['nb']})",
                key="sel_collection_fav",
            )
            if choix_id and choix_id != defaut_id:
                if st.button(
                    "Supprimer la collection",
                    key="danger_btn_del_collection",
                    type="tertiary",
                    icon=":material/delete:",
                    help="Supprime la collection et ses favoris (après confirmation)",
                ):
                    demander_confirmation(CLE_SUPPR_COLLECTION, (choix_id, par_id[choix_id]["nom"]))
                    st.rerun()
            noms_existants = {c["nom"].strip().casefold() for c in cols}
            with st.form("form_new_collection", clear_on_submit=False, border=False):
                nouveau_nom = st.text_input(
                    "Nouvelle collection", max_chars=80, placeholder="Nom de la collection"
                )
                creer = st.form_submit_button("Créer la collection", use_container_width=True)
            if creer:
                nom = (nouveau_nom or "").strip()
                if not nom:
                    afficher_erreur("Indiquez un nom de collection.")
                elif nom.casefold() in noms_existants:
                    afficher_erreur("Une collection porte déjà ce nom.")
                else:
                    try:
                        _favoris().creer_collection(nom)
                    except Exception as exc:
                        afficher_erreur("La collection n'a pas pu être créée.", exc)
                    else:
                        notifier("Collection créée.")
                        st.rerun()
            favs = _favoris().lister_favoris(choix_id) if choix_id else []
            if not favs:
                st.caption("Aucun favori dans cette collection.")
            for fav in favs[:30]:
                titre = fav.get("nom_complet") or "source"
                cite = fav.get("citation") or fav.get("section_titre") or ""
                st.markdown(f"**{titre}**  \n`{cite}`")
                if fav.get("url"):
                    st.markdown(f"[ouvrir]({fav['url']})")
                if fav.get("extrait"):
                    st.caption((fav["extrait"] or "")[:160] + "…")
                if st.button(
                    "Retirer des favoris",
                    key=f"rm_fav_{fav['id']}",
                    type="tertiary",
                    icon=":material/bookmark_remove:",
                ):
                    try:
                        retire = _favoris().supprimer_favori(fav["id"])
                    except Exception as exc:
                        retire = False
                        message_erreur("Retrait du favori impossible", exc)
                    if retire:
                        notifier("Favori retiré.")
                    else:
                        notifier("Le favori n'a pas pu être retiré.", "erreur")
                    st.rerun()
                st.divider()

    # Discussions (titre = 1er message) ; la courante vide reste visible
    discussions = [
        c for c in st.session_state.conversations
        if c.get("messages") or c.get("figee") or c["id"] == st.session_state.conversation_id
    ]
    # Figées en tête
    discussions = sorted(
        discussions,
        key=lambda x: (0 if x.get("figee") else 1, -(1 if x["id"] == st.session_state.conversation_id else 0)),
    )
    if st.session_state.pop("_fermer_menus", False):
        for _k in [k for k in st.session_state if str(k).startswith("menu_disc_")]:
            st.session_state[_k] = False
    if discussions:
        st.markdown('<div class="sb-section"><div class="sb-section-title">Discussions</div></div>', unsafe_allow_html=True)
        for c in discussions:
            titre = c.get("titre") or "Nouvelle discussion"
            actif = c["id"] == st.session_state.conversation_id
            figee = bool(c.get("figee"))
            label = ("🔒 " if figee else "") + titre
            row = st.columns([9, 1], gap="small")
            with row[0]:
                if st.button(
                    label,
                    key=f"disc_actif_{c['id']}" if actif else f"disc_{c['id']}",
                    use_container_width=True,
                    help=titre + (" (discussion ouverte)" if actif else ""),
                ):
                    charger_discussion(c["id"])
                    st.rerun()
            with row[1]:
                with st.popover(
                    "⋯",
                    help=f"Actions sur « {titre[:40]} »",
                    key=f"menu_disc_{c['id']}",
                    on_change=lambda: None,
                ):
                    if st.button(
                        "Renommer",
                        key=f"ren_{c['id']}",
                        icon=":material/edit:",
                        use_container_width=True,
                        disabled=figee,
                        help="Défigez la discussion pour la renommer" if figee else None,
                    ):
                        demander_confirmation(CLE_RENOMMER_DISCUSSION, c["id"])
                        st.session_state["_fermer_menus"] = True
                        st.rerun()
                    if st.button(
                        "Défiger" if figee else "Figer",
                        key=f"fig_{c['id']}",
                        icon=":material/lock_open:" if figee else ":material/lock:",
                        use_container_width=True,
                        help="Une discussion figée ne peut être ni modifiée ni supprimée",
                    ):
                        if basculer_figee(c["id"]):
                            notifier("Discussion défigée." if figee else "Discussion figée.")
                        else:
                            notifier("Le changement n'a pas pu être enregistré.", "erreur")
                        st.session_state["_fermer_menus"] = True
                        st.rerun()
                    if st.button(
                        "Supprimer",
                        key=f"danger_del_{c['id']}",
                        icon=":material/delete:",
                        use_container_width=True,
                        disabled=figee,
                        help="Défigez la discussion pour la supprimer" if figee else None,
                    ):
                        demander_confirmation(CLE_SUPPR_DISCUSSION, c["id"])
                        st.session_state["_fermer_menus"] = True
                        st.rerun()

    # Export juste au-dessus du bloc connexion / déconnexion
    if st.session_state.messages:
        titre_export = _titre_discussion(st.session_state.messages)
        cid = st.session_state.conversation_id
        md = export_markdown(
            st.session_state.messages,
            conversation_id=cid,
            titre=titre_export,
        )
        safe_name = re.sub(r"[^\w\-]+", "_", titre_export)[:40].strip("_") or "conversation"
        boite_export = st.container(key="sb_export_box")
        boite_export.markdown('<div class="sb-export-title">Exporter</div>', unsafe_allow_html=True)
        c_md, c_pdf = boite_export.columns(2, gap="small")
        with c_md:
            st.download_button(
                ".md",
                data=md.encode("utf-8"),
                file_name=f"AssistDoc_{safe_name}.md",
                mime="text/markdown; charset=utf-8",
                use_container_width=True,
                key="btn_export_md",
                help="Télécharger en Markdown",
            )
        with c_pdf:
            try:
                pdf_bytes = export_pdf(
                    st.session_state.messages,
                    titre=titre_export,
                    conversation_id=cid,
                )
                st.download_button(
                    "Pdf",
                    data=pdf_bytes,
                    file_name=f"AssistDoc_{safe_name}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key="btn_export_pdf",
                    help="Télécharger en PDF",
                )
            except Exception as exc:
                st.caption(message_erreur("PDF indisponible pour cette conversation.", exc))

    # Auth en bas de sidebar
    _u_sb = utilisateur_session()
    if _u_sb:
        st.divider()
        if est_admin_session():
            st.caption("Menu **Admin** disponible en haut de la barre latérale.")
        if (_u_sb.get("tier") or "guest") == "guest":
            st.markdown(
                """
                <div class="sb-promo">
                  <div class="sb-promo-title">Obtenez des réponses personnalisées</div>
                  <div class="sb-promo-text">
                    Connectez-vous pour obtenir des réponses sur la base des chats
                    enregistrés, créer des images et charger des fichiers.
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("Se connecter", key="sb_login", use_container_width=True):
                ouvrir_connexion()
                st.rerun()
        else:
            if st.button(
                "Se déconnecter",
                key="btn_logout",
                icon=":material/logout:",
                use_container_width=True,
            ):
                deconnecter()
                notifier("Vous êtes déconnecté.", "info")
                st.rerun()


# ── Chargement ────────────────────────────────────────────────────
if not st.session_state.pret:
    ph = st.empty()
    ph.markdown("""
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:60vh;gap:16px;">
        <div style="width:40px;height:40px;border-radius:50%;background:linear-gradient(145deg,#5b9fd4,#3b7eb0);
                    display:flex;align-items:center;justify-content:center;font-size:15px;color:#fff;font-weight:600;">A</div>
        <div style="font-size:14px;color:#8a877c;">Initialisation…</div>
    </div>
    """, unsafe_allow_html=True)
    try:
        m, g, o = charger()
        st.session_state.moteur     = m
        st.session_state.generateur = g
        st.session_state.orchestrateur = o
        st.session_state.pret       = True
        ph.empty()
        st.rerun()
    except Exception as e:
        ph.error(
            message_erreur(
                "L'assistant n'a pas pu démarrer (base documentaire ou modèle indisponible).",
                e,
                "Rechargez la page dans un instant ; si le problème persiste, contactez l'administrateur.",
            ),
            icon=":material/error:",
        )
        st.stop()


def _html_reflexion(label: str) -> str:
    """Indicateur compact affiché dans le seul bloc assistant en cours."""
    return (
        '<div class="thinking-inline">'
        '<div class="tdots"><span></span><span></span><span></span></div>'
        f'<div class="tlabel">{html_lib.escape(label)}</div>'
        "</div>"
    )


_traiter_actions_url()

# Suggestion cliquée : démarrer tout de suite (évite le flash des chips d'accueil)
_pending_sug = (st.session_state.pop("_sug", None) or "").strip()
if _pending_sug and not st.session_state.en_cours:
    st.session_state.messages.append({
        "role": "user",
        "content": _pending_sug,
        "fichiers": list(st.session_state.fichiers_en_attente),
    })
    st.session_state.historique_llm.append({"role": "user", "content": _pending_sug})
    st.session_state.fichiers_en_attente = []
    st.session_state.input_key += 1
    st.session_state.en_cours = True
    sync_discussion()
    st.rerun()

# ── TOPBAR (auth via sidebar uniquement) ─────────────────────────
st.markdown("""
<div class="topbar">
    <span class="topbar-l">AssistDoc <span class="chev">▾</span></span>
    <span class="topbar-r">Documentation GitHub</span>
</div>
""", unsafe_allow_html=True)
afficher_dialog_auth_si_besoin()
afficher_dialog_suppression_si_besoin()
afficher_dialog_feedback_si_besoin()


# ── CHAT ──────────────────────────────────────────────────────────
col = st.columns([1, 12, 1])[1]
zone_reponse_en_cours = None  # rempli si génération en cours (slot avant composer)

with col:
    st.markdown('<div class="chat-wrap">', unsafe_allow_html=True)

    if not st.session_state.messages and not st.session_state.en_cours:
        if _LOGO_FILE.exists():
            import base64 as _b64

            _wlogo = _b64.b64encode(_LOGO_FILE.read_bytes()).decode("ascii")
            _wicon_html = (
                f'<img class="wicon" src="data:image/png;base64,{_wlogo}" alt="AssistDoc" />'
            )
        else:
            _wicon_html = '<div class="wicon-fallback">A</div>'
        st.markdown(
            f"""
        <div class="welcome">
            {_wicon_html}
            <div class="wtitle">Bonjour, je suis AssistDoc</div>
            <div class="wsub">
                Posez une question technique ou joignez un fichier<br>
                pour l’analyser ensemble.
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

        suggestions = [
            "Créer une API REST avec Flask",
            "Implémenter l'authentification JWT",
            "Comprendre les hooks React",
            "Containeriser une app avec Docker",
            "SQLAlchemy avec PostgreSQL",
            "Démarrer une API FastAPI",
        ]
        cs = st.columns(2)
        for i, sug in enumerate(suggestions):
            with cs[i % 2]:
                if st.button(sug, key=f"sug_{i}", use_container_width=True):
                    st.session_state["_sug"] = sug + " ?"
                    st.rerun()

    edit_actif = st.session_state.get("edit_msg_idx")
    for msg_idx, msg in enumerate(st.session_state.messages):
        # Pendant l'édition d'un prompt : masquer la branche suivante (réponses obsolètes)
        if (
            isinstance(edit_actif, int)
            and msg_idx > edit_actif
            and not st.session_state.get("en_cours")
        ):
            continue
        if msg["role"] == "user":
            fichiers_msg = msg.get("fichiers", [])
            en_edition = (
                edit_actif == msg_idx
                and not _discussion_figee()
                and not st.session_state.get("en_cours")
            )
            with st.container(key=f"msg_user_{msg_idx}_{st.session_state.input_key}"):
                if en_edition:
                    # Remplace la bulle par l'éditeur (style ChatGPT)
                    _afficher_actions_message(msg_idx, msg.get("content", ""), "user")
                else:
                    with st.chat_message("user"):
                        for f in fichiers_msg or []:
                            _afficher_piece_jointe(f)
                        st.markdown(msg["content"])
                    _afficher_actions_message(msg_idx, msg.get("content", ""), "user")
        else:
            docs    = msg.get("docs", [])
            sans_sources = msg.get("sans_sources", False)
            abstention = msg.get("abstention", False)
            nb_web = int(msg.get("nb_sources_web") or 0)
            score_rag_msg = msg.get("score_rag")

            with st.container(key=f"msg_assistant_{msg_idx}_{st.session_state.input_key}"):
                with st.chat_message("assistant"):
                    st.markdown(nettoyer_reponse(msg["content"]))
                    for img in msg.get("images") or []:
                        b64 = img.get("b64")
                        if not b64:
                            continue
                        try:
                            import base64 as _b64img

                            st.image(
                                _b64img.b64decode(b64),
                                caption=img.get("caption") or "Image générée",
                                use_container_width=True,
                            )
                        except Exception:
                            st.caption("(image indisponible)")
                    _afficher_actions_message(msg_idx, msg.get("content", ""), "assistant")

                docs_valides = [] if sans_sources else list(docs or [])
                nb_sources = len(docs_valides)
                conf_moy = 0.0
                if isinstance(score_rag_msg, (int, float)) and score_rag_msg > 0:
                    conf_moy = float(score_rag_msg)
                elif docs_valides:
                    confs = [d.get("score_confiance") for d in docs_valides if isinstance(d.get("score_confiance"), (int, float))]
                    conf_moy = sum(confs) / len(confs) if confs else 0.0

                # Métadonnées utiles uniquement (pas de tokens ni de mode modèle)
                meta_parts = []
                if not sans_sources:
                    if nb_sources:
                        meta_parts.append(f"corpus {nb_sources}")
                    if nb_web:
                        meta_parts.append(f"web {nb_web}")
                    if conf_moy:
                        meta_parts.append(f"confiance {conf_moy:.0%}")
                if abstention:
                    meta_parts.append("abstention")
                if meta_parts:
                    st.caption(" · ".join(meta_parts))

                if docs_valides:
                    with st.expander("Sources & confiance", expanded=False):
                        afficher_sources(docs_valides, msg_idx=msg_idx)

                with st.expander("Signaler une erreur", expanded=False):
                    motif = st.text_area(
                        "Décrivez le problème (hallucination, mauvaise source, bug…)",
                        key=f"signal_{msg_idx}",
                        height=80,
                        placeholder="Ex. : la citation ne correspond pas à la réponse…",
                    )
                    cle_envoye = f"signal_envoye:{st.session_state.conversation_id}:{msg_idx}"
                    deja_signale = bool(st.session_state.get(cle_envoye))
                    if deja_signale:
                        st.caption("Signalement transmis à l'administrateur. Merci.")
                    if st.button(
                        "Envoyer le signalement",
                        key=f"btn_signal_{msg_idx}",
                        disabled=deja_signale,
                    ):
                        texte = (motif or "").strip()
                        if not texte:
                            afficher_avertissement("Décrivez le problème en quelques mots.")
                        elif _enregistrer_feedback_msg(
                            msg_idx, -1, f"[signalement] {texte}"
                        ):
                            st.session_state[cle_envoye] = True
                            notifier("Signalement envoyé. Merci.")
                            st.rerun()
                        else:
                            afficher_erreur("Le signalement n'a pas pu être enregistré. Réessayez.")

    # Emplacement unique de la réponse en cours — dans le fil, avant le composer
    if (
        st.session_state.en_cours
        and st.session_state.messages
        and st.session_state.messages[-1]["role"] == "user"
    ):
        with st.container(key=f"msg_assistant_pending_{st.session_state.input_key}"):
            with st.chat_message("assistant"):
                zone_reponse_en_cours = st.empty()
                zone_reponse_en_cours.markdown(
                    _html_reflexion("Réflexion en cours…"),
                    unsafe_allow_html=True,
                )

    st.markdown('</div>', unsafe_allow_html=True)


# ── COMPOSER (st.chat_input : Entrée envoie, Maj+Entrée = retour à la ligne) ──
def _journal_securite(action: str, gravite: str, details: str) -> None:
    u = utilisateur_session() or {}
    _users_db_auth().evenement_securite(action, gravite, details, acteur=u.get("id") or "")


def _joindre_fichiers(fichiers_up) -> list:
    """Pièces jointes soumises → fichiers traités ; les refusés sont signalés, jamais joints."""
    joints = []
    fichiers_up = list(fichiers_up or [])
    # Le widget masque l'import aux invités ; le serveur le refuse aussi (requête forgée)
    if fichiers_up and not est_compte_connecte():
        _journal_securite("fichier_refuse", "moyenne", f"{len(fichiers_up)} fichier(s) envoyé(s) sans compte")
        notifier("Connectez-vous pour joindre des fichiers.", "erreur")
        return joints
    if len(fichiers_up) > FICHIERS_MAX_PAR_MESSAGE:
        notifier(
            f"{len(fichiers_up) - FICHIERS_MAX_PAR_MESSAGE} fichier(s) ignoré(s) : "
            f"au plus {FICHIERS_MAX_PAR_MESSAGE} pièces jointes par message.",
            "avertissement",
        )
        fichiers_up = fichiers_up[:FICHIERS_MAX_PAR_MESSAGE]
    if not fichiers_up:
        return joints
    with st.spinner("Lecture des pièces jointes…"):
        for f in fichiers_up:
            t = traiter_fichier(f)
            if t.get("erreur"):
                _journal_securite(
                    "fichier_refuse", "faible",
                    f"Extension {Path(t['nom']).suffix.lower() or '(aucune)'} · "
                    f"{taille_lisible(t.get('taille') or 0)} · {t['erreur'][:160]}",
                )
                notifier(f"« {t['nom']} » non joint : {t['erreur']}", "erreur")
            elif all(j["nom"] != t["nom"] for j in joints):
                joints.append(t)
    return joints


def _transcrire(audio) -> str:
    if not est_compte_connecte():
        _journal_securite("fichier_refuse", "moyenne", "Audio envoyé sans compte")
        notifier("Connectez-vous pour dicter une question.", "erreur")
        return ""
    with st.spinner("Transcription audio…"):
        try:
            return (transcrire_audio(audio) or "").strip()
        except Exception as exc:
            notifier(
                message_erreur("La transcription a échoué.", exc, "Réessayez ou saisissez votre question."),
                "erreur",
            )
            return ""


connecte = est_compte_connecte()
# Quota épuisé : la saisie reste possible, le serveur refuse la requête et propose la connexion
composer_occupe = st.session_state.en_cours

with col:
    web_actif = bool(st.session_state.web_search_actif)
    with st.container(horizontal=True, gap="small", vertical_alignment="center", key="composer_outils"):
        if st.button(
            "Recherche web",
            key="btn_web_on" if web_actif else "btn_web_off",
            icon=":material/check_circle:" if web_actif else ":material/language:",
            type="tertiary",
            help="Recherche web activée — cliquer pour la désactiver"
            if web_actif
            else "Compléter les réponses par une recherche web",
            disabled=st.session_state.en_cours,
        ):
            activer_recherche_web(not web_actif)
            st.rerun()
        if not connecte:
            if st.button(
                "Joindre un fichier",
                key="plus_need_login",
                icon=":material/attach_file:",
                type="tertiary",
                help="Fichiers, images et audio réservés aux comptes connectés",
            ):
                ouvrir_connexion()
                st.rerun()

    saisie = st.chat_input(
        "Génération en cours…" if st.session_state.en_cours else "Poser une question…",
        key=f"composer_{st.session_state.input_key}",
        accept_file="multiple" if connecte else False,
        # Les formats refusés restent sélectionnables : traiter_fichier() explique le refus au lieu d'un rejet muet
        file_type=sorted(e.lstrip(".") for e in UPLOAD_EXTENSIONS_OK | set(UPLOAD_FORMATS_REFUSES)) if connecte else None,
        max_upload_size=max(1, UPLOAD_MAX_BYTES // (1024 * 1024)) if connecte else None,
        accept_audio=connecte,
        disabled=composer_occupe,
    )

    st.markdown(
        '<div class="composer-hint">AssistDoc peut se tromper. Vérifiez les informations importantes.</div>',
        unsafe_allow_html=True,
    )


# ── TRAITEMENT ────────────────────────────────────────────────────
q_finale, fichiers_soumis = "", []
if saisie is not None and not composer_occupe:
    if isinstance(saisie, str):
        q_finale = saisie.strip()
    else:
        q_finale = (saisie.text or "").strip()
        fichiers_soumis = _joindre_fichiers(saisie.files)
        if saisie.audio is not None:
            q_finale = " ".join(p for p in (q_finale, _transcrire(saisie.audio)) if p)
        if not q_finale and fichiers_soumis:
            q_finale = "Analyse le contenu des fichiers joints."
    if not q_finale:
        # Rien d'exploitable (fichiers refusés, audio vide) : afficher les notifications
        st.rerun()

if q_finale and not st.session_state.en_cours:
    q        = q_finale
    fichiers = st.session_state.fichiers_en_attente + fichiers_soumis

    st.session_state.messages.append({
        "role": "user", "content": q, "fichiers": fichiers
    })
    st.session_state.historique_llm.append({"role": "user", "content": q})
    st.session_state.fichiers_en_attente = []
    st.session_state.input_key          += 1
    st.session_state.en_cours            = True
    sync_discussion()
    st.rerun()


# ── GÉNÉRATION ────────────────────────────────────────────────────
# Un seul emplacement assistant : réflexion → stream/réponse → historique.
# La zone (st.empty) a été créée dans le fil de messages, avant le composer.
if st.session_state.en_cours and st.session_state.messages:
    users = [m for m in st.session_state.messages if m["role"] == "user"]
    if not users:
        st.session_state.en_cours = False
        st.stop()

    if st.session_state.messages[-1]["role"] == "assistant":
        st.session_state.en_cours = False
        st.rerun()

    dernier_user = users[-1]
    q            = dernier_user["content"]
    fichiers_msg = dernier_user.get("fichiers", [])
    a_un_fichier = bool(fichiers_msg)
    # Question de suivi sans pièce jointe : les documents du message précédent restent en contexte
    fichiers_contexte = fichiers_msg or fichiers_de_rappel(st.session_state.messages)

    contexte_fichiers = formater_pour_prompt(fichiers_msg, question=q, avec_regles=False)

    q_enrichie = q
    if contexte_fichiers:
        q_enrichie = (
            q + "\n\n[Fichiers joints par l'utilisateur — base ta réponse "
            "PRINCIPALEMENT sur leur contenu ci-dessous :]\n" + contexte_fichiers
        )

    filtres = construire_filtres()

    # Réutilise l'emplacement créé dans le fil (avant le composer) — pas de 2e bulle.
    zone_reponse = zone_reponse_en_cours
    if zone_reponse is None:
        with col:
            with st.container(key=f"msg_assistant_fallback_{st.session_state.input_key}"):
                with st.chat_message("assistant"):
                    zone_reponse = st.empty()

    def _afficher_reflexion(label: str) -> None:
        zone_reponse.markdown(_html_reflexion(label), unsafe_allow_html=True)

    try:
        t0 = time.time()
        # Un rerun pendant la génération (clic, fragment) ne doit pas décompter la question deux fois
        if dernier_user.get("quota_decompte"):
            ok_quota, msg_quota = True, ""
        else:
            ok_quota, msg_quota = consommer_requete(
                {"question": (q or "")[:200], "avec_fichier": a_un_fichier}
            )
            dernier_user["quota_decompte"] = ok_quota
        if not ok_quota:
            if st.session_state.historique_llm and st.session_state.historique_llm[-1].get("role") == "user":
                st.session_state.historique_llm.pop()
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"⏳ {msg_quota}",
                "docs": [], "tokens": 0, "latence": 0,
                "avec_fichier": a_un_fichier,
                "sans_sources": True, "abstention": False,
                "mode": "quota",
            })
            sync_discussion()
            st.session_state.en_cours = False
            st.rerun()

        # Signal pour la supervision uniquement : la question n'est ni bloquée ni modifiée
        for _source, _texte in [("question", q)] + [
            (f"fichier {Path(f.get('nom') or '').suffix.lower()}", f.get("contenu") or "") for f in fichiers_msg
        ]:
            _motifs = detecter_injection(_texte)
            if _motifs:
                _journal_securite(
                    "ia_injection_suspecte", "moyenne",
                    f"Source : {_source} · " + ", ".join(_LIBELLES_INJECTION[m] for m in _motifs),
                )

        salutation = (not a_un_fichier) and est_salutation(q)

        mode_force = None
        utiliser_corpus = bool(st.session_state.get("utiliser_corpus_avec_fichier", True))
        if salutation:
            mode_force = "texte"
        elif est_cahier_des_charges(q) or est_cahier_des_charges(q_enrichie):
            mode_force = "cdc"
        elif est_demande_projet(q):
            mode_force = "projet"
        elif a_un_fichier:
            # Avec corpus : laisser le classificateur + forcer RAG côté orchestrateur
            # Sans corpus : mode texte (fichier seul) sauf demande de code
            if utiliser_corpus:
                mode_force = "technique" if demande_code_explicite(q) else None
            else:
                mode_force = "technique" if demande_code_explicite(q) else "texte"

        web_actif_gen = bool(st.session_state.get("web_search_actif"))
        if demande_generation_image(q):
            _label_spin = "Génération de l'image…"
        elif necessite_preparation(fichiers_contexte, q):
            _label_spin = "Analyse des pièces jointes…"
        elif fichiers_contexte:
            _label_spin = "Lecture des documents joints…"
        elif web_actif_gen:
            _label_spin = "Recherche en cours…"
        else:
            _label_spin = "Réflexion en cours…"

        _afficher_reflexion(_label_spin)

        resultat = st.session_state.orchestrateur.repondre(
            question=q,
            historique=st.session_state.historique_llm[:-1],
            fichiers=fichiers_contexte or None,
            filtres=filtres if (utiliser_corpus or not a_un_fichier) else None,
            top_k=st.session_state.top_k,
            stream=True,
            mode_force=mode_force,
            contexte_projet_existant=st.session_state.get("contexte_projet") or {},
            utiliser_corpus=utiliser_corpus,
            user_id=_owner(),
        )

        if getattr(resultat, "contexte_projet", None):
            st.session_state.contexte_projet = resultat.contexte_projet

        if resultat.abstention:
            texte_abs = (
                resultat.reponse
                or "Je n'ai pas trouvé de passages suffisamment fiables dans le corpus "
                "pour répondre avec confiance."
            )
            zone_reponse.markdown(texte_abs)
            latence = time.time() - t0
            st.session_state.messages.append({
                "role": "assistant", "content": texte_abs,
                "docs": [], "tokens": 0, "latence": latence,
                "avec_fichier": a_un_fichier,
                "sans_sources": True,
                "abstention": True,
                "mode": "abstention",
                "score_rag": 0.0,
            })
            st.session_state.historique_llm.append({"role": "assistant", "content": texte_abs})
        else:
            flux = resultat.stream
            reponse_txt = ""
            if flux is not None:
                reponse_txt = afficher_flux(flux, zone=zone_reponse)
                # Journal après stream : contrôle qualité a posteriori, sans régénération
                try:
                    holder = resultat.usage_holder or {}
                    meta = resultat.meta_journal or {}
                    st.session_state.orchestrateur.journal.enregistrer({
                        "question": q[:300],
                        "mode": resultat.mode,
                        "strategie_sources": getattr(resultat.analyse, "strategie_sources", ""),
                        "score_rag": getattr(resultat, "score_rag", 0.0),
                        "tokens": holder.get("tokens_utilises") or 0,
                        "latence": time.time() - t0,
                        "regen": 0,
                        "score_qualite": meta.get("score_qualite"),
                        "qualite_valide": meta.get("qualite_valide"),
                        "web_utile": bool(sources_web_reelles(resultat.ressources_web)),
                        "stream": True,
                    })
                except Exception:
                    pass
            else:
                reponse_txt = nettoyer_reponse(resultat.reponse_seule or resultat.reponse or "")
                zone_reponse.markdown(reponse_txt)
            if str(reponse_txt or "").startswith("❌ Erreur"):
                _journal_securite("ia_erreur", "faible", str(reponse_txt)[:200])

            citations = resultat.citations or ""
            if citations and "📚" not in (reponse_txt or "") and "🌐" not in (reponse_txt or ""):
                reponse_affichee = (reponse_txt or "").strip() + "\n\n---\n\n" + citations
            else:
                reponse_affichee = (reponse_txt or "").strip()

            latence = time.time() - t0
            docs_affiches = resultat.documents or []
            if salutation:
                docs_affiches = []

            holder = resultat.usage_holder or {}
            tokens = (
                resultat.tokens_utilises
                or holder.get("tokens_utilises")
                or 0
            )
            if not tokens and reponse_affichee:
                tokens = max(1, len(reponse_affichee) // 4)

            conf_rag = float(getattr(resultat, "score_rag", 0.0) or 0.0)
            nb_web = len(sources_web_reelles(resultat.ressources_web))

            st.session_state.messages.append({
                "role": "assistant", "content": reponse_affichee,
                "docs": docs_affiches,
                "tokens": int(tokens),
                "latence": latence,
                "avec_fichier": a_un_fichier,
                "sans_sources": salutation or resultat.mode in {"conversation", "image"},
                "abstention": False,
                "mode": resultat.mode,
                "score_rag": conf_rag,
                "nb_sources_web": nb_web,
                "question_origine": q,
                "images": list(getattr(resultat, "images_generees", None) or []),
            })
            st.session_state.historique_llm.append({
                "role": "assistant", "content": reponse_affichee
            })
            if len(st.session_state.historique_llm) > 20:
                st.session_state.historique_llm = st.session_state.historique_llm[-20:]

    except Exception as e:
        try:
            _journal_securite("ia_erreur", "faible", f"Génération interrompue : {type(e).__name__}")
        except Exception:
            pass
        texte_err = message_erreur(
            "Je n'ai pas pu générer de réponse cette fois-ci.",
            e,
            "Réessayez dans un instant ou reformulez la question.",
        )
        zone_reponse.markdown(texte_err)
        st.session_state.messages.append({
            "role": "assistant",
            "content": texte_err,
            "docs": [], "tokens": 0, "latence": 0, "avec_fichier": a_un_fichier,
            "sans_sources": False, "abstention": False,
        })

    sync_discussion()
    st.session_state.en_cours = False
    st.rerun()
