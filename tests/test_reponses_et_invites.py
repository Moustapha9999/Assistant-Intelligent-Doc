"""Réponses de l'IA (nettoyage, Markdown, streaming) et parcours invité (quota, fenêtre de connexion)."""

from __future__ import annotations

import sqlite3
import sys
import threading
from datetime import timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app import utilisateurs_sqlite as module_users  # noqa: E402
from app.utilisateurs_sqlite import MSG_QUOTA_INVITE, UtilisateursSQLite  # noqa: E402
from core.nettoyage_reponse import REGLE_FORMAT, nettoyer_reponse  # noqa: E402

# ── 1. Nettoyage des réponses ───────────────────────────────────────────────

# Extraits réels relevés dans des conversations enregistrées
CELLULE_LISTE = (
    "| **2. Activités avec l’équipe Monitoring ATM/GAB** | <ul><li>**2.1 Gestion** : suivi des automates</li>"
    "<li>**2.2 Supervision** : alertes</li></ul> |"
)
CELLULE_BR = (
    "| **6. Synthèse chronologique** | Récapitulatif mensuel : <br>• Juin‑sept. 2026 : activités Monitoring. "
    "<br>• Oct. 2026 : IT. |"
)
CITATIONS = "statistiques calculées : somme = 13400)【ventes.csv – statistiques】. Total【3†L10-L20】 confirmé."


def test_html_dans_les_cellules_de_tableau():
    for ligne in (CELLULE_LISTE, CELLULE_BR):
        propre = nettoyer_reponse(ligne)
        assert "<" not in propre and ">" not in propre
        assert "\n" not in propre and propre.count("|") == ligne.count("|")
    assert "• **2.1 Gestion** : suivi des automates • **2.2 Supervision** : alertes" in nettoyer_reponse(CELLULE_LISTE)
    assert "Récapitulatif mensuel : • Juin‑sept. 2026" in nettoyer_reponse(CELLULE_BR)


def test_html_dans_le_texte_converti_en_markdown():
    propre = nettoyer_reponse("Ligne 1<br>Ligne 2<p>Para</p><b>gras</b> et <em>it</em> <code>x = 1</code>"
                              "<ul><li>un</li><li>deux</li></ul>")
    assert propre == "Ligne 1  \nLigne 2\n\nPara\n\n**gras** et *it* `x = 1`\n- un\n- deux"


def test_marqueurs_de_citation():
    propre = nettoyer_reponse(CITATIONS)
    assert "【" not in propre and "】" not in propre and "†" not in propre
    assert "13400) (ventes.csv – statistiques)." in propre  # la source reste citée
    assert "Total confirmé." in propre


def test_reflexion_jetons_et_marqueurs_internes():
    brut = ("<think>Je dois réfléchir…</think>Réponse<|end|> finale.\n"
            '<<<DONNEES_NON_FIABLES source="corpus">>>\nExtrait cité\n<<<FIN_DONNEES_NON_FIABLES>>>\nFin')
    assert nettoyer_reponse(brut) == "Réponse finale.\nExtrait cité\nFin"
    assert nettoyer_reponse("Début</think> suite") == "Début suite"  # balise orpheline hors code


MARKDOWN_PROPRE = """## Titre

Un paragraphe avec **gras**, *italique* et un [lien](https://fastapi.tiangolo.com).

- élément 1
- élément 2
  1. sous-élément

| Colonne | Valeur |
|:--------|-------:|
| a | 1 |

> Citation

Comparaison : a < b et b > c ; type générique List<T> ; flèche -> ok."""


def test_markdown_valide_inchange():
    assert nettoyer_reponse(MARKDOWN_PROPRE) == MARKDOWN_PROPRE


def test_code_jamais_modifie():
    code = ('```html\n<ul>\n  <li>un</li><br>\n</ul>\n<script>alert("x")</script>\n```\n'
            "Le code `<br/>` et ``a <b>c</b>`` restent tels quels.\n"
            "~~~python\nprint('【pas une citation】<think>')\n~~~")
    assert nettoyer_reponse(code) == code


def test_html_inconnu_conserve_et_jamais_rendu():
    # Pas de suppression aveugle : affiché en texte par st.markdown (unsafe_allow_html désactivé)
    texte = "Exemple : <script>alert(1)</script> et <img src=x onerror=alert(1)>"
    assert nettoyer_reponse(texte) == texte
    source = (ROOT / "src" / "app" / "accueil.py").read_text(encoding="utf-8")
    assert 'st.markdown(nettoyer_reponse(msg["content"]))' in source


def test_idempotent():
    for texte in (CELLULE_LISTE, CELLULE_BR, CITATIONS, MARKDOWN_PROPRE):
        une = nettoyer_reponse(texte)
        assert nettoyer_reponse(une) == une


def test_flux_partiel_masque_les_elements_incomplets():
    assert nettoyer_reponse("Somme 13400【ventes.c", partiel=True) == "Somme 13400"
    assert nettoyer_reponse("Ligne<b", partiel=True) == "Ligne"
    assert nettoyer_reponse("<think>en cours de réfl", partiel=True) == ""
    assert nettoyer_reponse("Texte <<<FIN_DONN", partiel=True) == "Texte"
    assert nettoyer_reponse("```python\nx = a <", partiel=True) == "```python\nx = a <"  # code intact


def test_regle_de_format_dans_le_prompt():
    from core.constructeur_prompt import ConstructeurPrompt
    from core.schemas import AnalyseQuestion, PlanReponse

    systeme, _ = ConstructeurPrompt().construire(
        question="x", analyse=AnalyseQuestion(mode="conversation"), plan=PlanReponse(sections=[]),
        documents=[], ressources_web=[],
    )
    assert REGLE_FORMAT in systeme


def test_affichage_en_streaming():
    pytest.importorskip("streamlit.testing.v1")
    from streamlit.testing.v1 import AppTest

    def script():
        import streamlit as st

        from app.ui_composants import afficher_flux

        morceaux = ["## Résultat\n\n| A | B |\n|---|---|\n| x<b", "r>y | 1 |\n\nSource【vent",
                    "es.csv】.\n\n```python\nprint('<br>')\n```"]
        st.session_state["final"] = afficher_flux(iter(morceaux), intervalle_s=0)

    at = AppTest.from_function(script).run()
    assert not at.exception
    final = at.session_state["final"]
    assert "| x ; y | 1 |" in final and "Source (ventes.csv)." in final
    assert "print('<br>')" in final
    assert [m.value for m in at.markdown][-1] == final


def test_export_et_rechargement_nettoyes(tmp_path):
    from app import export_conversation

    messages = [{"role": "user", "content": "Bilan ?"},
                {"role": "assistant", "content": CELLULE_BR + "\n" + CITATIONS, "docs": []}]
    md = export_conversation.export_markdown(messages)
    assert "<br>" not in md and "【" not in md and "Récapitulatif mensuel" in md


# ── 2. Quota invité (serveur) ───────────────────────────────────────────────


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("QUOTA_GUEST_REQ", "5")
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("STREAMLIT_PASSWORD", raising=False)
    return UtilisateursSQLite(tmp_path / "utilisateurs.db")


def test_cinq_requetes_puis_refus(db):
    invite = db.creer_invite()
    assert [db.reserver_requete(invite)[0] for _ in range(5)] == [True] * 5
    ok, msg = db.reserver_requete(invite)
    assert not ok and msg == MSG_QUOTA_INVITE.format(n=5)
    assert db.compter_requetes_jour(invite["id"]) == 5  # la requête refusée n'est pas décomptée
    assert db.verifier_quota(invite)[0] is False
    assert db.compter_requetes_jour(invite["id"]) == 5  # la consultation ne décompte rien


def test_actualisation_ne_reinitialise_pas_le_quota(db):
    invite = db.creer_invite()
    jeton = db.creer_session(invite["id"])
    for _ in range(5):
        db.reserver_requete(invite)
    rechargee = UtilisateursSQLite(db.chemin).valider_session(jeton)  # même cookie, nouveau processus
    assert rechargee["id"] == invite["id"]
    assert not UtilisateursSQLite(db.chemin).reserver_requete(rechargee)[0]


def test_requetes_simultanees_sans_depassement(db):
    invite = db.creer_invite()
    for _ in range(3):
        db.reserver_requete(invite)
    resultats, depart = [], threading.Barrier(12)

    def tenter():
        depart.wait()
        resultats.append(UtilisateursSQLite(db.chemin).reserver_requete(invite)[0])

    fils = [threading.Thread(target=tenter) for _ in range(12)]
    for f in fils:
        f.start()
    for f in fils:
        f.join()
    assert resultats.count(True) == 2
    assert db.compter_requetes_jour(invite["id"]) == 5


def test_renouvellement_quotidien(db):
    invite = db.creer_invite()
    for _ in range(5):
        db.reserver_requete(invite)
    hier = (module_users._maintenant() - timedelta(days=1)).isoformat()
    with sqlite3.connect(db.chemin) as conn:
        conn.execute("UPDATE usage_events SET cree_le = ?", (hier,))
    assert [db.reserver_requete(invite)[0] for _ in range(6)] == [True] * 5 + [False]


def test_api_refuse_sans_cle(monkeypatch):
    pytest.importorskip("fastapi.testclient")
    from fastapi.testclient import TestClient

    import api.main_api as api

    appels = []
    monkeypatch.setattr(api, "orchestrateur", lambda: appels.append(1))
    monkeypatch.setattr("api.auth.charger_api_keys", lambda: {"cle-valide": "alice"})
    client = TestClient(api.app)
    assert client.post("/ask", json={"question": "x"}).status_code == 401
    assert client.post("/ask", json={"question": "x"}, headers={"X-API-Key": "invite"}).status_code == 401
    assert appels == []


# ── 3. Fenêtre de connexion de l'invité (page réelle des composants) ───────


SCRIPT_INVITE = '''
import streamlit as st
from app import auth_basique as a
from app import identite

identite.identite_courante()
st.session_state.setdefault("messages", [])
if st.button("Envoyer", key="envoyer"):
    ok, msg = a.consommer_requete({})
    st.session_state["messages"].append(("ok" if ok else "refus", msg))
if st.button("Se connecter", key="sb_login"):
    a.ouvrir_connexion()
    st.rerun()
if st.button("Fermer", key="fermer"):
    a.fermer_connexion()  # même fonction que l'on_dismiss de la boîte de dialogue
a.afficher_dialog_auth_si_besoin()
'''


@pytest.fixture
def appli(db, monkeypatch):
    pytest.importorskip("streamlit.testing.v1")
    from app import auth_basique, identite

    for module, nom in ((identite, "users_db"), (auth_basique, "users_db"), (auth_basique, "_users_db")):
        monkeypatch.setattr(module, nom, lambda: db)
    invite = db.creer_invite()
    return db, db.creer_session(invite["id"])


def _ouvrir(jeton):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_string(SCRIPT_INVITE, default_timeout=30)
    at.session_state["_jeton_session"] = jeton
    at.session_state["_jeton_provisoire"] = False
    return at.run()


def _formulaire_visible(at) -> bool:
    return any(t.key == "modal_email" for t in at.text_input)


def test_parcours_invite_complet(appli):
    db, jeton = appli
    at = _ouvrir(jeton)
    assert not at.exception, at.exception
    assert not _formulaire_visible(at)  # ouverture de l'application

    for i in range(5):  # requêtes 1 à 5
        at.button(key="envoyer").click().run()
        assert at.session_state["messages"][-1][0] == "ok", i
        assert not _formulaire_visible(at)

    at.button(key="envoyer").click().run()  # 6e requête
    assert at.session_state["messages"][-1] == ("refus", MSG_QUOTA_INVITE.format(n=5))
    assert _formulaire_visible(at)
    assert any("limite de 5 requêtes gratuites" in str(c.value) for c in at.caption)

    at.button(key="fermer").click().run()  # fermeture
    assert not _formulaire_visible(at)
    assert len(at.session_state["messages"]) == 6  # conversation conservée
    at.run()
    assert not _formulaire_visible(at)  # pas de réouverture spontanée

    at.button(key="sb_login").click().run()  # clic volontaire après la limite
    assert _formulaire_visible(at)

    rechargement = _ouvrir(jeton)  # actualisation de la page
    assert not _formulaire_visible(rechargement)
    rechargement.button(key="envoyer").click().run()
    assert rechargement.session_state["messages"][-1][0] == "refus"
    assert db.compter_requetes_jour(db.valider_session(jeton)["id"]) == 5


def test_se_connecter_avant_la_limite(appli):
    _, jeton = appli
    at = _ouvrir(jeton)
    at.button(key="envoyer").click().run()
    at.button(key="sb_login").click().run()
    assert _formulaire_visible(at)
    assert not any("limite" in str(c.value) for c in at.caption), (
        at.session_state["messages"], [c.value for c in at.caption])  # pas de message de quota
    at.button(key="fermer").click().run()
    at.button(key="envoyer").click().run()  # requête suivante : pas de réouverture
    assert at.session_state["messages"][-1][0] == "ok" and not _formulaire_visible(at)
