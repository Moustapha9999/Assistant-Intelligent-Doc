"""Changement du mot de passe par son titulaire (administrateur) : serveur, politique, interface."""

from __future__ import annotations

import inspect
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app import utilisateurs_sqlite as module_users  # noqa: E402
from app.utilisateurs_sqlite import (  # noqa: E402
    MSG_MDP_ACTUEL,
    MSG_MDP_BLOCAGE,
    MSG_SESSION_INVALIDE,
    UtilisateursSQLite,
)
from securite import mots_de_passe, politique, totp  # noqa: E402

ACTUEL = "ancien-mdp-admin"
NOUVEAU = "Velo rouge sous la pluie 7"
EMAIL = "chef.equipe@test.local"


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("STREAMLIT_PASSWORD", raising=False)
    return UtilisateursSQLite(tmp_path / "utilisateurs.db")


def _admin(db, email=EMAIL, mdp=ACTUEL):
    user, _ = db.inscrire_email(email, mdp)
    with sqlite3.connect(db.chemin) as conn:
        conn.execute("UPDATE users SET tier = 'admin' WHERE id = ?", (user["id"],))
    return db.obtenir(user["id"])


def _hash(db, uid):
    with sqlite3.connect(db.chemin) as conn:
        return conn.execute("SELECT password_hash FROM users WHERE id = ?", (uid,)).fetchone()[0]


def _actions(db, action):
    return [e for e in db.lister_audit(500) if e["action"] == action]


# ── Politique ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("mdp", [
    "", "            ", "court1!", "Password2024!", "motdepasse123", "azertyuiop12", "aaaaaaaaaaaa",
    "abcabcabcabc", "123456789012", "qwertyuiop", "chef.equipe2026", "x" * 129,
])
def test_politique_refuse_les_mots_de_passe_faibles(mdp):
    assert mots_de_passe.erreurs(mdp, [EMAIL])


@pytest.mark.parametrize("mdp", [NOUVEAU, "correct-horse-battery", "Tq9#mL2@vX8!pR4z"])
def test_politique_accepte_les_phrases_de_passe(mdp):
    assert mots_de_passe.erreurs(mdp, [EMAIL]) == []


# ── Scénarios serveur ───────────────────────────────────────────────────────


def test_1_7_8_modification_puis_connexion(db):
    admin = _admin(db)
    jeton = db.creer_session(admin["id"])
    ok, msg = db.modifier_mon_mot_de_passe(jeton, ACTUEL, NOUVEAU, NOUVEAU)
    assert ok, msg
    assert db.connecter_email(EMAIL, NOUVEAU)[0]["id"] == admin["id"]
    assert db.connecter_email(EMAIL, ACTUEL)[0] is None
    assert _hash(db, admin["id"]).startswith("scrypt$")


def test_2_mot_de_passe_actuel_incorrect(db):
    admin = _admin(db)
    jeton = db.creer_session(admin["id"])
    avant = _hash(db, admin["id"])
    assert db.modifier_mon_mot_de_passe(jeton, "faux", NOUVEAU, NOUVEAU) == (False, MSG_MDP_ACTUEL)
    assert _hash(db, admin["id"]) == avant
    assert _actions(db, "mot_de_passe_echec")


def test_3_confirmation_differente(db):
    admin = _admin(db)
    jeton = db.creer_session(admin["id"])
    ok, msg = db.modifier_mon_mot_de_passe(jeton, ACTUEL, NOUVEAU, NOUVEAU + "x")
    assert not ok and "confirmation" in msg.lower()
    assert db.connecter_email(EMAIL, ACTUEL)[0] is not None


@pytest.mark.parametrize("faible", ["court", "Password2024!", "chef.equipe-2026", ""])
def test_4_politique_appliquee_par_le_serveur(db, faible):
    admin = _admin(db)
    jeton = db.creer_session(admin["id"])
    ok, msg = db.modifier_mon_mot_de_passe(jeton, ACTUEL, faible, faible)
    assert not ok and msg.startswith("Exigence non respectée")
    assert db.connecter_email(EMAIL, ACTUEL)[0] is not None


def test_reutilisation_du_mot_de_passe_actuel_refusee(tmp_path, monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    db = UtilisateursSQLite(tmp_path / "u.db")
    admin = _admin(db, mdp=NOUVEAU)
    ok, msg = db.modifier_mon_mot_de_passe(db.creer_session(admin["id"]), NOUVEAU, NOUVEAU, NOUVEAU)
    assert not ok and "différent" in msg


@pytest.mark.parametrize("jeton", [None, "", "jeton-inconnu", "x" * 300])
def test_5_refus_sans_authentification(db, jeton):
    admin = _admin(db)
    avant = _hash(db, admin["id"])
    assert db.modifier_mon_mot_de_passe(jeton, ACTUEL, NOUVEAU, NOUVEAU) == (False, MSG_SESSION_INVALIDE)
    assert _hash(db, admin["id"]) == avant
    assert _actions(db, "acces_refuse")


def test_5_refus_session_revoquee_invite_ou_compte_suspendu(db):
    admin = _admin(db)
    autre = _admin(db, "second@test.local")
    revoque = db.creer_session(admin["id"])
    db.revoquer_session(revoque)
    invite = db.creer_session(db.creer_invite()["id"])
    for jeton in (revoque, invite):
        assert db.modifier_mon_mot_de_passe(jeton, ACTUEL, NOUVEAU, NOUVEAU)[1] == MSG_SESSION_INVALIDE
    jeton = db.creer_session(admin["id"])
    assert db.suspendre(admin["id"], True, admin_id=autre["id"])
    assert db.modifier_mon_mot_de_passe(jeton, ACTUEL, NOUVEAU, NOUVEAU)[1] == MSG_SESSION_INVALIDE


def test_6_seul_le_titulaire_de_la_session_est_concerne(db):
    assert "user_id" not in inspect.signature(UtilisateursSQLite.modifier_mon_mot_de_passe).parameters
    a1 = _admin(db)
    a2 = _admin(db, "second@test.local", "mdp-du-second-admin")
    hash_a2 = _hash(db, a2["id"])
    # Avec la session de a1, le mot de passe de a2 ne sert à rien et n'est jamais modifié
    assert db.modifier_mon_mot_de_passe(db.creer_session(a1["id"]), "mdp-du-second-admin", NOUVEAU, NOUVEAU)[1] \
        == MSG_MDP_ACTUEL
    assert db.modifier_mon_mot_de_passe(db.creer_session(a1["id"]), ACTUEL, NOUVEAU, NOUVEAU)[0]
    assert _hash(db, a2["id"]) == hash_a2


def test_9_autres_sessions_revoquees_session_courante_conservee(db):
    admin = _admin(db)
    courante, autre1, autre2 = (db.creer_session(admin["id"]) for _ in range(3))
    ok, msg = db.modifier_mon_mot_de_passe(courante, ACTUEL, NOUVEAU, NOUVEAU)
    assert ok and "2 autre(s) session(s)" in msg
    assert db.valider_session(courante)["id"] == admin["id"]
    assert db.valider_session(autre1) is None and db.valider_session(autre2) is None


def test_10_audit_sans_mot_de_passe_ni_hachage_ni_jeton(db):
    admin = _admin(db)
    jeton = db.creer_session(admin["id"])
    ancien_hash = _hash(db, admin["id"])
    db.modifier_mon_mot_de_passe(jeton, "Tentative-Fausse-42", NOUVEAU, NOUVEAU)
    db.modifier_mon_mot_de_passe(jeton, ACTUEL, NOUVEAU, NOUVEAU)
    with sqlite3.connect(db.chemin) as conn:
        journal = repr(conn.execute("SELECT * FROM admin_audit").fetchall())
    for secret in (ACTUEL, NOUVEAU, "Tentative-Fausse-42", jeton, ancien_hash, _hash(db, admin["id"])):
        assert secret not in journal
    succes = _actions(db, "mot_de_passe_modifie")
    assert len(succes) == 1 and succes[0]["admin_id"] == admin["id"]
    assert succes[0]["categorie"] == "securite" and succes[0]["cree_le"]
    assert db.verifier_journal()["valide"]


def test_limitation_des_tentatives(db):
    admin = _admin(db)
    jeton = db.creer_session(admin["id"])
    for _ in range(politique.valeur("SECU_MAX_ECHECS")):
        db.modifier_mon_mot_de_passe(jeton, "faux", NOUVEAU, NOUVEAU)
    assert db.modifier_mon_mot_de_passe(jeton, ACTUEL, NOUVEAU, NOUVEAU) == (False, MSG_MDP_BLOCAGE)
    assert _actions(db, "auth_verrouillage")[0]["gravite"] == "elevee"


def test_code_mfa_exige_si_actif(db):
    admin = _admin(db)
    secret = db.preparer_totp(admin["id"])
    assert db.activer_totp(admin["id"], totp.code_pour_pas(secret, totp.pas_courant()))
    jeton = db.creer_session(admin["id"])
    assert not db.modifier_mon_mot_de_passe(jeton, ACTUEL, NOUVEAU, NOUVEAU, "000000")[0]
    code = totp.code_pour_pas(secret, totp.pas_courant() + 1)
    assert db.modifier_mon_mot_de_passe(jeton, ACTUEL, NOUVEAU, NOUVEAU, code)[0]


def test_compte_oauth_sans_mot_de_passe(db):
    user = db.upsert_github("42", "octo", email=None)
    jeton = db.creer_session(user["id"])
    ok, msg = db.modifier_mon_mot_de_passe(jeton, "x", NOUVEAU, NOUVEAU)
    assert not ok and "fournisseur externe" in msg


def test_soumissions_multiples_une_seule_modification(db):
    admin = _admin(db)
    jeton = db.creer_session(admin["id"])
    resultats = [db.modifier_mon_mot_de_passe(jeton, ACTUEL, NOUVEAU, NOUVEAU)[0] for _ in range(3)]
    assert resultats == [True, False, False]
    assert len(_actions(db, "mot_de_passe_modifie")) == 1
    assert db.connecter_email(EMAIL, NOUVEAU)[0] is not None


def test_panne_de_base_rien_n_est_modifie(db, monkeypatch):
    admin = _admin(db)
    jeton = db.creer_session(admin["id"])
    avant = _hash(db, admin["id"])

    def panne(*_a, **_k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(module_users, "ecriture", panne)
    with pytest.raises(sqlite3.OperationalError):
        db.modifier_mon_mot_de_passe(jeton, ACTUEL, NOUVEAU, NOUVEAU)
    monkeypatch.undo()
    assert _hash(db, admin["id"]) == avant and db.valider_session(jeton)


# ── Interface (page Admin réelle, exécutée par Streamlit) ───────────────────


@pytest.fixture
def page(tmp_path, monkeypatch, db):
    pytest.importorskip("streamlit.testing.v1")
    import config
    from app import historique_sqlite, identite

    monkeypatch.setattr(config, "DB_DIR", tmp_path)
    monkeypatch.setattr(config, "HISTORIQUE_DB", tmp_path / "historique.db")
    monkeypatch.setattr(historique_sqlite.config, "HISTORIQUE_DB", tmp_path / "historique.db")
    monkeypatch.setattr(identite, "users_db", lambda: db)
    admin = _admin(db)
    return db, admin, db.creer_session(admin["id"])


def _ouvrir(jeton):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "src" / "app" / "admin_page.py"), default_timeout=60)
    at.session_state["_jeton_session"] = jeton
    at.session_state["_jeton_provisoire"] = False
    at.run()
    at.button(key="admin_mdp").click().run()
    assert not at.exception, at.exception
    return at


def _saisir(at, actuel, nouveau, confirmation):
    at.text_input(key="secu_mdp_actuel").input(actuel)
    at.text_input(key="secu_mdp_nouveau").input(nouveau)
    at.text_input(key="secu_mdp_confirmation").input(confirmation)
    return at.run()


def test_interface_modification_reussie(page):
    db, admin, jeton = page
    at = _ouvrir(jeton)
    from streamlit.proto.TextInput_pb2 import TextInput

    for cle in ("secu_mdp_actuel", "secu_mdp_nouveau", "secu_mdp_confirmation"):
        assert at.text_input(key=cle).proto.type == TextInput.PASSWORD  # masqué, œil pour afficher
    assert at.button(key="secu_mdp_valider").disabled  # champs vides
    _saisir(at, ACTUEL, NOUVEAU, NOUVEAU)
    assert not at.button(key="secu_mdp_valider").disabled
    at.button(key="secu_mdp_valider").click().run()
    assert not at.exception, at.exception
    assert db.connecter_email(EMAIL, NOUVEAU)[0] is not None
    assert "secu_mdp_ouvert" not in at.session_state  # boîte refermée
    assert "secu_mdp_nouveau" not in at.session_state  # champs effacés


def test_interface_erreur_affichee_et_bouton_reactive(page):
    db, admin, jeton = page
    at = _saisir(_ouvrir(jeton), "faux", NOUVEAU, NOUVEAU)
    at.button(key="secu_mdp_valider").click().run()
    assert not at.exception, at.exception
    assert any(MSG_MDP_ACTUEL in str(e.value) for e in at.error)
    assert at.session_state["secu_mdp_en_cours"] is False
    assert db.connecter_email(EMAIL, ACTUEL)[0] is not None


def test_interface_panne_serveur(page, monkeypatch):
    db, admin, jeton = page

    def panne(*_a, **_k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(db, "modifier_mon_mot_de_passe", panne)
    at = _saisir(_ouvrir(jeton), ACTUEL, NOUVEAU, NOUVEAU)
    at.button(key="secu_mdp_valider").click().run()
    assert not at.exception, at.exception
    assert any("n'a pas été modifié" in str(e.value) for e in at.error)
    assert "database is locked" not in " ".join(str(e.value) for e in at.error)
    assert at.session_state["secu_mdp_en_cours"] is False


def test_interface_annuler(page):
    db, admin, jeton = page
    at = _saisir(_ouvrir(jeton), ACTUEL, NOUVEAU, NOUVEAU)
    at.button(key="secu_mdp_annuler").click().run()
    assert "secu_mdp_ouvert" not in at.session_state
    assert db.connecter_email(EMAIL, ACTUEL)[0] is not None
