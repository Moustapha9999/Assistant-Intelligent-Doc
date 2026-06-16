"""
Interface AssistDoc — Chat conversationnel avec upload de fichiers
ISI KOMUNIK · Master IAGE
"""

import sys, os, time
from pathlib import Path
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from retrieval.retrieval_hybride import RetrievalHybride
from generation.generateur_reponse import GenerateurReponse
from app.gestionnaire_fichiers import traiter_fichier, formater_pour_prompt

st.set_page_config(
    page_title="AssistDoc",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="expanded",
)

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

*, *::before, *::after { box-sizing: border-box; }
html, body, [data-testid="stAppViewContainer"] {
    background: #0D1117 !important; color: #E6EDF3;
    font-family: 'IBM Plex Sans', sans-serif;
}
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stToolbar"] { display: none; }
.block-container { padding: 0 !important; max-width: 100% !important; }

/* SIDEBAR */
[data-testid="stSidebar"] {
    background: #0D1117 !important;
    border-right: 1px solid #21262D !important;
}
.sb-logo {
    padding: 20px 16px 14px;
    border-bottom: 1px solid #21262D;
    display: flex; align-items: center; gap: 10px;
}
.sb-logo-icon { font-size: 20px; color: #58A6FF; }
.sb-logo-name {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 15px; font-weight: 600; color: #E6EDF3;
}
.sb-section {
    padding: 12px 16px 8px;
    border-bottom: 1px solid #21262D;
}
.sb-section-title {
    font-size: 9px; font-weight: 600;
    letter-spacing: 1.2px; text-transform: uppercase;
    color: #6E7681; margin-bottom: 10px;
}
.stat-row { display: flex; gap: 6px; margin-bottom: 4px; }
.stat-box {
    flex: 1; background: #161B22; border: 1px solid #21262D;
    border-radius: 5px; padding: 8px 6px; text-align: center;
}
.stat-box .n {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 15px; font-weight: 600; color: #58A6FF; display: block;
}
.stat-box .l {
    font-size: 8px; color: #6E7681;
    text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-top: 2px;
}

/* TOPBAR */
.topbar {
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 28px; border-bottom: 1px solid #21262D;
    background: #0D1117; position: sticky; top: 0; z-index: 100;
}
.topbar-l { font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #6E7681; }
.topbar-r { display: flex; align-items: center; gap: 14px; font-size: 10px; color: #6E7681; font-family: 'IBM Plex Mono', monospace; }
.dot { width: 6px; height: 6px; border-radius: 50%; background: #3FB950; display: inline-block; margin-right: 4px; box-shadow: 0 0 5px #3FB950; }

/* CHAT */
.chat-wrap { max-width: 820px; margin: 0 auto; padding: 20px 28px 160px; }

.bubble { display: flex; gap: 12px; margin-bottom: 20px; }
.bubble.user { flex-direction: row-reverse; }
.av {
    width: 32px; height: 32px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 13px; flex-shrink: 0;
    font-family: 'IBM Plex Mono', monospace; font-weight: 600;
}
.av.bot { background: rgba(88,166,255,0.15); border: 1px solid rgba(88,166,255,0.3); color: #58A6FF; }
.av.usr { background: rgba(63,185,80,0.15); border: 1px solid rgba(63,185,80,0.3); color: #3FB950; }
.bc { flex: 1; max-width: 88%; }

.user-txt {
    background: #161B22; border: 1px solid #30363D;
    border-radius: 12px 12px 4px 12px;
    padding: 10px 14px; font-size: 14px; color: #E6EDF3; line-height: 1.6;
}
.bot-txt {
    background: #0D1117; border: 1px solid #21262D;
    border-radius: 12px 12px 12px 4px;
    padding: 18px 22px; font-size: 14px; color: #C9D1D9; line-height: 1.8;
}
.bot-txt h1,.bot-txt h2 { color: #E6EDF3; font-weight: 600; margin: 14px 0 6px; font-size: 16px; }
.bot-txt h3 { color: #C9D1D9; font-weight: 600; margin: 10px 0 4px; font-size: 14px; }
.bot-txt code {
    font-family: 'IBM Plex Mono', monospace; font-size: 12px;
    background: #161B22; border: 1px solid #30363D;
    border-radius: 3px; padding: 1px 4px; color: #79B8FF;
}
.bot-txt pre {
    background: #161B22 !important; border: 1px solid #30363D !important;
    border-radius: 7px !important; padding: 14px !important;
    overflow-x: auto !important; font-size: 12px !important;
    line-height: 1.6 !important; margin: 10px 0 !important;
}
.bot-txt pre code { background: none !important; border: none !important; padding: 0 !important; color: #E6EDF3 !important; }
.bot-txt ul,.bot-txt ol { padding-left: 18px; margin: 6px 0; }
.bot-txt li { margin-bottom: 3px; }
.bot-txt a { color: #58A6FF; text-decoration: none; }
.bot-txt a:hover { text-decoration: underline; }
.bot-txt strong { color: #E6EDF3; }
.bot-txt hr { border: none; border-top: 1px solid #21262D; margin: 12px 0; }

.msg-meta { display: flex; gap: 8px; margin-top: 6px; font-size: 9px; color: #484F58; font-family: 'IBM Plex Mono', monospace; }
.src-tags { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
.src-tag {
    font-size: 9px; font-family: 'IBM Plex Mono', monospace;
    background: #161B22; border: 1px solid #21262D;
    border-radius: 3px; padding: 2px 7px; color: #6E7681; text-decoration: none;
}
.src-tag:hover { border-color: #58A6FF; color: #58A6FF; }

/* Fichiers attachés dans le message */
.file-badge {
    display: inline-flex; align-items: center; gap: 5px;
    background: #161B22; border: 1px solid #30363D;
    border-radius: 6px; padding: 4px 10px; margin: 4px 4px 0 0;
    font-size: 11px; color: #8B949E;
    font-family: 'IBM Plex Mono', monospace;
}
.file-badge .fi { color: #58A6FF; }

/* WELCOME */
.welcome { text-align: center; padding: 60px 28px 32px; max-width: 580px; margin: 0 auto; }
.wicon { font-size: 40px; margin-bottom: 16px; opacity: 0.7; }
.wtitle { font-size: 26px; font-weight: 300; color: #E6EDF3; margin-bottom: 6px; }
.wtitle strong { font-weight: 600; color: #58A6FF; }
.wsub { font-size: 13px; color: #8B949E; line-height: 1.6; margin-bottom: 28px; }

/* THINKING */
.think { display: flex; gap: 12px; margin-bottom: 20px; }
.think-box {
    background: #0D1117; border: 1px solid #21262D;
    border-radius: 12px 12px 12px 4px; padding: 14px 18px;
}
.tdots { display: flex; gap: 5px; align-items: center; }
.tdots span {
    width: 5px; height: 5px; border-radius: 50%;
    background: #58A6FF; animation: bounce 1.2s infinite;
}
.tdots span:nth-child(2) { animation-delay: 0.2s; }
.tdots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce { 0%,60%,100%{transform:translateY(0)} 30%{transform:translateY(-5px)} }
.tlabel { font-size: 11px; color: #6E7681; font-family: 'IBM Plex Mono', monospace; margin-top: 6px; }

/* INPUT ZONE */
.input-zone {
    position: fixed; bottom: 0; left: 0; right: 0;
    background: linear-gradient(transparent, #0D1117 25%);
    padding: 12px 0 20px; z-index: 200;
}
.input-inner { max-width: 820px; margin: 0 auto; padding: 0 28px; }

/* Upload preview */
.upload-preview {
    display: flex; flex-wrap: wrap; gap: 6px;
    margin-bottom: 8px; padding: 8px 12px;
    background: #161B22; border: 1px solid #21262D;
    border-radius: 8px;
}
.up-file {
    display: flex; align-items: center; gap: 5px;
    font-size: 11px; color: #8B949E;
    font-family: 'IBM Plex Mono', monospace;
    background: #0D1117; border: 1px solid #30363D;
    border-radius: 4px; padding: 3px 8px;
}
.up-file .ufi { color: #58A6FF; }

/* Streamlit overrides */
.stTextInput { margin: 0 !important; }
.stTextInput > div > div > input {
    background: #161B22 !important; border: 1px solid #30363D !important;
    border-radius: 8px !important; color: #E6EDF3 !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
    font-size: 14px !important; padding: 12px 16px !important;
    box-shadow: none !important;
}
.stTextInput > div > div > input:focus {
    border-color: #58A6FF !important;
    box-shadow: 0 0 0 2px rgba(88,166,255,0.15) !important;
}
.stTextInput > div > div > input::placeholder { color: #484F58 !important; }
.stTextInput label { display: none !important; }

.stButton > button {
    background: #58A6FF !important; color: #0D1117 !important;
    border: none !important; border-radius: 8px !important;
    font-weight: 600 !important; font-size: 13px !important;
    padding: 11px 18px !important; width: 100% !important;
    cursor: pointer !important; transition: background 0.15s !important;
}
.stButton > button:hover { background: #79B8FF !important; }

/* File uploader */
[data-testid="stFileUploader"] {
    background: #161B22 !important; border: 1px dashed #30363D !important;
    border-radius: 8px !important; padding: 8px !important;
}
[data-testid="stFileUploader"] label { color: #8B949E !important; font-size: 11px !important; }
[data-testid="stFileUploaderDropzone"] { background: #161B22 !important; border: none !important; padding: 6px !important; }
[data-testid="stFileUploaderDropzoneInstructions"] { color: #6E7681 !important; font-size: 11px !important; }

.stSelectbox > div > div { background: #161B22 !important; border-color: #30363D !important; color: #C9D1D9 !important; border-radius: 6px !important; }
.stSlider > div > div > div > div { background: #58A6FF !important; }
label { color: #8B949E !important; font-size: 11px !important; }
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: #0D1117; }
::-webkit-scrollbar-thumb { background: #30363D; border-radius: 2px; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ── Session state ─────────────────────────────────────────────────
def init():
    d = {
        "moteur": None, "generateur": None, "pret": False,
        "messages": [], "historique_llm": [],
        "input_key": 0, "en_cours": False,
        "filtre_lang": "Tous", "top_k": 5,
        "fichiers_en_attente": [],  # fichiers uploadés pas encore envoyés
    }
    for k, v in d.items():
        if k not in st.session_state:
            st.session_state[k] = v

init()


@st.cache_resource(show_spinner=False)
def charger():
    return RetrievalHybride(), GenerateurReponse()


# ── ICÔNES par type de fichier ────────────────────────────────────
def icone_fichier(nom: str) -> str:
    ext = Path(nom).suffix.lower()
    if ext == ".pdf":                          return "📄"
    if ext in {".png",".jpg",".jpeg",".gif",".webp"}: return "🖼️"
    if ext in {".py"}:                        return "🐍"
    if ext in {".js",".ts"}:                  return "🟨"
    if ext in {".java"}:                      return "☕"
    if ext in {".c",".cpp",".h"}:             return "⚙️"
    if ext in {".go"}:                        return "🐹"
    if ext in {".rs"}:                        return "🦀"
    if ext in {".md",".txt",".rst"}:          return "📝"
    if ext in {".json",".yaml",".yml",".toml"}: return "⚙️"
    return "📎"


# ── SIDEBAR ───────────────────────────────────────────────────────
with st.sidebar:
    nb_rep = len([m for m in st.session_state.messages if m["role"] == "assistant"])

    st.markdown(f"""
    <div class="sb-logo">
        <span class="sb-logo-icon">⬡</span>
        <span class="sb-logo-name">AssistDoc</span>
    </div>
    <div class="sb-section">
        <div class="sb-section-title">Corpus</div>
        <div class="stat-row">
            <div class="stat-box"><span class="n">87K</span><span class="l">Chunks</span></div>
            <div class="stat-box"><span class="n">289</span><span class="l">Repos</span></div>
        </div>
        <div class="stat-row">
            <div class="stat-box"><span class="n">{nb_rep}</span><span class="l">Réponses</span></div>
            <div class="stat-box"><span class="n">13</span><span class="l">Langages</span></div>
        </div>
    </div>
    <div class="sb-section">
        <div class="sb-section-title">Paramètres</div>
    </div>
    """, unsafe_allow_html=True)

    st.session_state.filtre_lang = st.selectbox(
        "Langage",
        ["Tous","Python","JavaScript","TypeScript","Java","Go","Rust","C","C++","PHP","Ruby"],
        key="sel_lang"
    )
    st.session_state.top_k = st.slider("Sources", 3, 10, 5, key="topk")

    st.markdown("""<div class="sb-section"><div class="sb-section-title">Actions</div></div>""",
                unsafe_allow_html=True)
    st.markdown("<div style='padding:8px 16px;'>", unsafe_allow_html=True)
    if st.button("✦ Nouvelle conversation", use_container_width=True):
        st.session_state.messages          = []
        st.session_state.historique_llm    = []
        st.session_state.fichiers_en_attente = []
        st.session_state.input_key        += 1
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Historique des questions ──
    questions_user = [m["content"] for m in st.session_state.messages if m["role"] == "user"]
    if questions_user:
        st.markdown("""<div class="sb-section"><div class="sb-section-title">Historique</div></div>""",
                    unsafe_allow_html=True)
        st.markdown("<div style='padding:0 16px 12px;max-height:240px;overflow-y:auto;'>", unsafe_allow_html=True)
        for i, q in enumerate(reversed(questions_user[-12:]), 1):
            num = len(questions_user) - i + 1
            txt = q[:48] + ("…" if len(q) > 48 else "")
            st.markdown(
                f'<div style="font-size:11px;color:#8B949E;padding:5px 8px;margin-bottom:3px;'
                f'background:#161B22;border:1px solid #21262D;border-radius:5px;'
                f'font-family:\'IBM Plex Mono\',monospace;white-space:nowrap;overflow:hidden;'
                f'text-overflow:ellipsis;">#{num} {txt}</div>',
                unsafe_allow_html=True
            )
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("""
    <div style="padding:12px 16px;border-top:1px solid #21262D;margin-top:6px;">
        <div style="font-size:9px;color:#6E7681;letter-spacing:0.8px;text-transform:uppercase;margin-bottom:4px;">Modèle</div>
        <div style="font-family:'IBM Plex Mono',monospace;font-size:10px;color:#58A6FF;">llama-3.3-70b-versatile</div>
        <div style="font-size:9px;color:#484F58;margin-top:2px;">Groq · Qdrant · BM25 + Dense</div>
    </div>
    """, unsafe_allow_html=True)


# ── Chargement ────────────────────────────────────────────────────
if not st.session_state.pret:
    ph = st.empty()
    ph.markdown("""
    <div style="display:flex;flex-direction:column;align-items:center;
                justify-content:center;height:60vh;gap:14px;">
        <div style="font-size:36px;">⬡</div>
        <div style="font-family:'IBM Plex Mono',monospace;font-size:13px;color:#C9D1D9;">
            Initialisation…
        </div>
    </div>
    """, unsafe_allow_html=True)
    try:
        m, g = charger()
        st.session_state.moteur     = m
        st.session_state.generateur = g
        st.session_state.pret       = True
        ph.empty()
        st.rerun()
    except Exception as e:
        ph.error(f"❌ {e}")
        st.stop()


# ── TOPBAR ────────────────────────────────────────────────────────
nb = len(st.session_state.messages) // 2
st.markdown(f"""
<div class="topbar">
    <span class="topbar-l">AssistDoc · Documentation GitHub francophone</span>
    <div class="topbar-r">
        <span><span class="dot"></span>Actif</span>
        <span style="color:#3FB950">llama-3.3-70b</span>
        <span>{nb} échange{'s' if nb>1 else ''}</span>
    </div>
</div>
""", unsafe_allow_html=True)


# ── CHAT ──────────────────────────────────────────────────────────
col = st.columns([1, 10, 1])[1]

with col:
    st.markdown('<div class="chat-wrap">', unsafe_allow_html=True)

    # Écran bienvenue
    if not st.session_state.messages:
        st.markdown("""
        <div class="welcome">
            <div class="wicon">⬡</div>
            <div class="wtitle">Bonjour ! Je suis <strong>AssistDoc</strong></div>
            <div class="wsub">
                Posez vos questions techniques en français.<br>
                Vous pouvez aussi <strong>joindre des fichiers</strong> :
                PDF, images, code, Markdown…
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
        cs = st.columns(2)
        for i, (icon, sug) in enumerate(suggestions):
            with cs[i % 2]:
                if st.button(f"{icon}  {sug}", key=f"s{i}", use_container_width=True):
                    st.session_state["_sug"] = sug
                    st.rerun()

    # Affichage messages
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            fichiers_msg = msg.get("fichiers", [])
            badges = "".join([
                f'<span class="file-badge"><span class="fi">{icone_fichier(f["nom"])}</span>{f["nom"]}</span>'
                for f in fichiers_msg
            ])
            st.markdown(f"""
            <div class="bubble user">
                <div class="av usr">M</div>
                <div class="bc">
                    {'<div style="margin-bottom:6px;">' + badges + '</div>' if badges else ''}
                    <div class="user-txt">{msg["content"]}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            docs    = msg.get("docs", [])
            tokens  = msg.get("tokens", 0)
            latence = msg.get("latence", 0)

            st.markdown("""
            <div class="bubble">
                <div class="av bot">⬡</div>
                <div class="bc">
                    <div class="bot-txt">
            """, unsafe_allow_html=True)

            st.markdown(msg["content"])

            st.markdown(f"""
                    </div>
                    <div class="msg-meta">
                        <span>⏱ {latence:.1f}s</span>
                        <span>📄 {len(docs)} sources</span>
                        <span>🔢 {tokens} tokens</span>
                    </div>
            """, unsafe_allow_html=True)

            if docs:
                st.markdown('<div class="src-tags">', unsafe_allow_html=True)
                for doc in docs[:5]:
                    url  = doc.get("url", "#")
                    repo = doc.get("nom_complet", "N/A").split("/")[-1]
                    lang = doc.get("langage", "")
                    st.markdown(
                        f'<a class="src-tag" href="{url}" target="_blank">⬡ {repo} · {lang}</a>',
                        unsafe_allow_html=True
                    )
                st.markdown('</div>', unsafe_allow_html=True)

            st.markdown("</div></div>", unsafe_allow_html=True)

    if st.session_state.en_cours:
        st.markdown("""
        <div class="think">
            <div class="av bot">⬡</div>
            <div class="think-box">
                <div class="tdots"><span></span><span></span><span></span></div>
                <div class="tlabel">Recherche · Génération en cours…</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)


# ── INPUT + UPLOAD ────────────────────────────────────────────────
with col:
    st.markdown('<div class="input-zone"><div class="input-inner">', unsafe_allow_html=True)

    # Preview des fichiers en attente
    if st.session_state.fichiers_en_attente:
        badges = "".join([
            f'<span class="up-file"><span class="ufi">{icone_fichier(f["nom"])}</span>{f["nom"]}</span>'
            for f in st.session_state.fichiers_en_attente
        ])
        st.markdown(f'<div class="upload-preview">{badges}</div>', unsafe_allow_html=True)

    # Ligne input + bouton
    c1, c2 = st.columns([9, 1])
    with c1:
        valeur = st.session_state.pop("_sug", "")
        question = st.text_input(
            "q",
            value=valeur,
            placeholder="Posez votre question… ou joignez un fichier ↓",
            key=f"inp_{st.session_state.input_key}",
            label_visibility="collapsed",
        )
    with c2:
        envoyer = st.button("↑", use_container_width=True)

    # Upload fichiers
    fichiers_up = st.file_uploader(
        "📎 Joindre des fichiers (PDF, images, code, Markdown…)",
        accept_multiple_files=True,
        key=f"up_{st.session_state.input_key}",
        label_visibility="visible",
    )

    # Traiter les fichiers uploadés
    if fichiers_up:
        traites = [traiter_fichier(f) for f in fichiers_up]
        st.session_state.fichiers_en_attente = traites

    st.markdown('</div></div>', unsafe_allow_html=True)


# ── TRAITEMENT ────────────────────────────────────────────────────
q_finale = (question if (envoyer and question.strip()) else None) or (valeur or None)

if q_finale and q_finale.strip() and not st.session_state.en_cours:
    q         = q_finale.strip()
    fichiers  = st.session_state.fichiers_en_attente.copy()

    st.session_state.messages.append({
        "role": "user", "content": q, "fichiers": fichiers
    })
    st.session_state.historique_llm.append({"role": "user", "content": q})
    st.session_state.fichiers_en_attente = []
    st.session_state.input_key          += 1
    st.session_state.en_cours            = True
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

    # Contexte fichiers
    contexte_fichiers = formater_pour_prompt(fichiers_msg)

    # Question enrichie avec contenu des fichiers
    q_enrichie = q
    if contexte_fichiers:
        q_enrichie = q + "\n\n[Fichiers joints par l'utilisateur :]\n" + contexte_fichiers

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
            question   = q_enrichie,
            documents  = docs,
            historique = st.session_state.historique_llm[:-1],
        )
        latence = time.time() - t0

        st.session_state.messages.append({
            "role": "assistant", "content": res["reponse_seule"],
            "docs": docs, "tokens": res["tokens_utilises"], "latence": latence,
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