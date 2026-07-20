import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from app.historique_sqlite import HistoriqueSQLite


def test_conversation_messages_et_feedback(tmp_path):
    historique = HistoriqueSQLite(tmp_path / "historique.db")
    conversation_id = historique.creer_conversation("Test")
    historique.sauvegarder_conversation(
        conversation_id, "Test",
        [{"role": "user", "content": "Bonjour"}, {"role": "assistant", "content": "Salut"}],
    )
    assert historique.charger_messages(conversation_id) == [
        {"role": "user", "content": "Bonjour"},
        {"role": "assistant", "content": "Salut"},
    ]
    historique.enregistrer_feedback(conversation_id, 1, 5, "Très utile")
    with historique._connect() as conn:
        feedback = conn.execute("SELECT note, commentaire FROM feedback").fetchone()
    assert feedback["note"] == 5
    assert feedback["commentaire"] == "Très utile"


def test_figer_renommer_supprimer(tmp_path):
    historique = HistoriqueSQLite(tmp_path / "historique2.db")
    cid = historique.creer_conversation("Ancien titre")
    historique.sauvegarder_conversation(
        cid, "Ancien titre",
        [{"role": "user", "content": "Q1"}],
    )

    assert historique.renommer_conversation(cid, "Nouveau titre") is True
    assert historique.obtenir_conversation(cid)["titre"] == "Nouveau titre"

    assert historique.figer_conversation(cid, True) is True
    assert historique.est_figee(cid) is True
    # Figée : pas de renommage ni suppression
    assert historique.renommer_conversation(cid, "Autre") is False
    assert historique.supprimer_conversation(cid) is False
    assert historique.obtenir_conversation(cid) is not None

    # Titre conservé malgré une sauvegarde
    historique.sauvegarder_conversation(cid, "Titre écrasé", [{"role": "user", "content": "Q2"}])
    assert historique.obtenir_conversation(cid)["titre"] == "Nouveau titre"

    assert historique.figer_conversation(cid, False) is True
    assert historique.supprimer_conversation(cid) is True
    assert historique.obtenir_conversation(cid) is None


def test_lister_figees_en_tete(tmp_path):
    historique = HistoriqueSQLite(tmp_path / "historique3.db")
    a = historique.creer_conversation("A")
    b = historique.creer_conversation("B")
    historique.figer_conversation(b, True)
    liste = historique.lister_conversations()
    assert liste[0]["id"] == b
    assert liste[0]["figee"] is True
    assert {c["id"] for c in liste} == {a, b}
