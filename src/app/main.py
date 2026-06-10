"""
Interface principale — AssistDoc
Système RAG conversationnel avec mémoire
ISI KOMUNIK · Master IAGE
"""

import sys
import os
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from retrieval.retrieval_hybride import RetrievalHybride
from generation.generateur_reponse import GenerateurReponse

st.set_page_config(
    page_title="AssistDoc — Documentation GitHub en français",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

*, *::before, *::after { box-sizing: border-box; }

html, body, [data-testid="stAppViewContainer"] {
    background: #0D1117 !important;
    color: #E6EDF3;
    font-family: 'IBM Plex Sans', sans-serif;
}

#MainMenu, footer, header { visibility: hidden; }
[data-testid="stToolbar"] { display: none; }
.block-container { padding: 0 !important; max-width: 100% !important; }

/* ── SIDEBAR ── */
[data-testid="stSidebar"] {
    background: #0D1117 !important;
    border-right: 1px solid #21262D !important;
}
[data-testid="stSidebar"] > div:first-child {
    padding: 0 !important;
}
[data-testid="stSidebar"] section {
    padding: 0 !important;
}

.sidebar-logo {
    padding: 24px 20px 16px;
    border-bottom: 1px solid #21262D;
}
.sidebar-logo-row { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
.sidebar-logo-icon { font-size: 22px; color: #58A6FF; }
.sidebar-logo-name {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 16px; font-weight: 600; color: #E6EDF3;
}
.sidebar-tagline {
    font-size: 10px; color: #6E7681;
    letter-spacing: 1px; text-transform: uppercase;
    padding-left: 32px;
}
.sidebar-section {
    padding: 16px 20px 8px;
    border-bottom: 1px solid #21262D;
}
.sidebar-section-title {
    font-size: 10px; font-weight: 600;
    letter-spacing: 1px; text-transform: uppercase;
    color: #6E7681; margin-bottom: 12px;
}
.stat-grid { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 4px; }
.stat-card {
    flex: 1; min-width: 60px;
    background: #161B22; border: 1px solid #21262D;
    border-radius: 6px; padding: 10px 8px; text-align: center;
}
.stat-card .num {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 16px; font-weight: 600; color: #58A6FF;
    display: block; line-height: 1;
}
.stat-card .lbl {
    font-size: 9px; color: #6E7681;
    text-transform: uppercase; letter-spacing: 0.5px;
    margin-top: 4px; display: block;
}

/* ── TOPBAR ── */
.topbar {
    display: flex; align-items: center;
    justify-content: space-between;
    padding: 12px 32px;
    border-bottom: 1px solid #21262D;
    background: #0D1117;
    position: sticky; top: 0; z-index: 100;
}
.topbar-title { font-family: 'IBM Plex Mono', monospace; font-size: 12px; color: #6E7681; }
.topbar-right {
    display: flex; align-items: center; gap: 16px;
    font-size: 11px; color: #6E7681;
    font-family: 'IBM Plex Mono', monospace;
}
.status-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: #3FB950; display: inline-block;
    margin-right: 5px; box-shadow: 0 0 6px #3FB950;
}

/* ── CHAT ── */
.chat-wrapper {
    max-width: 860px; margin: 0 auto;
    padding: 24px 32px 140px;
}

.chat-bubble { display: flex; gap: 14px; margin-bottom: 24px; }
.chat-bubble.user { flex-direction: row-reverse; }

.bubble-avatar {
    width: 36px; height: 36px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 15px; flex-shrink: 0;
    font-family: 'IBM Plex Mono', monospace; font-weight: 600;
}
.bubble-avatar.assistant {
    background: rgba(88,166,255,0.15);
    border: 1px solid rgba(88,166,255,0.3); color: #58A6FF;
}
.bubble-avatar.user-av {
    background: rgba(63,185,80,0.15);
    border: 1px solid rgba(63,185,80,0.3); color: #3FB950;
}
.bubble-content { flex: 1; max-width: 85%; }

.bubble-user-text {
    background: #161B22; border: 1px solid #30363D;
    border-radius: 12px 12px 4px 12px;
    padding: 12px 16px; font-size: 14px; color: #E6EDF3; line-height: 1.6;
}

.bubble-assistant-text {
    background: #0D1117; border: 1px solid #21262D;
    border-radius: 12px 12px 12px 4px;
    padding: 20px 24px; font-size: 14px; color: #C9D1D9; line-height: 1.8;
}
.bubble-assistant-text h1, .bubble-assistant-text h2 {
    color: #E6EDF3; font-weight: 600; margin: 16px 0 8px; font-size: 17px;
}
.bubble-assistant-text h3 {
    color: #C9D1D9; font-weight: 600; margin: 12px 0 6px; font-size: 15px;
}
.bubble-assistant-text code {
    font-family: 'IBM Plex Mono', monospace; font-size: 12px;
    background: #161B22; border: 1px solid #30363D;
    border-radius: 4px; padding: 1px 5px; color: #79B8FF;
}
.bubble-assistant-text pre {
    background: #161B22 !important; border: 1px solid #30363D !important;
    border-radius: 8px !important; padding: 16px !important;
    overflow-x: auto !important; font-size: 12px !important;
    line-height: 1.6 !important; margin: 12px 0 !important;
}
.bubble-assistant-text pre code {
    background: none !important; border: none !important;
    padding: 0 !important; color: #E6EDF3 !important;
}
.bubble-assistant-text ul, .bubble-assistant-text ol { padding-left: 20px; margin: 8px 0; }
.bubble-assistant-text li { margin-bottom: 4px; }
.bubble-assistant-text a { color: #58A6FF; text-decoration: none; }
.bubble-assistant-text a:hover { text-decoration: underline; }
.bubble-assistant-text strong { color: #E6EDF3; }
.bubble-assistant-text hr { border: none; border-top: 1px solid #21262D; margin: 16px 0; }

.bubble-meta {
    display: flex; gap: 10px; margin-top: 8px;
    font-size: 10px; color: #484F58;
    font-family: 'IBM Plex Mono', monospace;
}
.sources-mini { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.source-tag {
    font-size: 10px; font-family: 'IBM Plex Mono', monospace;
    background: #161B22; border: 1px solid #21262D;
    border-radius: 4px; padding: 2px 8px; color: #6E7681; text-decoration: none;
}
.source-tag:hover { border-color: #58A6FF; color: #58A6FF; }

/* ── WELCOME ── */
.welcome-screen {
    text-align: center; padding: 80px 32px 40px;
    max-width: 620px; margin: 0 auto;
}
.welcome-icon { font-size: 48px; margin-bottom: 20px; opacity: 0.7; }
.welcome-title { font-size: 28px; font-weight: 300; color: #E6EDF3; margin-bottom: 8px; }
.welcome-title strong { font-weight: 600; color: #58A6FF; }
.welcome-sub { font-size: 14px; color: #8B949E; line-height: 1.6; margin-bottom: 32px; }

/* ── THINKING ── */
.thinking-bubble { display: flex; gap: 14px; margin-bottom: 24px; }
.thinking-content {
    background: #0D1117; border: 1px solid #21262D;
    border-radius: 12px 12px 12px 4px; padding: 16px 20px;
}
.thinking-dots { display: flex; gap: 6px; align-items: center; }
.thinking-dots span {
    width: 6px; height: 6px; border-radius: 50%;
    background: #58A6FF; display: inline-block;
    animation: bounce 1.2s infinite;
}
.thinking-dots span:nth-child(2) { animation-delay: 0.2s; }
.thinking-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
    0%, 60%, 100% { transform: translateY(0); }
    30% { transform: translateY(-6px); }
}
.thinking-label {
    font-size: 12px; color: #6E7681;
    font-family: 'IBM Plex Mono', monospace; margin-top: 8px;
}

/* ── INPUT FIXÉE EN BAS ── */
.input-zone {
    position: fixed; bottom: 0; left: 0; right: 0;
    background: linear-gradient(transparent, #0D1117 30%);
    padding: 16px 0 24px; z-index: 200;
}
.input-inner { max-width: 860px; margin: 0 auto; padding: 0 32px; }

/* Input Streamlit */
.stTextInput { margin: 0 !important; }
.stTextInput > div > div > input {
    background: #161B22 !important;
    border: 1px solid #30363D !important;
    border-radius: 10px !important;
    color: #E6EDF3 !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
    font-size: 15px !important;
    padding: 14px 18px !important;
    box-shadow: none !important;
}
.stTextInput > div > div > input:focus {
    border-color: #58A6FF !important;
    box-shadow: 0 0 0 3px rgba(88,166,255,0.15) !important;
}
.stTextInput > div > div > input::placeholder { color: #484F58 !important; }
.stTextInput label { display: none !important; }

/* Boutons */
.stButton > button {
    background: #58A6FF !important; color: #0D1117 !important;
    border: none !important; border-radius: 8px !important;
    font-weight: 600 !important; font-size: 13px !important;
    padding: 12px 20px !important; cursor: pointer !important;
    transition: background 0.15s !important;
    width: 100% !important;
}
.stButton > button:hover { background: #79B8FF !important; }

/* Selectbox & Slider */
.stSelectbox > div > div {
    background: #161B22 !important; border-color: #30363D !important;
    color: #C9D1D9 !important; border-radius: 6px !important;
}
.stSlider > div > div > div > div { background: #58A6FF !important; }
label { color: #8B949E !important; font-size: 11px !important; }

/* Scrollbar */
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: #0D1117; }
::-webkit-scrollbar-thumb { background: #30363D; border-radius: 3px; }
</style>
"""

st.markdown(CSS, unsafe_allow_html=True)


# ── Session state ─────────────────────────────────────────────────
def init_state():
    defaults = {
        "moteur"        : None,
        "generateur"    : None,
        "pret"          : False,
        "messages"      : [],
        "historique_llm": [],
        "input_key"     : 0,
        "en_cours"      : False,
        "filtre_lang"   : "Tous",
        "top_k"         : 5,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()


@st.cache_resource(show_spinner=False)
def charger_systeme():
    return RetrievalHybride(), GenerateurReponse()


# ── SIDEBAR ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div class="sidebar-logo">
        <div class="sidebar-logo-row">
            <span class="sidebar-logo-icon">⬡</span>
            <span class="sidebar-logo-name">AssistDoc</span>
        </div>
        <div class="sidebar-tagline">Documentation GitHub · FR</div>
    </div>
    """, unsafe_allow_html=True)

    nb_msg = len([m for m in st.session_state.messages if m["role"] == "assistant"])
    st.markdown(f"""
    <div class="sidebar-section">
        <div class="sidebar-section-title">Corpus</div>
        <div class="stat-grid">
            <div class="stat-card"><span class="num">87K</span><span class="lbl">Chunks</span></div>
            <div class="stat-card"><span class="num">289</span><span class="lbl">Repos</span></div>
            <div class="stat-card"><span class="num">{nb_msg}</span><span class="lbl">Réponses</span></div>
            <div class="stat-card"><span class="num">13</span><span class="lbl">Langages</span></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="sidebar-section">
        <div class="sidebar-section-title">Paramètres</div>
    </div>
    """, unsafe_allow_html=True)

    st.session_state.filtre_lang = st.selectbox(
        "Langage",
        ["Tous","Python","JavaScript","TypeScript","Java","Go","Rust","C","C++","PHP","Ruby"],
        key="sel_lang"
    )
    st.session_state.top_k = st.slider("Sources", 3, 10, 5, key="top_k_slider")

    st.markdown("<div style='padding:12px 20px 8px;'>", unsafe_allow_html=True)
    if st.button("✦ Nouvelle conversation", use_container_width=True):
        st.session_state.messages       = []
        st.session_state.historique_llm = []
        st.session_state.input_key     += 1
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("""
    <div style="padding:16px 20px;border-top:1px solid #21262D;margin-top:8px;">
        <div style="font-size:10px;color:#6E7681;letter-spacing:0.5px;text-transform:uppercase;margin-bottom:6px;">Modèle</div>
        <div style="font-family:'IBM Plex Mono',monospace;font-size:11px;color:#58A6FF;">llama-3.3-70b-versatile</div>
        <div style="font-size:10px;color:#484F58;margin-top:2px;">Groq · Qdrant · BM25 + Dense</div>
    </div>
    """, unsafe_allow_html=True)


# ── Chargement ────────────────────────────────────────────────────
if not st.session_state.pret:
    ph = st.empty()
    ph.markdown("""
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:60vh;gap:16px;">
        <div style="font-size:40px;">⬡</div>
        <div style="font-family:'IBM Plex Mono',monospace;font-size:14px;color:#C9D1D9;">
            Initialisation du système RAG…
        </div>
    </div>
    """, unsafe_allow_html=True)
    try:
        m, g = charger_systeme()
        st.session_state.moteur     = m
        st.session_state.generateur = g
        st.session_state.pret       = True
        ph.empty()
        st.rerun()
    except Exception as e:
        ph.error(f"❌ Erreur : {e}")
        st.stop()


# ── TOPBAR ────────────────────────────────────────────────────────
nb_total = len(st.session_state.messages)
st.markdown(f"""
<div class="topbar">
    <span class="topbar-title">AssistDoc · Documentation GitHub francophone</span>
    <div class="topbar-right">
        <span><span class="status-dot"></span>Système actif</span>
        <span style="color:#3FB950">llama-3.3-70b</span>
        <span>{nb_total // 2} échange{'s' if nb_total//2 > 1 else ''}</span>
    </div>
</div>
""", unsafe_allow_html=True)


# ── ZONE CHAT ─────────────────────────────────────────────────────
col_main = st.columns([1, 10, 1])[1]

with col_main:
    st.markdown('<div class="chat-wrapper">', unsafe_allow_html=True)

    # Écran de bienvenue
    if not st.session_state.messages:
        st.markdown("""
        <div class="welcome-screen">
            <div class="welcome-icon">⬡</div>
            <div class="welcome-title">Bonjour ! Je suis <strong>AssistDoc</strong></div>
            <div class="welcome-sub">
                Posez vos questions techniques en français.<br>
                Je recherche dans 87 889 chunks de documentation GitHub<br>
                et génère des réponses sourcées avec du code concret.
            </div>
        </div>
        """, unsafe_allow_html=True)

        suggestions = [
            ("🐍", "Comment créer une API REST avec Flask ?"),
            ("🔐", "Implémenter l'authentification JWT ?"),
            ("⚛️", "Les hooks React useState et useEffect"),
            ("🐳", "Containeriser une app Python avec Docker"),
            ("🗄️", "Utiliser SQLAlchemy avec PostgreSQL"),
            ("⚡", "Créer une API rapide avec FastAPI"),
        ]
        cols = st.columns(2)
        for i, (icon, sug) in enumerate(suggestions):
            with cols[i % 2]:
                if st.button(f"{icon}  {sug}", key=f"sug_{i}", use_container_width=True):
                    st.session_state["_sug"] = sug
                    st.rerun()

    # Messages
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.markdown(f"""
            <div class="chat-bubble user">
                <div class="bubble-avatar user-av">M</div>
                <div class="bubble-content">
                    <div class="bubble-user-text">{msg["content"]}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            docs    = msg.get("docs", [])
            tokens  = msg.get("tokens", 0)
            latence = msg.get("latence", 0)

            st.markdown("""
            <div class="chat-bubble">
                <div class="bubble-avatar assistant">⬡</div>
                <div class="bubble-content">
                    <div class="bubble-assistant-text">
            """, unsafe_allow_html=True)

            st.markdown(msg["content"])

            st.markdown(f"""
                    </div>
                    <div class="bubble-meta">
                        <span>⏱ {latence:.1f}s</span>
                        <span>📄 {len(docs)} sources</span>
                        <span>🔢 {tokens} tokens</span>
                    </div>
            """, unsafe_allow_html=True)

            if docs:
                st.markdown('<div class="sources-mini">', unsafe_allow_html=True)
                for doc in docs[:5]:
                    url  = doc.get("url", "#")
                    repo = doc.get("nom_complet", "N/A").split("/")[-1]
                    lang = doc.get("langage", "")
                    st.markdown(
                        f'<a class="source-tag" href="{url}" target="_blank">⬡ {repo} · {lang}</a>',
                        unsafe_allow_html=True
                    )
                st.markdown('</div>', unsafe_allow_html=True)

            st.markdown("</div></div>", unsafe_allow_html=True)

    # Indicateur thinking
    if st.session_state.en_cours:
        st.markdown("""
        <div class="thinking-bubble">
            <div class="bubble-avatar assistant">⬡</div>
            <div class="thinking-content">
                <div class="thinking-dots">
                    <span></span><span></span><span></span>
                </div>
                <div class="thinking-label">Recherche en cours…</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)


# ── INPUT ─────────────────────────────────────────────────────────
with col_main:
    st.markdown('<div class="input-zone"><div class="input-inner">', unsafe_allow_html=True)
    col_i, col_b = st.columns([9, 1])

    with col_i:
        valeur = st.session_state.pop("_sug", "")
        question = st.text_input(
            "q",
            value            = valeur,
            placeholder      = "Posez votre question technique en français…",
            key              = f"inp_{st.session_state.input_key}",
            label_visibility = "collapsed",
        )
    with col_b:
        envoyer = st.button("↑", use_container_width=True)

    st.markdown('</div></div>', unsafe_allow_html=True)


# ── TRAITEMENT ────────────────────────────────────────────────────
q_finale = (question if (envoyer and question.strip()) else None) or (valeur or None)

if q_finale and q_finale.strip() and not st.session_state.en_cours:
    q = q_finale.strip()
    st.session_state.messages.append({"role": "user", "content": q})
    st.session_state.historique_llm.append({"role": "user", "content": q})
    st.session_state.input_key += 1
    st.session_state.en_cours   = True
    st.rerun()


# ── GÉNÉRATION ────────────────────────────────────────────────────
if st.session_state.en_cours and st.session_state.messages:
    users = [m for m in st.session_state.messages if m["role"] == "user"]
    if not users:
        st.session_state.en_cours = False
        st.stop()

    # Déjà répondu ?
    if st.session_state.messages[-1]["role"] == "assistant":
        st.session_state.en_cours = False
        st.rerun()

    q = users[-1]["content"]
    filtres = (
        {"langage": st.session_state.filtre_lang}
        if st.session_state.filtre_lang != "Tous" else None
    )

    try:
        t0   = time.time()
        docs = st.session_state.moteur.rechercher(
            q, top_k_retrieval=20,
            top_k_final=st.session_state.top_k,
            filtres=filtres,
        )
        res = st.session_state.generateur.generer(
            question   = q,
            documents  = docs,
            historique = st.session_state.historique_llm[:-1],
        )
        latence = time.time() - t0

        st.session_state.messages.append({
            "role"   : "assistant",
            "content": res["reponse_seule"],
            "docs"   : docs,
            "tokens" : res["tokens_utilises"],
            "latence": latence,
        })
        st.session_state.historique_llm.append({
            "role": "assistant", "content": res["reponse_seule"]
        })
        if len(st.session_state.historique_llm) > 20:
            st.session_state.historique_llm = st.session_state.historique_llm[-20:]

    except Exception as e:
        st.session_state.messages.append({
            "role": "assistant", "content": f"❌ Erreur : {e}",
            "docs": [], "tokens": 0, "latence": 0,
        })

    st.session_state.en_cours = False
    st.rerun()