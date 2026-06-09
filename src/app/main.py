"""
Interface principale — Assistant Intelligent Doc
Système RAG pour développeurs francophones — ISI KOMUNIK
"""

import sys
import os
import time
from pathlib import Path

import streamlit as st

# ── Path setup ───────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from retrieval.retrieval_hybride import RetrievalHybride
from generation.generateur_reponse import GenerateurReponse

# ── Page config ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="AssistDoc — Documentation GitHub en français",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Design tokens ────────────────────────────────────────────────────
CSS = """
<style>
/* ── Google Fonts ── */
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

/* ── Reset & base ── */
*, *::before, *::after { box-sizing: border-box; }

html, body, [data-testid="stAppViewContainer"] {
    background: #0D1117 !important;
    color: #E6EDF3;
    font-family: 'IBM Plex Sans', sans-serif;
}

/* ── Hide Streamlit chrome ── */
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stToolbar"] { display: none; }
.block-container { padding: 0 !important; max-width: 100% !important; }

/* ══════════════════════════════════════════
   SIDEBAR
══════════════════════════════════════════ */
[data-testid="stSidebar"] {
    background: #0D1117 !important;
    border-right: 1px solid #21262D !important;
    padding: 0 !important;
}
[data-testid="stSidebar"] > div { padding: 0 !important; }

.sidebar-header {
    padding: 28px 20px 24px;
    border-bottom: 1px solid #21262D;
}
.sidebar-logo {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 6px;
}
.sidebar-logo-hex {
    font-size: 22px;
    color: #58A6FF;
    line-height: 1;
}
.sidebar-logo-text {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 16px;
    font-weight: 600;
    color: #E6EDF3;
    letter-spacing: -0.3px;
}
.sidebar-tagline {
    font-size: 11px;
    color: #8B949E;
    letter-spacing: 0.4px;
    text-transform: uppercase;
    padding-left: 32px;
}

.sidebar-section {
    padding: 20px 20px 12px;
    border-bottom: 1px solid #21262D;
}
.sidebar-section-title {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: #6E7681;
    margin-bottom: 14px;
}

/* Stats cards in sidebar */
.stat-row {
    display: flex;
    gap: 8px;
    margin-bottom: 8px;
}
.stat-card {
    flex: 1;
    background: #161B22;
    border: 1px solid #21262D;
    border-radius: 6px;
    padding: 10px 8px;
    text-align: center;
}
.stat-card .num {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 18px;
    font-weight: 600;
    color: #58A6FF;
    line-height: 1;
    display: block;
}
.stat-card .lbl {
    font-size: 9px;
    color: #6E7681;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    margin-top: 4px;
    display: block;
}

/* Langue filter pills */
.lang-pill-row {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 6px;
}
.lang-pill {
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-family: 'IBM Plex Mono', monospace;
    border: 1px solid #30363D;
    color: #8B949E;
    cursor: pointer;
    transition: all 0.15s;
}
.lang-pill.active {
    border-color: #58A6FF;
    color: #58A6FF;
    background: rgba(88,166,255,0.08);
}

/* Sidebar history */
.history-item {
    padding: 8px 12px;
    border-radius: 6px;
    margin-bottom: 4px;
    cursor: pointer;
    transition: background 0.15s;
    border: 1px solid transparent;
}
.history-item:hover {
    background: #161B22;
    border-color: #21262D;
}
.history-item .q {
    font-size: 12px;
    color: #C9D1D9;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.history-item .ts {
    font-size: 10px;
    color: #6E7681;
    margin-top: 2px;
    font-family: 'IBM Plex Mono', monospace;
}

/* ══════════════════════════════════════════
   MAIN LAYOUT
══════════════════════════════════════════ */
.main-wrapper {
    display: flex;
    flex-direction: column;
    height: 100vh;
    padding: 0;
}

/* ── Top bar ── */
.topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 32px;
    border-bottom: 1px solid #21262D;
    background: #0D1117;
    position: sticky;
    top: 0;
    z-index: 100;
}
.topbar-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 13px;
    color: #6E7681;
    letter-spacing: 0.3px;
}
.topbar-status {
    display: flex;
    align-items: center;
    gap: 20px;
    font-size: 11px;
    color: #6E7681;
}
.status-dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: #3FB950;
    display: inline-block;
    margin-right: 5px;
    box-shadow: 0 0 6px #3FB950;
}

/* ── Hero search ── */
.hero {
    padding: 60px 32px 32px;
    text-align: center;
    max-width: 780px;
    margin: 0 auto;
    width: 100%;
}
.hero-eyebrow {
    font-size: 11px;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: #58A6FF;
    font-family: 'IBM Plex Mono', monospace;
    margin-bottom: 16px;
}
.hero-title {
    font-size: 36px;
    font-weight: 300;
    color: #E6EDF3;
    line-height: 1.2;
    margin-bottom: 8px;
    letter-spacing: -0.5px;
}
.hero-title strong {
    font-weight: 600;
    color: #58A6FF;
}
.hero-sub {
    font-size: 14px;
    color: #8B949E;
    margin-bottom: 36px;
    line-height: 1.6;
}

/* ── Search box ── */
.search-wrapper {
    position: relative;
    max-width: 720px;
    margin: 0 auto;
}
.stTextInput > div > div > input {
    background: #161B22 !important;
    border: 1px solid #30363D !important;
    border-radius: 10px !important;
    color: #E6EDF3 !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
    font-size: 15px !important;
    padding: 16px 20px !important;
    transition: border-color 0.2s !important;
    box-shadow: 0 0 0 0px transparent !important;
}
.stTextInput > div > div > input:focus {
    border-color: #58A6FF !important;
    box-shadow: 0 0 0 3px rgba(88,166,255,0.15) !important;
    outline: none !important;
}
.stTextInput > div > div > input::placeholder {
    color: #484F58 !important;
}
.stTextInput label { display: none !important; }

/* ── Quick suggestions ── */
.suggestions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    justify-content: center;
    margin-top: 16px;
}
.suggestion-chip {
    padding: 6px 14px;
    background: #161B22;
    border: 1px solid #21262D;
    border-radius: 20px;
    font-size: 12px;
    color: #8B949E;
    cursor: pointer;
    transition: all 0.15s;
    font-family: 'IBM Plex Sans', sans-serif;
}
.suggestion-chip:hover {
    border-color: #58A6FF;
    color: #58A6FF;
    background: rgba(88,166,255,0.05);
}

/* ── Send button ── */
.stButton > button {
    background: #58A6FF !important;
    color: #0D1117 !important;
    border: none !important;
    border-radius: 8px !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    padding: 12px 28px !important;
    cursor: pointer !important;
    transition: all 0.2s !important;
    letter-spacing: 0.2px !important;
    width: 100% !important;
}
.stButton > button:hover {
    background: #79B8FF !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 16px rgba(88,166,255,0.3) !important;
}

/* ══════════════════════════════════════════
   RÉPONSE
══════════════════════════════════════════ */
.response-container {
    max-width: 780px;
    margin: 0 auto;
    padding: 0 32px 60px;
    width: 100%;
}

.response-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 20px;
    padding-bottom: 16px;
    border-bottom: 1px solid #21262D;
}
.response-question {
    font-size: 18px;
    font-weight: 500;
    color: #E6EDF3;
    flex: 1;
}
.response-meta {
    display: flex;
    gap: 16px;
    align-items: center;
}
.meta-badge {
    display: flex;
    align-items: center;
    gap: 5px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    color: #6E7681;
    background: #161B22;
    border: 1px solid #21262D;
    border-radius: 4px;
    padding: 4px 8px;
}

/* Answer card */
.answer-card {
    background: #161B22;
    border: 1px solid #21262D;
    border-radius: 10px;
    padding: 28px;
    margin-bottom: 20px;
    line-height: 1.8;
    font-size: 14px;
    color: #C9D1D9;
}
.answer-card h1, .answer-card h2, .answer-card h3 {
    color: #E6EDF3;
    font-weight: 600;
    margin-top: 20px;
    margin-bottom: 10px;
}
.answer-card h1 { font-size: 20px; }
.answer-card h2 { font-size: 17px; }
.answer-card h3 { font-size: 15px; }
.answer-card code {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    background: #0D1117;
    border: 1px solid #30363D;
    border-radius: 4px;
    padding: 1px 5px;
    color: #79B8FF;
}
.answer-card pre {
    background: #0D1117 !important;
    border: 1px solid #30363D !important;
    border-radius: 8px !important;
    padding: 16px !important;
    overflow-x: auto !important;
    font-size: 12px !important;
    line-height: 1.6 !important;
    margin: 14px 0 !important;
}
.answer-card pre code {
    background: none !important;
    border: none !important;
    padding: 0 !important;
    color: #E6EDF3 !important;
}
.answer-card ul, .answer-card ol {
    padding-left: 20px;
    margin: 10px 0;
}
.answer-card li { margin-bottom: 6px; }
.answer-card a { color: #58A6FF; text-decoration: none; }
.answer-card a:hover { text-decoration: underline; }
.answer-card strong { color: #E6EDF3; }

/* Sources grid */
.sources-section {
    margin-top: 8px;
}
.sources-title {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
    color: #6E7681;
    margin-bottom: 12px;
}
.sources-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 10px;
}
.source-card {
    background: #0D1117;
    border: 1px solid #21262D;
    border-radius: 8px;
    padding: 12px 14px;
    transition: border-color 0.15s;
    text-decoration: none !important;
    display: block;
}
.source-card:hover {
    border-color: #58A6FF;
}
.source-card .sc-num {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 10px;
    color: #58A6FF;
    font-weight: 600;
    margin-bottom: 4px;
}
.source-card .sc-repo {
    font-size: 12px;
    font-weight: 600;
    color: #C9D1D9;
    margin-bottom: 2px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.source-card .sc-section {
    font-size: 11px;
    color: #6E7681;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.source-card .sc-lang {
    display: inline-block;
    margin-top: 6px;
    font-size: 10px;
    font-family: 'IBM Plex Mono', monospace;
    color: #3FB950;
    background: rgba(63,185,80,0.08);
    border: 1px solid rgba(63,185,80,0.2);
    border-radius: 3px;
    padding: 1px 6px;
}

/* Metrics row */
.metrics-row {
    display: flex;
    gap: 10px;
    margin-bottom: 20px;
}
.metric-chip {
    display: flex;
    align-items: center;
    gap: 6px;
    background: #161B22;
    border: 1px solid #21262D;
    border-radius: 6px;
    padding: 8px 14px;
    font-size: 12px;
    font-family: 'IBM Plex Mono', monospace;
}
.metric-chip .mc-val { color: #58A6FF; font-weight: 600; }
.metric-chip .mc-lbl { color: #6E7681; }

/* ── Loading ── */
.loading-bar {
    height: 2px;
    background: linear-gradient(90deg, transparent, #58A6FF, transparent);
    animation: slide 1.2s infinite;
    border-radius: 1px;
    margin-bottom: 24px;
}
@keyframes slide {
    0%   { background-position: -200% center; }
    100% { background-position: 200% center; }
}
.loading-text {
    text-align: center;
    font-size: 13px;
    color: #6E7681;
    font-family: 'IBM Plex Mono', monospace;
    padding: 32px;
}
.loading-step {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 0;
    font-size: 12px;
    color: #6E7681;
    font-family: 'IBM Plex Mono', monospace;
}
.loading-step .dot {
    width: 6px; height: 6px;
    border-radius: 50%;
    background: #58A6FF;
    animation: pulse 1s infinite;
}
@keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50%       { opacity: 0.4; transform: scale(0.8); }
}

/* ── Empty state ── */
.empty-state {
    text-align: center;
    padding: 60px 32px;
    color: #6E7681;
}
.empty-icon {
    font-size: 40px;
    margin-bottom: 16px;
    opacity: 0.4;
}
.empty-title {
    font-size: 16px;
    color: #8B949E;
    margin-bottom: 8px;
}
.empty-desc {
    font-size: 13px;
    line-height: 1.6;
}

/* ── Select & slider ── */
.stSelectbox > div > div {
    background: #161B22 !important;
    border-color: #30363D !important;
    color: #C9D1D9 !important;
    border-radius: 6px !important;
}
.stSlider > div > div > div > div {
    background: #58A6FF !important;
}
label { color: #8B949E !important; font-size: 12px !important; }
.stSelectbox label, .stSlider label {
    color: #8B949E !important;
    font-size: 11px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.5px !important;
}

/* Scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #0D1117; }
::-webkit-scrollbar-thumb { background: #30363D; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #484F58; }
</style>
"""

st.markdown(CSS, unsafe_allow_html=True)


# ── Session state ────────────────────────────────────────────────────
def init_state():
    defaults = {
        "moteur"     : None,
        "generateur" : None,
        "pret"       : False,
        "historique" : [],          # [(question, resultat)]
        "question"   : "",
        "filtre_lang": "Tous",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()


# ── Chargement des modèles ───────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def charger_systeme():
    moteur     = RetrievalHybride()
    generateur = GenerateurReponse()
    return moteur, generateur


# ── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    # Logo
    st.markdown("""
    <div class="sidebar-header">
        <div class="sidebar-logo">
            <span class="sidebar-logo-hex">⬡</span>
            <span class="sidebar-logo-text">AssistDoc</span>
        </div>
        <div class="sidebar-tagline">Documentation GitHub · FR</div>
    </div>
    """, unsafe_allow_html=True)

    # Stats
    st.markdown("""
    <div class="sidebar-section">
        <div class="sidebar-section-title">Corpus</div>
        <div class="stat-row">
            <div class="stat-card">
                <span class="num">1 446</span>
                <span class="lbl">Chunks</span>
            </div>
            <div class="stat-card">
                <span class="num">50+</span>
                <span class="lbl">Repos</span>
            </div>
        </div>
        <div class="stat-row">
            <div class="stat-card">
                <span class="num">384</span>
                <span class="lbl">Dimensions</span>
            </div>
            <div class="stat-card">
                <span class="num">5</span>
                <span class="lbl">Langages</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Paramètres
    st.markdown("""
    <div class="sidebar-section">
        <div class="sidebar-section-title">Paramètres</div>
    </div>
    """, unsafe_allow_html=True)

    filtre_lang = st.selectbox(
        "Langage",
        ["Tous", "Python", "JavaScript", "Java", "C", "C++"],
        key="sel_lang"
    )
    top_k = st.slider("Résultats", min_value=3, max_value=10, value=5, key="top_k")

    # Historique
    if st.session_state.historique:
        st.markdown("""
        <div class="sidebar-section">
            <div class="sidebar-section-title">Historique</div>
        </div>
        """, unsafe_allow_html=True)

        for i, (q, _) in enumerate(reversed(st.session_state.historique[-8:])):
            ts = f"{len(st.session_state.historique) - i}"
            st.markdown(f"""
            <div class="history-item">
                <div class="q">{q[:55]}{'…' if len(q)>55 else ''}</div>
                <div class="ts">#{ts}</div>
            </div>
            """, unsafe_allow_html=True)

    # Bouton clear
    if st.session_state.historique:
        st.markdown("<div style='padding: 12px 20px;'>", unsafe_allow_html=True)
        if st.button("🗑 Effacer l'historique", use_container_width=True):
            st.session_state.historique = []
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)


# ── Chargement du système ────────────────────────────────────────────
if not st.session_state.pret:
    with st.spinner(""):
        placeholder = st.empty()
        placeholder.markdown("""
        <div class="loading-text">
            <div style="font-size:32px;margin-bottom:20px;">⬡</div>
            <div style="font-size:15px;color:#C9D1D9;margin-bottom:24px;">
                Initialisation du système RAG…
            </div>
            <div class="loading-bar"></div>
        </div>
        """, unsafe_allow_html=True)
        try:
            m, g = charger_systeme()
            st.session_state.moteur     = m
            st.session_state.generateur = g
            st.session_state.pret       = True
            placeholder.empty()
        except Exception as e:
            placeholder.error(f"❌ Erreur d'initialisation : {e}")
            st.stop()


# ── Top bar ──────────────────────────────────────────────────────────
nb_questions = len(st.session_state.historique)
st.markdown(f"""
<div class="topbar">
    <span class="topbar-title">Assistant RAG · Documentation GitHub francophone</span>
    <div class="topbar-status">
        <span><span class="status-dot"></span>Qdrant actif</span>
        <span style="color:#3FB950;font-family:'IBM Plex Mono',monospace;">
            llama-3.3-70b
        </span>
        <span>{nb_questions} requête{'s' if nb_questions>1 else ''}</span>
    </div>
</div>
""", unsafe_allow_html=True)


# ── Hero + search ────────────────────────────────────────────────────
col_main = st.columns([1, 8, 1])[1]

with col_main:
    st.markdown("""
    <div class="hero">
        <div class="hero-eyebrow">ISI KOMUNIK · Master IAGE</div>
        <div class="hero-title">
            Interrogez la documentation<br>
            <strong>GitHub en français</strong>
        </div>
        <div class="hero-sub">
            Retrieval hybride BM25 + dense · Reranking cross-encoder · Citations systématiques
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Suggestions rapides
    suggestions = [
        "API REST avec Flask",
        "Authentification JWT",
        "Hooks React",
        "Gestion erreurs Node.js",
        "SQLAlchemy ORM",
        "Docker déploiement",
    ]
    cols_sug = st.columns(len(suggestions))
    question_suggestion = None
    for i, (col, sug) in enumerate(zip(cols_sug, suggestions)):
        with col:
            if st.button(sug, key=f"sug_{i}", use_container_width=True):
                question_suggestion = sug

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # Champ de saisie
    question_input = st.text_input(
        "Question",
        placeholder="Ex : Comment implémenter l'authentification OAuth2 avec Flask ?",
        key="question_input",
        label_visibility="collapsed",
    )

    # Bouton rechercher
    col_btn1, col_btn2, col_btn3 = st.columns([2, 3, 2])
    with col_btn2:
        lancer = st.button("Rechercher", use_container_width=True, type="primary")


# ── Traitement de la requête ─────────────────────────────────────────
question_finale = question_suggestion or (question_input if lancer else None)

if question_finale and question_finale.strip():
    q = question_finale.strip()
    filtres = {"langage": filtre_lang} if filtre_lang != "Tous" else None

    with col_main:
        st.markdown("""
        <div class="response-container">
        """, unsafe_allow_html=True)

        # Loading steps
        loading_ph = st.empty()
        loading_ph.markdown(f"""
        <div style="padding: 32px 0;">
            <div class="loading-bar"></div>
            <div class="loading-step"><span class="dot"></span>Vectorisation de la requête…</div>
            <div class="loading-step" style="opacity:0.5"><span class="dot"></span>Recherche dense (Qdrant)…</div>
            <div class="loading-step" style="opacity:0.3"><span class="dot"></span>Fusion BM25 + RRF…</div>
            <div class="loading-step" style="opacity:0.2"><span class="dot"></span>Reranking cross-encoder…</div>
            <div class="loading-step" style="opacity:0.1"><span class="dot"></span>Génération Groq llama-3.3-70b…</div>
        </div>
        """, unsafe_allow_html=True)

        t0 = time.time()

        # Retrieval
        docs = st.session_state.moteur.rechercher(
            q,
            top_k_retrieval=20,
            top_k_final=top_k,
            filtres=filtres,
        )

        # Génération
        resultat = st.session_state.generateur.generer(q, docs)
        latence  = time.time() - t0

        loading_ph.empty()

        # ── En-tête de réponse ──
        st.markdown(f"""
        <div class="response-header">
            <div class="response-question">{q}</div>
        </div>
        """, unsafe_allow_html=True)

        # ── Métriques ──
        st.markdown(f"""
        <div class="metrics-row">
            <div class="metric-chip">
                <span class="mc-val">{latence:.1f}s</span>
                <span class="mc-lbl">latence</span>
            </div>
            <div class="metric-chip">
                <span class="mc-val">{len(docs)}</span>
                <span class="mc-lbl">sources</span>
            </div>
            <div class="metric-chip">
                <span class="mc-val">{resultat['tokens_utilises']}</span>
                <span class="mc-lbl">tokens</span>
            </div>
            <div class="metric-chip">
                <span class="mc-val">llama-3.3-70b</span>
                <span class="mc-lbl">modèle</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Réponse principale ──
        st.markdown('<div class="answer-card">', unsafe_allow_html=True)
        st.markdown(resultat["reponse_seule"])
        st.markdown('</div>', unsafe_allow_html=True)

        # ── Sources ──
        if docs:
            st.markdown('<div class="sources-section">', unsafe_allow_html=True)
            st.markdown('<div class="sources-title">📚 Sources</div>', unsafe_allow_html=True)
            st.markdown('<div class="sources-grid">', unsafe_allow_html=True)

            for i, doc in enumerate(docs, 1):
                url     = doc.get("url", "#")
                repo    = doc.get("nom_complet", "N/A")
                section = doc.get("section_titre", "N/A")
                lang    = doc.get("langage", "")
                score   = doc.get("score_rerank", 0)

                st.markdown(f"""
                <a class="source-card" href="{url}" target="_blank">
                    <div class="sc-num">#{i} · score {score:.2f}</div>
                    <div class="sc-repo">{repo}</div>
                    <div class="sc-section">{section[:45]}{'…' if len(section)>45 else ''}</div>
                    <span class="sc-lang">{lang}</span>
                </a>
                """, unsafe_allow_html=True)

            st.markdown('</div></div>', unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

        # Sauvegarder dans l'historique
        st.session_state.historique.append((q, resultat))
        st.rerun()


# ── État vide ────────────────────────────────────────────────────────
elif not st.session_state.historique:
    with col_main:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-icon">⬡</div>
            <div class="empty-title">Prêt à répondre</div>
            <div class="empty-desc">
                Posez une question technique en français.<br>
                Le système recherche dans 1 446 chunks de documentation GitHub<br>
                et génère une réponse sourcée en moins de 5 secondes.
            </div>
        </div>
        """, unsafe_allow_html=True)


# ── Dernier résultat (après rerun) ───────────────────────────────────
elif st.session_state.historique and not question_finale:
    q_last, res_last = st.session_state.historique[-1]
    docs_last = res_last["documents"]

    with col_main:
        st.markdown('<div class="response-container">', unsafe_allow_html=True)

        st.markdown(f"""
        <div class="response-header">
            <div class="response-question">{q_last}</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
        <div class="metrics-row">
            <div class="metric-chip">
                <span class="mc-val">{len(docs_last)}</span>
                <span class="mc-lbl">sources</span>
            </div>
            <div class="metric-chip">
                <span class="mc-val">{res_last['tokens_utilises']}</span>
                <span class="mc-lbl">tokens</span>
            </div>
            <div class="metric-chip">
                <span class="mc-val">llama-3.3-70b</span>
                <span class="mc-lbl">modèle</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown('<div class="answer-card">', unsafe_allow_html=True)
        st.markdown(res_last["reponse_seule"])
        st.markdown('</div>', unsafe_allow_html=True)

        if docs_last:
            st.markdown('<div class="sources-section">', unsafe_allow_html=True)
            st.markdown('<div class="sources-title">📚 Sources</div>', unsafe_allow_html=True)
            st.markdown('<div class="sources-grid">', unsafe_allow_html=True)
            for i, doc in enumerate(docs_last, 1):
                url     = doc.get("url", "#")
                repo    = doc.get("nom_complet", "N/A")
                section = doc.get("section_titre", "N/A")
                lang    = doc.get("langage", "")
                score   = doc.get("score_rerank", 0)
                st.markdown(f"""
                <a class="source-card" href="{url}" target="_blank">
                    <div class="sc-num">#{i} · score {score:.2f}</div>
                    <div class="sc-repo">{repo}</div>
                    <div class="sc-section">{section[:45]}{'…' if len(section)>45 else ''}</div>
                    <span class="sc-lang">{lang}</span>
                </a>
                """, unsafe_allow_html=True)
            st.markdown('</div></div>', unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)