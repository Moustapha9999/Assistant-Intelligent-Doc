"""
Interface AssistDoc — Chat conversationnel avec upload de fichiers
ISI KOMUNIK · Master IAGE
"""

import sys, os, time, uuid, re, importlib
from pathlib import Path
from typing import Optional
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from retrieval.retrieval_hybride import RetrievalHybride
from generation import generateur_reponse as _generateur_reponse

importlib.reload(_generateur_reponse)
GenerateurReponse = _generateur_reponse.GenerateurReponse
demande_code_explicite = _generateur_reponse.demande_code_explicite
demande_generation_image = _generateur_reponse.demande_generation_image
est_demande_projet = _generateur_reponse.est_demande_projet
est_cahier_des_charges = _generateur_reponse.est_cahier_des_charges
est_salutation = _generateur_reponse.est_salutation
from core.orchestrateur import OrchestrateurAssistant
from app.gestionnaire_fichiers import traiter_fichier, formater_pour_prompt, transcrire_audio
from app.historique_sqlite import HistoriqueSQLite
from app.favoris_sqlite import FavorisSQLite
from app.auth_basique import (
    afficher_dialog_auth_si_besoin,
    barre_compte_sidebar,
    consommer_requete,
    deconnecter,
    est_admin_session,
    exiger_auth,
    utilisateur_courant,
    utilisateur_session,
)
from app import export_conversation as _export_conversation

importlib.reload(_export_conversation)
export_markdown = _export_conversation.export_markdown
export_pdf = _export_conversation.export_pdf
from retrieval.citations import citation_courte, enrichir_document
import streamlit.components.v1 as components
import html as html_lib

_LOGO_FILE = ROOT / "assets" / "assistdoc_logo.png"
st.set_page_config(
    page_title="AssistDoc",
    page_icon=str(_LOGO_FILE) if _LOGO_FILE.exists() else "⬡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Session invité automatique (style ChatGPT) — pas d'écran bloquant
exiger_auth()

# Persistance SQLite
@st.cache_resource
def _db() -> HistoriqueSQLite:
    return HistoriqueSQLite()


@st.cache_resource
def _favoris() -> FavorisSQLite:
    return FavorisSQLite()


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,500;8..60,600&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --bg: #262624;
    --bg-side: #1f1e1d;
    --bg-elev: #30302e;
    --bg-input: #30302e;
    --border: #3d3d3a;
    --text: #f5f4ef;
    --text-muted: #b0aea5;
    --text-dim: #8a877c;
    --accent: #5b9fd4;
    --code-bg: #2a3540;
    --code-fg: #a8d4f0;
}

*, *::before, *::after { box-sizing: border-box; }
html, body, [data-testid="stAppViewContainer"], .stApp {
    background: var(--bg) !important;
    color: var(--text);
    font-family: 'Inter', system-ui, sans-serif;
}
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stToolbar"] { display: none; }
.block-container { padding: 0 !important; max-width: 100% !important; }
[data-testid="stAppViewContainer"] > .main { background: var(--bg) !important; }

/* ── Sidebar Claude-like ── */
[data-testid="stSidebar"] {
    background: var(--bg-side) !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
    min-width: 260px !important;
}
[data-testid="stSidebar"] > div:first-child { padding: 12px 10px 20px !important; }
.sb-brand {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 10px 18px;
}
.sb-brand-icon {
    width: 32px; height: 32px; border-radius: 9px;
    object-fit: cover;
    display: block;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25);
}
.sb-brand-name { font-size: 15px; font-weight: 600; color: var(--text); letter-spacing: -0.2px; }
.sb-export-box {
    margin: 10px 0 6px 0;
    padding: 10px 10px 8px;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    background: rgba(255,255,255,0.03);
}
.sb-export-title {
    font-size: 11px; font-weight: 600; color: var(--text-dim);
    letter-spacing: 0.04em; text-transform: uppercase;
    margin-bottom: 4px;
}
.sb-export-hint {
    font-size: 11px; color: var(--text-muted); line-height: 1.35;
    margin-bottom: 8px;
}
.sb-promo {
    margin: 8px 0 10px 0;
    padding: 14px 14px 12px;
    border-radius: 14px;
    background: #0d0d0d;
    border: 1px solid rgba(255,255,255,0.08);
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
.sb-section { padding: 14px 10px 6px; }
.sb-section-title {
    font-size: 11px; font-weight: 500; color: var(--text-dim);
    margin-bottom: 8px; padding-left: 4px;
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
.chat-wrap { max-width: 720px; margin: 0 auto; padding: 8px 24px 240px; }
.welcome {
    text-align: center; padding: 80px 20px 36px;
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

.tdots { display: flex; gap: 5px; align-items: center; padding: 8px 0; }
.tdots span {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--text-dim); animation: bounce 1.2s infinite;
}
.tdots span:nth-child(2) { animation-delay: 0.2s; }
.tdots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce { 0%,60%,100%{transform:translateY(0)} 30%{transform:translateY(-5px)} }
.tlabel { font-size: 13px; color: var(--text-dim); margin-top: 4px; }

/* Messages — user à droite, IA à gauche */
[data-testid="stChatMessage"] {
    background: transparent !important;
    padding: 10px 0 !important;
    max-width: 780px; margin: 0 auto;
    gap: 12px !important;
    display: flex !important;
    width: 100% !important;
}
[data-testid="stChatMessage"] img,
[data-testid="stChatMessage"] [data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessage"] [data-testid="stChatMessageAvatarAssistant"] {
    background: var(--bg-elev) !important;
    border: none !important;
    border-radius: 50% !important;
    width: 28px !important; height: 28px !important;
    font-size: 11px !important;
    flex-shrink: 0 !important;
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
}

/* User → droite */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    flex-direction: row-reverse !important;
    justify-content: flex-start !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {
    background: rgba(91,159,212,0.12) !important;
    border: 1px solid rgba(91,159,212,0.22) !important;
    border-radius: 16px 16px 4px 16px !important;
    padding: 12px 16px !important;
    color: var(--text) !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 15px !important;
    font-weight: 500 !important;
}

/* IA → gauche */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
    flex-direction: row !important;
    justify-content: flex-start !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) [data-testid="stChatMessageContent"] {
    text-align: left !important;
}
[data-testid="stChatMessageContent"] p { margin: 0 0 0.85em !important; }
[data-testid="stChatMessageContent"] pre {
    background: #1a1918 !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 12px !important;
    padding: 16px !important;
    overflow-x: auto !important;
    font-size: 13px !important;
    font-family: 'JetBrains Mono', monospace !important;
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
[data-testid="stChatMessageContent"] a { color: #7eb8e0 !important; }
[data-testid="stChatMessageContent"] strong { color: var(--text) !important; font-weight: 600 !important; }
[data-testid="stChatMessageContent"] h1,
[data-testid="stChatMessageContent"] h2,
[data-testid="stChatMessageContent"] h3 {
    font-family: 'Source Serif 4', Georgia, serif !important;
    color: var(--text) !important;
    font-weight: 600 !important;
    margin: 1.1em 0 0.45em !important;
}
[data-testid="stChatMessageContent"] h1 { font-size: 1.35em !important; }
[data-testid="stChatMessageContent"] h2 { font-size: 1.2em !important; }
[data-testid="stChatMessageContent"] h3 { font-size: 1.08em !important; }

/* ── Input flottant style Claude ── */
.input-zone {
    position: fixed; bottom: 0; left: 0; right: 0;
    background: linear-gradient(transparent, var(--bg) 40%);
    padding: 28px 0 18px; z-index: 200;
    pointer-events: none;
}
.input-inner { max-width: 720px; margin: 0 auto; padding: 0 24px; }
.upload-preview {
    display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px;
}
.up-file {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 12px; color: var(--text-muted);
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 10px; padding: 6px 11px;
}
.up-file .ufi { color: var(--accent); }
.composer-hint {
    font-size: 11.5px; color: var(--text-dim);
    text-align: center; margin-top: 12px; letter-spacing: 0.1px;
}

/* Composer = dernière rangée horizontale du chat */
section.main .block-container .stHorizontalBlock:has(.stTextInput) {
    background: var(--bg-input) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 22px !important;
    padding: 8px 10px 8px 10px !important;
    box-shadow: 0 8px 32px rgba(0,0,0,0.28) !important;
    align-items: center !important;
    max-width: 720px !important;
    margin: 0 auto !important;
    gap: 6px !important;
}

.stTextInput { margin: 0 !important; }
.stTextInput > div { background: transparent !important; border: none !important; }
.stTextInput > div > div { background: transparent !important; border: none !important; }
.stTextInput > div > div > input {
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    color: var(--text) !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 15px !important;
    padding: 10px 8px !important;
    box-shadow: none !important;
    height: 44px !important;
}
.stTextInput > div > div > input:focus {
    border: none !important; box-shadow: none !important;
}
.stTextInput > div > div > input::placeholder { color: var(--text-dim) !important; }
.stTextInput label { display: none !important; }

/* Bouton envoyer (rond) */
section.main .stHorizontalBlock:has(.stTextInput) .stButton > button {
    background: var(--text) !important;
    color: #1a1918 !important;
    border: none !important;
    border-radius: 50% !important;
    font-weight: 600 !important;
    font-size: 16px !important;
    width: 40px !important; height: 40px !important;
    min-width: 40px !important; max-width: 40px !important;
    padding: 0 !important; cursor: pointer !important;
}
section.main .stHorizontalBlock:has(.stTextInput) .stButton > button:hover {
    background: #fff !important; transform: none !important; opacity: 0.92;
}

button[kind="secondary"],
.stButton > button[data-testid="baseButton-secondary"] {
    background: rgba(255,255,255,0.04) !important;
    color: var(--text-muted) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 14px !important;
    font-weight: 450 !important; font-size: 13.5px !important;
    padding: 14px 16px !important;
    height: auto !important; min-height: 48px !important; width: 100% !important;
    text-align: left !important; justify-content: flex-start !important;
}
button[kind="secondary"]:hover,
.stButton > button[data-testid="baseButton-secondary"]:hover {
    background: rgba(255,255,255,0.07) !important;
    border-color: rgba(255,255,255,0.14) !important;
    color: var(--text) !important;
}

/* Sidebar buttons */
section[data-testid="stSidebar"] .stButton > button {
    width: 100% !important; max-width: none !important;
    border-radius: 10px !important;
    justify-content: flex-start !important;
    text-align: left !important;
    font-size: 13px !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
}
/* Nouvelle conversation (primary) */
section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: transparent !important; color: var(--text) !important;
    border: 1px solid rgba(255,255,255,0.14) !important;
    height: 40px !important; font-weight: 500 !important;
    padding: 0 14px !important; margin-bottom: 4px !important;
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
    background: rgba(255,255,255,0.05) !important;
}
/* Discussions (secondary) */
section[data-testid="stSidebar"] .stButton > button[kind="secondary"] {
    background: transparent !important; color: var(--text-muted) !important;
    border: none !important; height: auto !important; min-height: 36px !important;
    font-weight: 450 !important; padding: 8px 12px !important;
}
section[data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {
    background: rgba(255,255,255,0.05) !important; color: var(--text) !important;
    border: none !important; transform: none !important;
}
section[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"] .stButton > button {
    min-height: 28px !important;
    padding: 0 4px !important;
    font-size: 12px !important;
}
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
section[data-testid="stSidebar"] [data-testid="stPopover"] > button:hover,
section[data-testid="stSidebar"] [data-testid="stPopover"] button:hover {
    background: rgba(255,255,255,0.08) !important;
    color: var(--text) !important;
}
section[data-testid="stSidebar"] div[data-testid="stHorizontalBlock"]
  > div[data-testid="column"]:last-child {
    flex: 0 0 32px !important;
    width: 32px !important;
    min-width: 32px !important;
}

/* Upload / menu + style Claude */
[data-testid="stFileUploader"] {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    margin: 0 !important;
}
[data-testid="stFileUploader"] section,
[data-testid="stFileUploaderDropzone"] {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    min-height: 0 !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] > div > span,
[data-testid="stFileUploaderDropzoneInstructions"] span[data-testid="stFileUploaderDropzoneInstructionsText"],
[data-testid="stFileUploader"] small,
[data-testid="stFileUploader"] label {
    display: none !important;
}
[data-testid="stFileUploaderDropzoneInstructions"] {
    display: none !important;
}
[data-testid="stFileUploaderDropzone"] button,
[data-testid="stFileUploader"] button {
    background: transparent !important;
    color: var(--text) !important;
    border: none !important;
    border-radius: 10px !important;
    font-size: 14px !important;
    font-weight: 450 !important;
    height: 40px !important;
    min-height: 40px !important;
    width: 100% !important;
    max-width: none !important;
    padding: 0 12px !important;
    justify-content: flex-start !important;
    text-align: left !important;
    box-shadow: none !important;
}
[data-testid="stFileUploaderDropzone"] button:hover,
[data-testid="stFileUploader"] button:hover {
    background: rgba(255,255,255,0.06) !important;
}
/* Remplacer le libellé "Browse files" via overlay CSS n'est pas fiable :
   on le masque et on pose un faux libellé au-dessus via .plus-menu-item */
.plus-menu {
    min-width: 268px;
    padding: 4px 2px 2px;
}
.plus-menu-item {
    display: flex; align-items: center; gap: 10px;
    padding: 9px 12px; margin: 1px 0;
    border-radius: 10px;
    font-size: 14px; font-weight: 450;
    color: var(--text);
    line-height: 1.25;
}
.plus-menu-item .ico {
    width: 18px; text-align: center; opacity: 0.9; flex-shrink: 0;
}
.plus-menu-item .meta {
    margin-left: auto;
    font-size: 11px; color: var(--text-dim); font-weight: 400;
}
.plus-menu-sep {
    height: 1px; margin: 6px 8px;
    background: rgba(255,255,255,0.08);
}
.plus-upload-slot {
    position: relative;
    margin: 0;
}
.plus-upload-slot::before {
    content: "📎  Ajouter des fichiers ou images";
    position: absolute;
    left: 12px; top: 50%;
    transform: translateY(-50%);
    z-index: 2;
    pointer-events: none;
    font-size: 14px; font-weight: 450;
    color: var(--text);
    font-family: 'Inter', system-ui, sans-serif;
}
.plus-upload-slot [data-testid="stFileUploader"] {
    opacity: 0.02;
    position: relative;
    z-index: 3;
}
.plus-upload-slot:hover {
    background: rgba(255,255,255,0.06);
    border-radius: 10px;
}

.stSelectbox > div > div {
    background: var(--bg-elev) !important;
    border-color: rgba(255,255,255,0.1) !important;
    color: var(--text) !important;
    border-radius: 10px !important;
}
.stSlider > div > div > div > div { background: var(--accent) !important; }
label { color: var(--text-muted) !important; font-size: 12px !important; font-weight: 500 !important; }

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

/* Bouton + du composer */
.composer-plus-wrap button,
section.main .stPopover > button,
section.main [data-testid="stPopover"] > button {
    background: rgba(255,255,255,0.06) !important;
    color: var(--text) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 12px !important;
    width: 40px !important;
    height: 40px !important;
    min-width: 40px !important;
    max-width: 40px !important;
    padding: 0 !important;
    font-size: 20px !important;
    font-weight: 400 !important;
}
section.main .stPopover > button:hover,
section.main [data-testid="stPopover"] > button:hover {
    background: rgba(255,255,255,0.1) !important;
}

/* Corps des popovers */
div[data-testid="stPopoverBody"],
[data-testid="stPopoverBody"] {
    background: #2c2c29 !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 10px !important;
    box-shadow: 0 12px 32px rgba(0,0,0,0.45) !important;
    /* Compact par défaut (menu ⋯ discussions) */
    padding: 3px !important;
    min-width: 0 !important;
    width: max-content !important;
    max-width: 132px !important;
}
[data-testid="stPopoverBody"] [data-testid="stVerticalBlock"] {
    gap: 0 !important;
}
[data-testid="stPopoverBody"] [data-testid="stElementContainer"],
[data-testid="stPopoverBody"] .stElementContainer {
    margin-bottom: 0 !important;
}
[data-testid="stPopoverBody"] .stButton > button,
[data-testid="stPopoverBody"] button[kind="secondary"] {
    background: transparent !important;
    color: var(--text) !important;
    border: none !important;
    border-radius: 6px !important;
    justify-content: flex-start !important;
    text-align: left !important;
    height: 26px !important;
    min-height: 26px !important;
    padding: 0 8px !important;
    font-size: 12px !important;
    font-weight: 450 !important;
    width: 100% !important;
    box-shadow: none !important;
}
[data-testid="stPopoverBody"] .stButton > button:hover,
[data-testid="stPopoverBody"] button[kind="secondary"]:hover {
    background: rgba(255,255,255,0.06) !important;
    color: var(--text) !important;
    border: none !important;
    transform: none !important;
}
[data-testid="stPopoverBody"] .stButton > button[kind="primary"] {
    background: rgba(91,159,212,0.14) !important;
    color: #c5e2f7 !important;
    border: none !important;
}
/* Menu + du composer : plus large */
[data-testid="stPopoverBody"]:has(.plus-menu),
[data-testid="stPopoverBody"]:has([data-testid="stFileUploader"]) {
    min-width: 260px !important;
    max-width: 320px !important;
    width: 280px !important;
    padding: 6px !important;
    border-radius: 14px !important;
}
[data-testid="stPopoverBody"]:has(.plus-menu) .stButton > button,
[data-testid="stPopoverBody"]:has([data-testid="stFileUploader"]) .stButton > button {
    height: 40px !important;
    min-height: 40px !important;
    padding: 0 12px !important;
    font-size: 14px !important;
    border-radius: 10px !important;
}
[data-testid="stPopoverBody"] hr {
    margin: 6px 8px !important;
    border-color: rgba(255,255,255,0.08) !important;
}

/* Audio input discret */
[data-testid="stAudioInput"] {
    background: transparent !important;
}
[data-testid="stAudioInput"] label {
    color: var(--text-dim) !important;
    font-size: 12px !important;
}

.plus-hint {
    font-size: 12px; color: var(--text-dim); margin: 4px 0 10px;
}
.web-on {
    display: inline-flex; align-items: center; gap: 6px;
    font-size: 12px; color: #9ec9e8;
    background: rgba(91,159,212,0.14);
    border: 1px solid rgba(91,159,212,0.28);
    border-radius: 999px; padding: 4px 12px;
    margin-bottom: 10px;
}
.web-on .dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: #5b9fd4;
    box-shadow: 0 0 0 3px rgba(91,159,212,0.2);
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# Flèche scroll bas injectée dans le parent Streamlit
components.html(
    """
    <script>
    (function () {
      const doc = window.parent.document;

      // Styles dans le parent (sinon #assist-scroll-btn est invisible)
      if (!doc.getElementById('assist-scroll-style')) {
        const style = doc.createElement('style');
        style.id = 'assist-scroll-style';
        style.textContent = `
          #assist-scroll-btn {
            position: fixed !important;
            bottom: 110px !important;
            left: 50% !important;
            transform: translateX(-50%) !important;
            z-index: 2147483646 !important;
            width: 36px !important;
            height: 36px !important;
            border-radius: 50% !important;
            border: 1px solid rgba(255,255,255,0.18) !important;
            background: rgba(48,48,46,0.96) !important;
            cursor: pointer !important;
            display: none;
            align-items: center !important;
            justify-content: center !important;
            box-shadow: 0 4px 18px rgba(0,0,0,0.45) !important;
            backdrop-filter: blur(10px);
            padding: 0 !important;
            margin: 0 !important;
          }
          #assist-scroll-btn.show { display: flex !important; }
          #assist-scroll-btn:hover {
            background: rgba(70,70,66,0.98) !important;
            border-color: rgba(255,255,255,0.28) !important;
          }
          #assist-scroll-btn svg {
            width: 16px; height: 16px;
            stroke: #f5f4ef; fill: none;
            stroke-width: 2.2; stroke-linecap: round; stroke-linejoin: round;
          }
        `;
        doc.head.appendChild(style);
      }

      let btn = doc.getElementById('assist-scroll-btn');
      if (!btn) {
        btn = doc.createElement('button');
        btn.id = 'assist-scroll-btn';
        btn.title = 'Descendre en bas';
        btn.setAttribute('aria-label', 'Descendre en bas');
        btn.type = 'button';
        btn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M6 9l6 6 6-6"/></svg>';
        doc.body.appendChild(btn);
      }

      function getScrollEl() {
        const candidates = [
          doc.querySelector('[data-testid="stAppViewContainer"]'),
          doc.querySelector('.main'),
          doc.querySelector('section.main'),
          doc.scrollingElement,
          doc.documentElement,
          doc.body,
        ];
        for (const el of candidates) {
          if (el && el.scrollHeight > el.clientHeight + 40) return el;
        }
        return candidates[0] || doc.documentElement;
      }

      function nearBottom() {
        const el = getScrollEl();
        if (!el) return true;
        const gap = el.scrollHeight - el.scrollTop - el.clientHeight;
        return gap < 120;
      }

      function update() {
        if (nearBottom()) btn.classList.remove('show');
        else btn.classList.add('show');
      }

      function scrollBottom() {
        const el = getScrollEl();
        if (el) {
          el.scrollTo({ top: el.scrollHeight + 500, behavior: 'smooth' });
          // double passe pour le padding bas
          setTimeout(() => {
            el.scrollTop = el.scrollHeight;
            update();
          }, 280);
        }
        try {
          window.parent.scrollTo({ top: (doc.body.scrollHeight || 0) + 500, behavior: 'smooth' });
        } catch (e) {}
      }

      btn.onclick = scrollBottom;

      const el = getScrollEl();
      if (el && !el._assistScrollBound) {
        el.addEventListener('scroll', update, { passive: true });
        el._assistScrollBound = true;
      }
      if (!window.parent._assistScrollBound) {
        window.parent.addEventListener('scroll', update, { passive: true });
        window.parent._assistScrollBound = true;
      }
      setInterval(update, 400);
      update();

      // Pont toolbar (edit/feedback) : le sandbox bloque location.href depuis l'iframe
      if (!window.parent._assistToolbarBound) {
        window.parent.addEventListener('message', function (e) {
          try {
            const d = e.data;
            if (!d || d.source !== 'assistdoc-toolbar') return;
            const url = new URL(window.parent.location.href);
            if (d.action === 'edit') {
              url.searchParams.set('edit_msg', String(d.idx));
            } else if (d.action === 'fb') {
              url.searchParams.set('fb', String(d.note));
              url.searchParams.set('fb_idx', String(d.idx));
            } else {
              return;
            }
            window.parent.location.href = url.toString();
          } catch (err) {}
        });
        window.parent._assistToolbarBound = true;
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
    try:
        if not _db().supprimer_conversation(cid):
            return False
    except Exception:
        return False

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


def modifier_message(idx: int, nouveau_contenu: str) -> bool:
    if _discussion_figee():
        return False
    if idx < 0 or idx >= len(st.session_state.messages):
        return False
    contenu = (nouveau_contenu or "").strip()
    if not contenu:
        return False
    st.session_state.messages[idx]["content"] = contenu
    # Resync historique LLM
    st.session_state.historique_llm = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages
        if m.get("role") in ("user", "assistant")
    ]
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
    st.session_state.show_audio = False
    st.session_state.show_camera = False
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
            st.session_state.show_audio = False
            st.session_state.show_camera = False
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
        "show_audio": False,
        "show_camera": False,
        "utiliser_corpus_avec_fichier": True,
        "edit_msg_idx": None,
        "contexte_projet": {},
    }
    for k, v in d.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # Charger historique SQLite si session vide
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
    repo = (doc.get("nom_complet") or "").lower()
    src = (doc.get("source_file") or "").lower()
    return (
        bool(doc.get("source_enrichissement"))
        or repo.startswith("enrichissement/")
        or "knowledge/" in repo
        or src.startswith("enrichissement/")
        or "knowledge/" in src
    )


def afficher_sources(docs: list, msg_idx: int = 0):
    """Citations expert : [fichier:ligne], commits, score de confiance + favoris."""
    if not docs:
        return
    cols_fav = _favoris().lister_collections()
    col_ids = {c["nom"]: c["id"] for c in cols_fav}
    col_noms = list(col_ids.keys()) or ["Général"]
    for i, raw in enumerate(docs[:6], 1):
        doc = enrichir_document(raw)
        repo = doc.get("nom_complet") or "source"
        cite = doc.get("citation_courte") or citation_courte(doc)
        conf = doc.get("score_confiance")
        etoiles = doc.get("etoiles") or 0
        date = (doc.get("mis_a_jour_le") or "")[:10]
        conf_txt = f"{conf:.0%}" if isinstance(conf, (int, float)) else "—"
        blob = doc.get("url_blob") or doc.get("url") or ""
        commits = doc.get("url_commits") or ""
        label = f"**[{i}] {repo}** `{cite}`"
        meta_bits = [f"confiance {conf_txt}"]
        if _est_source_enrichie(doc):
            meta_bits.append("guide enrichi")
        elif etoiles and int(etoiles) < 50_000:
            meta_bits.append(f"★ {etoiles:,}")
        if date:
            meta_bits.append(date)
        liens = []
        if blob and str(blob).startswith("http") and not _est_source_enrichie(doc):
            liens.append(f"[fichier]({blob})")
        if commits and not _est_source_enrichie(doc):
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
            )
        with c2:
            deja = _favoris().est_deja_favori(
                repo, doc.get("source_file") or "", doc.get("section_titre") or ""
            )
            if st.button(
                "★ Favori" if not deja else "★ OK",
                key=f"fav_btn_{msg_idx}_{i}",
                disabled=deja,
                use_container_width=True,
            ):
                _favoris().ajouter_favori(doc, collection_id=col_ids.get(cible))
                st.toast(f"Ajouté à « {cible} »")
                st.rerun()


@st.cache_resource(show_spinner=False)
def charger():
    orchestrateur = OrchestrateurAssistant()
    return orchestrateur.retrieval, orchestrateur, orchestrateur


def icone_fichier(nom: str) -> str:
    ext = Path(nom).suffix.lower()
    if ext == ".pdf":                          return "📄"
    if ext in {".docx", ".doc"}:               return "📘"
    if ext in {".png",".jpg",".jpeg",".gif",".webp"}: return "🖼️"
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
                    st.session_state.edit_msg_idx = None
                else:
                    st.session_state.edit_msg_idx = idx
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
            if _enregistrer_feedback_msg(idx, note):
                st.toast(
                    "👍 Envoyé à l'admin" if note > 0 else "👎 Envoyé à l'admin"
                )
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
    """Toolbar Claude : SVG identiques (copier / modifier / feedback)."""
    import json as _json

    figee = _discussion_figee()
    en_edition = st.session_state.get("edit_msg_idx") == msg_idx
    js_texte = _json.dumps(contenu or "")
    safe = f"{role}_{msg_idx}_{st.session_state.input_key}"
    safe = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in safe)
    align = "flex-end" if role == "user" else "flex-start"

    ico_copy = (
        '<svg viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>'
        '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>'
    )
    ico_edit = (
        '<svg viewBox="0 0 24 24"><path d="M12 20h9"/>'
        '<path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>'
    )
    ico_close = (
        '<svg viewBox="0 0 24 24"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>'
    )
    ico_ok = '<svg viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></svg>'

    edit_svg = ico_close if en_edition else ico_edit
    edit_title = "Fermer" if en_edition else "Modifier"
    dis_attr = "disabled" if figee else ""

    # Copier / éditer en HTML ; 👍/👎 en boutons Streamlit (fiable → Admin)
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
            width: 100%;
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
          .tb-{safe} .tb-btn:disabled {{
            opacity: 0.35; cursor: not-allowed;
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
          <button class="tb-btn" id="edt_{safe}" title="{edit_title}" type="button" {dis_attr}>{edit_svg}</button>
        </div>
        <script>
        (function() {{
          const cpy = document.getElementById("cpy_{safe}");
          const edt = document.getElementById("edt_{safe}");
          const okIcon = `{ico_ok}`;
          const copyIcon = `{ico_copy}`;
          const figee = {str(figee).lower()};

          function send(payload) {{
            try {{
              window.parent.postMessage(Object.assign({{ source: "assistdoc-toolbar" }}, payload), "*");
            }} catch (e) {{}}
          }}

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
          if (edt && !figee) {{
            edt.onclick = function() {{ send({{ action: "edit", idx: {msg_idx} }}); }};
          }}
        }})();
        </script>
        """,
        height=30,
    )

    if role == "assistant":
        deja = st.session_state.setdefault("feedback_envoye", [])
        if not isinstance(deja, list):
            deja = list(deja)
            st.session_state.feedback_envoye = deja
        fb_key = f"{st.session_state.conversation_id}:{msg_idx}"
        c_up, c_dn, _ = st.columns([1, 1, 12])
        with c_up:
            if st.button(
                "👍",
                key=f"fb_up_{safe}",
                help="Utile — visible dans Admin",
                disabled=fb_key in deja,
            ):
                if _enregistrer_feedback_msg(msg_idx, 1):
                    deja.append(fb_key)
                    st.toast("👍 Envoyé à l'admin")
                    st.rerun()
                else:
                    st.toast("Échec enregistrement feedback")
        with c_dn:
            if st.button(
                "👎",
                key=f"fb_dn_{safe}",
                help="Pas utile — visible dans Admin",
                disabled=fb_key in deja,
            ):
                if _enregistrer_feedback_msg(msg_idx, -1):
                    deja.append(fb_key)
                    st.toast("👎 Envoyé à l'admin")
                    st.rerun()
                else:
                    st.toast("Échec enregistrement feedback")

    if en_edition and not figee:
        nouveau = st.text_area(
            "Éditer le message",
            value=contenu,
            height=180,
            key=f"inline_edit_{role}_{msg_idx}",
        )
        s1, s2 = st.columns(2)
        with s1:
            if st.button(
                "Enregistrer",
                key=f"inline_save_{role}_{msg_idx}",
                type="primary",
                use_container_width=True,
            ):
                if modifier_message(msg_idx, nouveau):
                    st.session_state.edit_msg_idx = None
                    st.toast("Message mis à jour")
                    st.rerun()
                else:
                    st.warning("Modification impossible.")
        with s2:
            if st.button(
                "Annuler",
                key=f"inline_cancel_{role}_{msg_idx}",
                use_container_width=True,
            ):
                st.session_state.edit_msg_idx = None
                st.rerun()


def url_valide(doc: dict) -> bool:
    """Vrai seulement si le doc a une URL GitHub exploitable."""
    url = doc.get("url", "")
    return isinstance(url, str) and url.startswith("http")


# ── SIDEBAR ───────────────────────────────────────────────────────
_LOGO_PATH = ROOT / "assets" / "assistdoc_logo.png"
with st.sidebar:
    if _LOGO_PATH.exists():
        import base64

        _logo_b64 = base64.b64encode(_LOGO_PATH.read_bytes()).decode("ascii")
        st.markdown(
            f"""
            <div class="sb-brand">
                <img class="sb-brand-icon" src="data:image/png;base64,{_logo_b64}" alt="AssistDoc" />
                <div class="sb-brand-name">AssistDoc</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div class="sb-brand">
                <div class="sb-brand-icon" style="background:linear-gradient(145deg,#5b9fd4,#3b7eb0);
                  display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;
                  border-radius:9px;width:32px;height:32px;">A</div>
                <div class="sb-brand-name">AssistDoc</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    barre_compte_sidebar()

    if st.button("＋  Nouvelle conversation", use_container_width=True, key="btn_new_chat", type="primary"):
        nouvelle_discussion()
        st.rerun()

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
    if discussions:
        st.markdown('<div class="sb-section"><div class="sb-section-title">Discussions</div></div>', unsafe_allow_html=True)
        for c in discussions:
            titre = c.get("titre") or "Nouvelle discussion"
            actif = c["id"] == st.session_state.conversation_id
            figee = bool(c.get("figee"))
            prefix = ("▸ " if actif else "") + ("🔒 " if figee else "")
            label = prefix + titre
            row = st.columns([9, 1], gap="small")
            with row[0]:
                if st.button(label, key=f"disc_{c['id']}", use_container_width=True, type="secondary"):
                    charger_discussion(c["id"])
                    st.rerun()
            with row[1]:
                with st.popover("⋯", help="Actions"):
                    tip_fige = "Défiger" if figee else "Figer"
                    if st.button(
                        tip_fige,
                        key=f"fig_{c['id']}",
                        use_container_width=True,
                    ):
                        basculer_figee(c["id"])
                        st.rerun()
                    if st.button(
                        "Renommer",
                        key=f"ren_{c['id']}",
                        use_container_width=True,
                        disabled=figee,
                    ):
                        st.session_state["edit_titre_id"] = c["id"]
                        st.rerun()
                    if st.button(
                        "Supprimer",
                        key=f"del_{c['id']}",
                        use_container_width=True,
                        disabled=figee,
                    ):
                        st.session_state["confirm_del_id"] = c["id"]
                        st.rerun()

        # Formulaire de renommage
        edit_id = st.session_state.get("edit_titre_id")
        if edit_id:
            cible = _trouver_discussion(edit_id)
            if cible and not cible.get("figee"):
                with st.form(key=f"form_rename_{edit_id}", clear_on_submit=True):
                    nouveau = st.text_input(
                        "Nouveau titre",
                        value=cible.get("titre") or "",
                        max_chars=120,
                        key=f"inp_rename_{edit_id}",
                    )
                    ok, annuler = st.columns(2)
                    with ok:
                        submitted = st.form_submit_button("Enregistrer", use_container_width=True)
                    with annuler:
                        cancel = st.form_submit_button("Annuler", use_container_width=True)
                    if cancel:
                        st.session_state.pop("edit_titre_id", None)
                        st.rerun()
                    if submitted:
                        if renommer_discussion(edit_id, nouveau):
                            st.session_state.pop("edit_titre_id", None)
                            st.toast("Titre mis à jour")
                        else:
                            st.warning("Impossible de renommer (vide ou figée).")
                        st.rerun()
            else:
                st.session_state.pop("edit_titre_id", None)

        # Confirmation suppression
        del_id = st.session_state.get("confirm_del_id")
        if del_id:
            cible = _trouver_discussion(del_id)
            if cible and not cible.get("figee"):
                st.warning(f"Supprimer « {cible.get('titre', 'discussion')} » ?")
                c_ok, c_no = st.columns(2)
                with c_ok:
                    if st.button("Oui, supprimer", key="confirm_del_yes", use_container_width=True, type="primary"):
                        if supprimer_discussion(del_id):
                            st.session_state.pop("confirm_del_id", None)
                            st.toast("Discussion supprimée")
                        else:
                            st.error("Suppression impossible (figée ?).")
                        st.rerun()
                with c_no:
                    if st.button("Annuler", key="confirm_del_no", use_container_width=True):
                        st.session_state.pop("confirm_del_id", None)
                        st.rerun()
            else:
                st.session_state.pop("confirm_del_id", None)

    with st.expander("Favoris & collections", expanded=False):
        cols = _favoris().lister_collections()
        noms = [c["nom"] for c in cols] or ["Général"]
        ids = {c["nom"]: c["id"] for c in cols}
        choix = st.selectbox("Collection", noms, key="sel_collection_fav")
        with st.form("form_new_collection", clear_on_submit=True):
            nouveau_nom = st.text_input("Nouvelle collection", max_chars=80)
            if st.form_submit_button("Créer", use_container_width=True):
                if nouveau_nom.strip():
                    _favoris().creer_collection(nouveau_nom.strip())
                    st.toast("Collection créée")
                    st.rerun()
        favs = _favoris().lister_favoris(ids.get(choix))
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
            if st.button("Retirer", key=f"rm_fav_{fav['id']}", use_container_width=True):
                _favoris().supprimer_favori(fav["id"])
                st.rerun()
            st.divider()

    if st.session_state.messages:
        titre_export = _titre_discussion(st.session_state.messages)
        cid = st.session_state.conversation_id
        st.markdown(
            """
            <div class="sb-export-box">
              <div class="sb-export-title">Exporter</div>
              <div class="sb-export-hint">
                Document structuré : résumé, questions / réponses numérotées et sources.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        md = export_markdown(
            st.session_state.messages,
            conversation_id=cid,
            titre=titre_export,
        )
        safe_name = re.sub(r"[^\w\-]+", "_", titre_export)[:40].strip("_") or "conversation"
        st.download_button(
            "Markdown (.md)",
            data=md.encode("utf-8"),
            file_name=f"AssistDoc_{safe_name}.md",
            mime="text/markdown; charset=utf-8",
            use_container_width=True,
            key="btn_export_md",
            help="Fichier Markdown lisible (GitHub, Notion, VS Code…)",
        )
        try:
            pdf_bytes = export_pdf(
                st.session_state.messages,
                titre=titre_export,
                conversation_id=cid,
            )
            st.download_button(
                "PDF (.pdf)",
                data=pdf_bytes,
                file_name=f"AssistDoc_{safe_name}.pdf",
                mime="application/pdf",
                use_container_width=True,
                key="btn_export_pdf",
                help="PDF mis en page pour lecture / impression",
            )
        except Exception as exc:
            st.caption(f"PDF indisponible : {exc}")

    with st.expander("Paramètres", expanded=False):
        st.session_state.filtre_lang = st.selectbox(
            "Langage",
            ["Tous","Python","JavaScript","TypeScript","Java","Go","Rust","C","C++","PHP","Ruby"],
            key="sel_lang"
        )
        st.session_state.filtre_repo = st.text_input(
            "Repo (ex. tiangolo/fastapi)",
            value=st.session_state.get("filtre_repo", ""),
            key="sel_repo",
        )
        st.session_state.filtre_stars = st.number_input(
            "Stars min", min_value=0, max_value=500000,
            value=int(st.session_state.get("filtre_stars", 0) or 0),
            step=100, key="sel_stars",
        )
        st.session_state.filtre_date = st.text_input(
            "Mis à jour après (YYYY-MM-DD)",
            value=st.session_state.get("filtre_date", ""),
            key="sel_date",
        )
        st.session_state.top_k = st.slider("Sources", 3, 10, 5, key="topk")
        st.session_state.utiliser_corpus_avec_fichier = st.toggle(
            "Fichier + corpus ensemble",
            value=st.session_state.get("utiliser_corpus_avec_fichier", True),
            key="tog_corpus_fichier",
        )

    # Auth en bas de sidebar
    _u_sb = utilisateur_session()
    if _u_sb:
        st.divider()
        if est_admin_session():
            st.caption("🛡 Page **Admin** — menu Streamlit en haut à gauche.")
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
                st.session_state.show_auth_dialog = True
                st.session_state.auth_email_step = "email"
                st.rerun()
        else:
            if st.button("Se déconnecter", key="btn_logout", use_container_width=True):
                deconnecter()
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
        ph.error(f"❌ {e}")
        st.stop()


_traiter_actions_url()

# ── TOPBAR (auth via sidebar uniquement) ─────────────────────────
st.markdown("""
<div class="topbar">
    <span class="topbar-l">AssistDoc <span class="chev">▾</span></span>
    <span class="topbar-r">Documentation GitHub</span>
</div>
""", unsafe_allow_html=True)
afficher_dialog_auth_si_besoin()


# ── CHAT ──────────────────────────────────────────────────────────
col = st.columns([1, 12, 1])[1]

with col:
    st.markdown('<div class="chat-wrap">', unsafe_allow_html=True)

    if not st.session_state.messages:
        if _LOGO_PATH.exists():
            import base64 as _b64

            _wlogo = _b64.b64encode(_LOGO_PATH.read_bytes()).decode("ascii")
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
                if st.button(sug, key=f"s{i}", use_container_width=True, type="secondary"):
                    st.session_state["_sug"] = sug + " ?"
                    st.rerun()

    for msg_idx, msg in enumerate(st.session_state.messages):
        if msg["role"] == "user":
            # Utilisateur à droite
            _, droite = st.columns([2, 5])
            with droite:
                fichiers_msg = msg.get("fichiers", [])
                with st.chat_message("user", avatar="user"):
                    if fichiers_msg:
                        for f in fichiers_msg:
                            if f.get("type") == "image" and f.get("image_b64"):
                                try:
                                    import base64 as _b64img

                                    st.image(
                                        _b64img.b64decode(f["image_b64"]),
                                        caption=f.get("nom") or "image",
                                        use_container_width=True,
                                    )
                                except Exception:
                                    st.caption(f"🖼 {f.get('nom')}")
                            else:
                                st.markdown(
                                    f"`{icone_fichier(f['nom'])} {f['nom']}`"
                                )
                    st.markdown(msg["content"])
                    _afficher_actions_message(msg_idx, msg.get("content", ""), "user")
        else:
            # IA à gauche
            gauche, _ = st.columns([5, 2])
            with gauche:
                docs    = msg.get("docs", [])
                tokens  = msg.get("tokens", 0)
                sans_sources = msg.get("sans_sources", False)
                abstention = msg.get("abstention", False)
                mode_msg = msg.get("mode") or ""
                nb_web = int(msg.get("nb_sources_web") or 0)
                score_rag_msg = msg.get("score_rag")

                with st.chat_message("assistant", avatar="assistant"):
                    st.markdown(msg["content"])
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

                    # Tokens + confiance + décompte sources (pas de latence)
                    meta_parts = []
                    if tokens:
                        meta_parts.append(f"{tokens} tokens")
                    if mode_msg and mode_msg not in {"conversation", "abstention"}:
                        meta_parts.append(f"mode {mode_msg}")
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
                        if st.button("Envoyer le signalement", key=f"btn_signal_{msg_idx}"):
                            texte = (motif or "").strip()
                            if not texte:
                                st.warning("Ajoutez un court commentaire.")
                            elif _enregistrer_feedback_msg(
                                msg_idx, -1, f"[signalement] {texte}"
                            ):
                                st.toast("⚠ Signalement envoyé à l'admin")
                            else:
                                st.error("Impossible d'enregistrer le signalement.")


    if st.session_state.en_cours:
        gauche, _ = st.columns([5, 2])
        with gauche:
            with st.chat_message("assistant", avatar="assistant"):
                st.markdown("""
                <div class="tdots"><span></span><span></span><span></span></div>
                <div class="tlabel">Recherche et génération…</div>
                """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)


# ── INPUT + UPLOAD (composer flottant style Claude) ───────────────
with col:
    if st.session_state.fichiers_en_attente:
        badges = "".join([
            f'<span class="up-file"><span class="ufi">{icone_fichier(f["nom"])}</span>{html_lib.escape(f["nom"])}</span>'
            for f in st.session_state.fichiers_en_attente
        ])
        st.markdown(f'<div class="upload-preview">{badges}</div>', unsafe_allow_html=True)

    if st.session_state.web_search_actif:
        st.markdown(
            '<div class="web-on"><span class="dot"></span> Recherche web</div>',
            unsafe_allow_html=True,
        )

    # Ligne composer : [+] | texte | ↑
    c_plus, c_input, c_send = st.columns([1, 10, 1])

    with c_plus:
        with st.popover("＋", help="Ajouter"):
            st.markdown('<div class="plus-menu">', unsafe_allow_html=True)

            # Un seul upload (fichiers + images), rendu comme une ligne de menu
            st.markdown('<div class="plus-upload-slot">', unsafe_allow_html=True)
            fichiers_up = st.file_uploader(
                "Ajouter des fichiers ou images",
                accept_multiple_files=True,
                type=None,
                key=f"up_files_{st.session_state.input_key}",
                label_visibility="collapsed",
            )
            st.markdown("</div>", unsafe_allow_html=True)
            if fichiers_up:
                traites = [traiter_fichier(f) for f in fichiers_up]
                existants = {f["nom"] for f in st.session_state.fichiers_en_attente}
                ajoutés = 0
                for t in traites:
                    if t["nom"] not in existants:
                        st.session_state.fichiers_en_attente.append(t)
                        ajoutés += 1
                if ajoutés:
                    st.toast(f"{ajoutés} fichier(s) ajouté(s)")

            if st.button("📷  Prendre une photo", use_container_width=True, key="btn_cam", type="secondary"):
                st.session_state.show_camera = not st.session_state.show_camera
                st.rerun()

            if st.button("🎤  Enregistrer un audio", use_container_width=True, key="btn_aud", type="secondary"):
                st.session_state.show_audio = not st.session_state.show_audio
                st.rerun()

            st.markdown('<div class="plus-menu-sep"></div>', unsafe_allow_html=True)

            web_actif = bool(st.session_state.web_search_actif)
            web_label = "🌐  Recherche Web" + ("    ✓" if web_actif else "")
            if st.button(
                web_label,
                use_container_width=True,
                key="btn_web_toggle",
                type="primary" if web_actif else "secondary",
            ):
                activer_recherche_web(not web_actif)
                st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)

    bloque_invite = bool(st.session_state.get("force_login"))
    with c_input:
        valeur = st.session_state.pop("_sug", "")
        question = st.text_input(
            "q", value=valeur,
            placeholder=(
                "Connectez-vous pour continuer…"
                if bloque_invite
                else "Poser une question…"
            ),
            key=f"inp_{st.session_state.input_key}",
            label_visibility="collapsed",
            disabled=bloque_invite,
        )
    with c_send:
        envoyer = st.button(
            "↑",
            use_container_width=True,
            key="btn_send",
            disabled=bloque_invite,
        )

    # Panneau caméra (si demandé via +)
    if st.session_state.show_camera:
        photo = st.camera_input("Photo", key=f"cam_{st.session_state.input_key}")
        if photo is not None:
            traite = traiter_fichier(photo)
            if all(f["nom"] != traite["nom"] for f in st.session_state.fichiers_en_attente):
                st.session_state.fichiers_en_attente.append(traite)
            st.session_state.show_camera = False
            st.rerun()

    # Panneau audio (si demandé via +)
    if st.session_state.show_audio:
        audio = st.audio_input(
            "Enregistrer un message vocal",
            key=f"aud_{st.session_state.input_key}",
        )
        if audio is not None:
            with st.spinner("Transcription audio…"):
                try:
                    texte = transcrire_audio(audio)
                except Exception as e:
                    texte = ""
                    st.warning(f"Transcription impossible : {e}")
            if texte:
                st.session_state["_sug"] = texte
                st.session_state.show_audio = False
                st.rerun()
            else:
                # Garder l'audio comme pièce jointe si pas de texte
                traite = traiter_fichier(audio)
                st.session_state.fichiers_en_attente.append(traite)
                st.session_state.show_audio = False
                st.info("Audio joint (transcription vide).")

    st.markdown(
        '<div class="composer-hint">AssistDoc peut se tromper. Vérifiez les informations importantes.</div>',
        unsafe_allow_html=True,
    )


# ── TRAITEMENT ────────────────────────────────────────────────────
q_finale = (question if (envoyer and question.strip()) else None) or (valeur or None)
if st.session_state.get("force_login"):
    q_finale = None

if q_finale and q_finale.strip() and not st.session_state.en_cours:
    q        = q_finale.strip()
    fichiers = st.session_state.fichiers_en_attente.copy()

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

    contexte_fichiers = formater_pour_prompt(fichiers_msg)
    a_un_fichier      = bool(fichiers_msg)

    q_enrichie = q
    if contexte_fichiers:
        q_enrichie = (
            q + "\n\n[Fichiers joints par l'utilisateur — base ta réponse "
            "PRINCIPALEMENT sur leur contenu ci-dessous :]\n" + contexte_fichiers
        )

    filtres = construire_filtres()

    try:
        t0 = time.time()
        ok_quota, msg_quota = consommer_requete(
            {"question": (q or "")[:200], "avec_fichier": a_un_fichier}
        )
        if not ok_quota:
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

        _label_spin = "Réflexion…"
        if demande_generation_image(q):
            _label_spin = "Génération de l'image…"
        elif a_un_fichier and any(f.get("type") == "image" for f in fichiers_msg):
            _label_spin = "Analyse de l'image…"

        with st.spinner(_label_spin):
            resultat = st.session_state.orchestrateur.repondre(
                question=q,
                historique=st.session_state.historique_llm[:-1],
                fichiers=fichiers_msg if a_un_fichier else None,
                filtres=filtres if (utiliser_corpus or not a_un_fichier) else None,
                top_k=st.session_state.top_k,
                stream="auto",
                mode_force=mode_force,
                contexte_projet_existant=st.session_state.get("contexte_projet") or {},
                utiliser_corpus=utiliser_corpus,
            )

        if getattr(resultat, "contexte_projet", None):
            st.session_state.contexte_projet = resultat.contexte_projet

        if resultat.abstention:
            texte_abs = (
                resultat.reponse
                or "Je n'ai pas trouvé de passages suffisamment fiables dans le corpus "
                "pour répondre avec confiance."
            )
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
                gauche, _ = st.columns([5, 2])
                with gauche:
                    with st.chat_message("assistant", avatar="assistant"):
                        reponse_txt = st.write_stream(flux)
                # Journal après stream (pas de boucle qualité en stream)
                try:
                    holder = resultat.usage_holder or {}
                    st.session_state.orchestrateur.journal.enregistrer({
                        "question": q[:300],
                        "mode": resultat.mode,
                        "strategie_sources": getattr(resultat.analyse, "strategie_sources", ""),
                        "score_rag": getattr(resultat, "score_rag", 0.0),
                        "tokens": holder.get("tokens_utilises") or 0,
                        "latence": time.time() - t0,
                        "regen": 0,
                        "web_utile": bool(resultat.ressources_web),
                        "stream": True,
                    })
                except Exception:
                    pass
            else:
                reponse_txt = resultat.reponse_seule or resultat.reponse or ""

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
            nb_web = len(resultat.ressources_web or [])

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
        st.session_state.messages.append({
            "role": "assistant", "content": f"❌ Erreur : {e}",
            "docs": [], "tokens": 0, "latence": 0, "avec_fichier": a_un_fichier,
            "sans_sources": False, "abstention": False,
        })

    sync_discussion()
    st.session_state.en_cours = False
    st.rerun()
