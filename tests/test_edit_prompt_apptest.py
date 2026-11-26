"""Test fonctionnel Streamlit : édition de prompt + lecture réelle du widget."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SCRIPT = r'''
import streamlit as st
from app.edition_conversation import appliquer_edition_prompt, edition_autorisee

st.session_state.setdefault("messages", [
    {"role": "user", "content": "Bonjour", "quota_decompte": True},
    {"role": "assistant", "content": "Salut !"},
    {"role": "user", "content": "Q2", "quota_decompte": True},
    {"role": "assistant", "content": "R2"},
])
st.session_state.setdefault("historique_llm", [])
st.session_state.setdefault("en_cours", False)
st.session_state.setdefault("edit_msg_idx", None)
st.session_state.setdefault("figee", False)
st.session_state.setdefault("input_key", 0)
st.session_state.setdefault("synced", [])

def sync():
    st.session_state.synced.append(
        [m["content"] for m in st.session_state.messages]
    )

if st.button("ouvrir_edit"):
    st.session_state.edit_msg_idx = 0
    st.session_state["inline_edit_user_0"] = st.session_state.messages[0]["content"]
    st.rerun()

if st.session_state.edit_msg_idx == 0:
    cle = "inline_edit_user_0"
    if cle not in st.session_state:
        st.session_state[cle] = st.session_state.messages[0]["content"]
    with st.form("edit_form_user_0", border=False):
        st.text_area("edit", key=cle, label_visibility="collapsed")
        annuler = st.form_submit_button("Annuler")
        envoyer = st.form_submit_button("Envoyer", type="primary")
    if annuler:
        st.session_state.edit_msg_idx = None
        st.rerun()
    if envoyer:
        texte = str(st.session_state.get(cle) or "").strip()
        assert edition_autorisee(st.session_state, figee=False)
        res = appliquer_edition_prompt(st.session_state.messages, 0, texte)
        assert res is not None
        msgs, hist = res
        st.session_state.messages = msgs
        st.session_state.historique_llm = hist
        st.session_state.edit_msg_idx = None
        st.session_state.en_cours = True
        st.session_state.input_key += 1
        sync()
        st.rerun()

st.write("en_cours=" + str(st.session_state.en_cours))
st.write("n_msgs=" + str(len(st.session_state.messages)))
st.write("user0=" + st.session_state.messages[0]["content"])
'''


@pytest.fixture
def at():
    mod = pytest.importorskip("streamlit.testing.v1")
    return mod.AppTest.from_string(SCRIPT, default_timeout=30)


def test_edit_form_recupere_nouvelle_valeur_et_tronque(at):
    app = at.run()
    assert not app.exception
    app.button[0].click().run()  # ouvrir_edit
    assert app.session_state.edit_msg_idx == 0

    # Simule la saisie utilisateur dans le widget form (état Streamlit réel)
    app.session_state["inline_edit_user_0"] = "Bonjour, explique-moi SQLAlchemy"
    # Soumet le formulaire via le bouton Envoyer (index 1 : Annuler=0, Envoyer=1)
    submits = list(app.button) + list(getattr(app, "form_submit_button", lambda: [])() or [])
    # AppTest expose form_submit_button
    envoyer = None
    for b in app.button:
        if "Envoyer" in (b.label or ""):
            envoyer = b
            break
    if envoyer is None and hasattr(app, "form_submit_button"):
        for b in app.form_submit_button:
            if "Envoyer" in (getattr(b, "label", None) or ""):
                envoyer = b
                break
    assert envoyer is not None, "bouton Envoyer introuvable"
    envoyer.click().run()

    assert not app.exception
    assert app.session_state.en_cours is True
    assert len(app.session_state.messages) == 1
    assert app.session_state.messages[0]["content"] == "Bonjour, explique-moi SQLAlchemy"
    assert app.session_state.edit_msg_idx is None
    assert app.session_state.synced[-1] == ["Bonjour, explique-moi SQLAlchemy"]
