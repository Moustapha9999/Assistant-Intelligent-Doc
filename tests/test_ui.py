"""Système d'interface : thème, notifications, confirmations, fenêtres (sans navigateur)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app import ui_composants as ui  # noqa: E402
from app.ui_theme import CSS_COMPOSANTS, JETONS, css_theme  # noqa: E402

APP = ROOT / "src" / "app"


# ── Thème ────────────────────────────────────────────────────────────────────


def test_jetons_utilises_sont_definis():
    utilises = set(re.findall(r"var\((--ui-[\w-]+)\)", CSS_COMPOSANTS))
    assert utilises, "le CSS commun doit s'appuyer sur les jetons"
    assert utilises <= set(JETONS), utilises - set(JETONS)


def test_css_commun_sans_selecteur_global_ni_important():
    for ligne in CSS_COMPOSANTS.splitlines():
        brut = ligne.strip()
        assert not re.match(r"^(button|label|input|div|p|a)\s*[,{]", brut), brut
    assert "!important" not in CSS_COMPOSANTS


def test_css_theme_est_un_bloc_style_unique():
    css = css_theme()
    assert css.startswith("<style>") and css.endswith("</style>")
    assert css.count("<style>") == 1


def test_largeurs_fenetres_non_forcees():
    """La largeur vient de st.dialog(width=...) : aucun CSS ne doit l'imposer."""
    for nom in ("accueil.py", "auth_basique.py", "admin_page.py"):
        src = (APP / nom).read_text(encoding="utf-8")
        assert not re.search(r'stDialog"\]\s*div\[role="dialog"\]\s*\{\{?\s*width', src), nom
    bloc = CSS_COMPOSANTS.split("Fenêtres modales")[1].split("Champs")[0]
    assert not re.search(r"(?<![-\w])width\s*:", bloc)


def test_pages_sans_surcharge_globale_de_boutons():
    for nom in ("accueil.py", "admin_page.py", "auth_basique.py"):
        src = (APP / nom).read_text(encoding="utf-8")
        assert not re.search(r'^\s*\.stButton\s*>?\s*button(\[kind="\w+"\])?\s*\{', src, re.M), nom
        assert not re.search(r'^\s*button\[kind="\w+"\]', src, re.M), nom
        assert not re.search(r"^\s*label\s*\{", src, re.M), nom
    accueil = (APP / "accueil.py").read_text(encoding="utf-8")
    assert "st-key-confirm_del" not in accueil and "del-dialog" not in accueil


def test_aucune_exception_affichee_brute():
    """Pas de `{e}` / `{exc}` dans un message montré à l'utilisateur."""
    motif = re.compile(
        r"st\.(error|warning|caption|info|success|toast)\(\s*f[\"'][^\"']*\{(e|exc|err)\}"
    )
    for nom in ("accueil.py", "admin_page.py", "auth_basique.py"):
        src = (APP / nom).read_text(encoding="utf-8")
        assert not motif.search(src), nom
    corpus = (APP / "admin_corpus.py").read_text(encoding="utf-8")
    assert not re.search(r"return False, f\"[^\"]*\{exc\}", corpus)


# ── Notifications ────────────────────────────────────────────────────────────


def test_notifications_file_sans_doublon_puis_videe():
    etat: dict = {}
    ui.notifier("Conversation supprimée.", etat=etat)
    ui.notifier("Conversation supprimée.", etat=etat)
    ui.notifier("Échec.", "erreur", etat=etat)
    vus = []
    affichees = ui.afficher_notifications(
        etat=etat, toast=lambda m, icon, duration: vus.append((m, icon, duration))
    )
    assert [m for m, _ in affichees] == ["succes", "erreur"]
    assert [v[0] for v in vus] == ["Conversation supprimée.", "Échec."]
    assert vus[1][2] == "long", "une erreur doit rester lisible plus longtemps"
    assert ui.afficher_notifications(etat=etat, toast=lambda *a, **k: None) == []


def test_niveau_inconnu_refuse():
    with pytest.raises(ValueError):
        ui.notifier("x", "bravo", etat={})


def test_message_erreur_ne_montre_pas_l_exception(caplog):
    exc = RuntimeError("SELECT * FROM users WHERE token='abc' /srv/app/data.db")
    with caplog.at_level("WARNING", logger="assistdoc.ui"):
        texte = ui.message_erreur("Action impossible.", exc, "Réessayez.")
    assert texte == "Action impossible. Réessayez."
    assert "SELECT" not in texte and "/srv" not in texte
    assert "SELECT" in caplog.text, "le détail doit partir dans le journal"


# ── Confirmations ────────────────────────────────────────────────────────────


def test_annulation_ne_modifie_rien():
    etat: dict = {}
    appels = []
    ui.demander_confirmation("suppr", "conv-1", etat=etat)
    ui.annuler_confirmation("suppr", etat=etat)
    res = ui.executer_confirmation(
        "suppr", "conv-1", lambda: appels.append(1) or True, succes="ok", echec="ko", etat=etat
    )
    assert res is None and appels == []
    assert ui.CLE_NOTIFICATIONS not in etat


def test_confirmation_execute_une_seule_fois():
    etat: dict = {}
    appels = []
    ui.demander_confirmation("suppr", "conv-1", etat=etat)
    action = lambda: appels.append(1) or True  # noqa: E731
    premier = ui.executer_confirmation("suppr", "conv-1", action, succes="Supprimée.", echec="ko", etat=etat)
    second = ui.executer_confirmation("suppr", "conv-1", action, succes="Supprimée.", echec="ko", etat=etat)
    assert (premier, second) == (True, None)
    assert appels == [1], "un double clic ne doit pas exécuter deux fois l'action"
    assert etat[ui.CLE_NOTIFICATIONS] == [("succes", "Supprimée.")]
    assert ui.confirmation_en_attente("suppr", etat=etat) is None


def test_confirmation_pour_une_autre_cible_refusee():
    etat: dict = {}
    ui.demander_confirmation("suppr", "conv-1", etat=etat)
    assert ui.executer_confirmation("suppr", "conv-2", lambda: True, succes="ok", echec="ko", etat=etat) is None
    assert ui.confirmation_en_attente("suppr", etat=etat) == "conv-1"


@pytest.mark.parametrize("action", [lambda: False, lambda: 1 / 0])
def test_echec_sans_succes_annonce_et_demande_retablie(action):
    etat: dict = {}
    ui.demander_confirmation("suppr", ("col", "Docs"), etat=etat)
    res = ui.executer_confirmation(
        "suppr", ("col", "Docs"), action, succes="Supprimée.", echec="Suppression impossible.", etat=etat
    )
    assert res is False
    assert ui.CLE_NOTIFICATIONS not in etat, "aucun succès en cas d'échec"
    assert ui.confirmation_en_attente("suppr", etat=etat) == ("col", "Docs")
    assert ui.erreur_confirmation("suppr", etat=etat) == "Suppression impossible."
    assert ui.erreur_confirmation("suppr", etat=etat) == "", "message d'échec lu une seule fois"


# ── Contenu des fenêtres ─────────────────────────────────────────────────────


def test_texte_dialogue_echappe_le_nom():
    h = ui.html_texte_dialogue(
        "La conversation {nom} sera supprimée.", nom="<img src=x onerror=alert(1)>", note="Définitif <b>"
    )
    assert "<img" not in h and "&lt;img" in h
    assert "<strong>&lt;img" in h
    assert 'class="ui-note">Définitif &lt;b&gt;' in h


# ── Fenêtre réelle via AppTest (rendu Streamlit sans navigateur) ────────────

SCRIPT_DIALOGUE = '''
import streamlit as st
from app import ui_composants as ui

st.session_state.setdefault("base", ["a", "b"])
st.session_state.setdefault("appels", 0)
st.session_state.setdefault("echouer", False)


def supprimer(cible):
    st.session_state.appels += 1
    if st.session_state.echouer:
        return False
    st.session_state.base.remove(cible)
    return True


@st.dialog("Supprimer cette conversation ?", width="small")
def fenetre():
    cible = ui.confirmation_en_attente("suppr")
    ui.texte_dialogue("La conversation {nom} sera supprimée.", nom=cible,
                      note="Cette action ne pourra pas être annulée.")
    err = ui.erreur_confirmation("suppr")
    if err:
        ui.afficher_erreur(err)
    annuler, confirmer = ui.pied_dialogue("suppr", "Supprimer", danger=True)
    if annuler:
        ui.annuler_confirmation("suppr")
        st.rerun()
    if confirmer:
        if ui.executer_confirmation("suppr", cible, lambda: supprimer(cible),
                                    succes="Conversation supprimée.", echec="Échec de la suppression.") is not None:
            st.rerun()


ui.afficher_notifications()
if st.button("ouvrir"):
    ui.demander_confirmation("suppr", "a")
    st.rerun()
if ui.confirmation_en_attente("suppr"):
    fenetre()
st.write("base=" + ",".join(st.session_state.base))
'''


@pytest.fixture
def app_test():
    at_mod = pytest.importorskip("streamlit.testing.v1")
    at = at_mod.AppTest.from_string(SCRIPT_DIALOGUE, default_timeout=30)
    return at


def _boutons(at):
    return {b.key: b for b in at.button}


def _fenetre_ouverte(at) -> bool:
    """AppTest garde l'arbre du run interrompu par st.rerun : un run de plus donne l'écran réel."""
    at.run()
    return "danger_suppr_confirmer" in _boutons(at)


def test_apptest_annuler_puis_confirmer(app_test):
    at = app_test.run()
    [b for b in at.button if b.label == "ouvrir"][0].click().run()
    b = _boutons(at)
    assert "suppr_annuler" in b and "danger_suppr_confirmer" in b
    assert any("ui-dialog-texte" in m.value for m in at.markdown)

    b["suppr_annuler"].click().run()
    assert at.session_state["appels"] == 0
    assert at.session_state["base"] == ["a", "b"]
    assert "suppr" not in at.session_state
    assert not _fenetre_ouverte(at)

    [b for b in at.button if b.label == "ouvrir"][0].click().run()
    _boutons(at)["danger_suppr_confirmer"].click().run()
    assert at.session_state["appels"] == 1
    assert at.session_state["base"] == ["b"]
    assert [t.value for t in at.toast] == ["Conversation supprimée."]
    assert not _fenetre_ouverte(at), "la fenêtre se ferme après succès"
    assert not at.toast, "la notification n'est affichée qu'une fois"


def test_apptest_echec_garde_la_fenetre_ouverte(app_test):
    at = app_test
    at.session_state["echouer"] = True
    at.run()
    [b for b in at.button if b.label == "ouvrir"][0].click().run()
    _boutons(at)["danger_suppr_confirmer"].click().run()
    assert at.session_state["appels"] == 1
    assert at.session_state["base"] == ["a", "b"]
    assert not at.toast, "aucun succès annoncé"
    assert [e.value for e in at.error] == ["Échec de la suppression."]
    assert _fenetre_ouverte(at), "la fenêtre reste ouverte pour réessayer ou annuler"
    assert not at.error, "le message d'échec n'est pas répété à chaque rerun"
    assert not at.toast
