"""Isolation des utilisateurs : identité, sessions, OAuth, historique, favoris, quotas, export."""

import sqlite3
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.export_conversation import exporter_conversation
from app.favoris_sqlite import FavorisSQLite
from app.historique_sqlite import HistoriqueSQLite
from app.identite import Identite, fermer_session, ouvrir_session_compte, resoudre_identite, script_cookie
from app.utilisateurs_sqlite import UtilisateursSQLite, empreinte_jeton
from core.memoire_longue import MemoireLongue
from securite.acces import AccesRefuse, VueProprietaire

MSGS = [{"role": "user", "content": "Question A"}, {"role": "assistant", "content": "Réponse A"}]


@pytest.fixture
def bases(tmp_path, monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    return (
        UtilisateursSQLite(tmp_path / "utilisateurs.db"),
        HistoriqueSQLite(tmp_path / "historique.db"),
        FavorisSQLite(tmp_path / "favoris.db"),
    )


def _navigateur(users, cookie=None):
    """Simule un navigateur : (utilisateur, jeton du cookie)."""
    user, jeton, _ = resoudre_identite(users, None, cookie)
    return user, jeton


# ── Test 1 : deux invités sur deux machines ─────────────────────────────────


def test_deux_invites_ne_voient_pas_les_conversations_l_un_de_l_autre(bases):
    users, histo, _ = bases
    a, _ = _navigateur(users)
    b, _ = _navigateur(users)
    assert a["id"] != b["id"]

    cid = histo.creer_conversation("Conversation de A", owner_id=a["id"])
    histo.sauvegarder_conversation(cid, "Conversation de A", MSGS, owner_id=a["id"])

    assert [c["id"] for c in histo.lister_conversations(owner_id=a["id"])] == [cid]
    assert histo.lister_conversations(owner_id=b["id"]) == []
    with pytest.raises(AccesRefuse):
        histo.charger_messages(cid, owner_id=b["id"])
    assert histo.obtenir_conversation(cid, owner_id=b["id"]) is None


def test_aucun_proprietaire_generique(bases):
    users, histo, fav = bases
    for vide in ("", None):
        with pytest.raises(AccesRefuse):
            histo.lister_conversations(owner_id=vide)
        with pytest.raises(AccesRefuse):
            fav.lister_collections(owner_id=vide)
    with pytest.raises(AccesRefuse):
        VueProprietaire(histo, "")


# ── Test 2 : persistance de l'invité ────────────────────────────────────────


def test_invite_retrouve_son_historique_avec_son_cookie(bases):
    users, histo, _ = bases
    a, cookie = _navigateur(users)
    cid = histo.creer_conversation("A", owner_id=a["id"])

    # Rechargement de la page / nouvelle session Streamlit : seul le cookie subsiste
    meme, jeton, nouvelle = resoudre_identite(users, None, cookie)
    assert not nouvelle and meme["id"] == a["id"] and jeton == cookie
    assert [c["id"] for c in histo.lister_conversations(owner_id=meme["id"])] == [cid]


def test_cookie_absent_invalide_ou_expire_donne_un_nouvel_invite(bases):
    users, _, _ = bases
    a, cookie = _navigateur(users)
    for faux in ("", "inexistant", "x" * 300):
        u, _, nouvelle = resoudre_identite(users, None, faux)
        assert nouvelle and u["id"] != a["id"]

    with sqlite3.connect(users.chemin) as conn:
        passe = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        conn.execute("UPDATE sessions SET expire_le = ? WHERE jeton_hash = ?", (passe, empreinte_jeton(cookie)))
    u, _, nouvelle = resoudre_identite(users, None, cookie)
    assert nouvelle and u["id"] != a["id"]


def test_seule_l_empreinte_du_jeton_est_stockee(bases):
    users, _, _ = bases
    _, jeton = _navigateur(users)
    with sqlite3.connect(users.chemin) as conn:
        stockes = [r[0] for r in conn.execute("SELECT jeton_hash FROM sessions")]
    assert jeton not in stockes and empreinte_jeton(jeton) in stockes
    assert len(jeton) >= 40


# ── Tests 3 et 4 : Google et GitHub ─────────────────────────────────────────


def test_google_meme_compte_quel_que_soit_l_appareil(bases):
    users, histo, _ = bases
    c1 = users.upsert_google("g-123", email="alice@gmail.com", display_name="Alice")
    cid = histo.creer_conversation("Google", owner_id=c1["id"])
    c2 = users.upsert_google("g-123", email="alice@gmail.com")
    assert c1["id"] == c2["id"]
    assert [c["id"] for c in histo.lister_conversations(owner_id=c2["id"])] == [cid]
    autre = users.upsert_google("g-999", email="bob@gmail.com")
    assert histo.lister_conversations(owner_id=autre["id"]) == []


def test_github_identifiant_stable_et_pas_de_fusion_par_email(bases):
    users, _, _ = bases
    g1 = users.upsert_github("42", "alice-gh", email="alice@example.com")
    g2 = users.upsert_github("42", "alice-renommee", email="alice@example.com")
    assert g1["id"] == g2["id"] and g2["github_login"] == "alice-renommee"

    # Même e-mail, autre fournisseur : comptes distincts, e-mail non dupliqué
    goo = users.upsert_google("g-1", email="alice@example.com")
    assert goo["id"] != g1["id"] and goo["email"] is None


def test_preprise_de_compte_par_email_impossible(bases):
    users, _, _ = bases
    attaquant, _ = users.inscrire_email("victime@example.com", "motdepasse1")
    victime = users.upsert_github("777", "victime", email="victime@example.com")
    assert victime["id"] != attaquant["id"]
    assert victime["tier"] == "github"


def test_mot_de_passe_scrypt_et_migration_ancien_hash(bases):
    users, _, _ = bases
    u, _ = users.inscrire_email("c@example.com", "secret123")
    with sqlite3.connect(users.chemin) as conn:
        stocke = conn.execute("SELECT password_hash FROM users WHERE id = ?", (u["id"],)).fetchone()[0]
    assert stocke.startswith("scrypt$")
    assert users.connecter_email("c@example.com", "mauvais")[0] is None
    assert users.connecter_email("c@example.com", "secret123")[0]["id"] == u["id"]


# ── États OAuth ─────────────────────────────────────────────────────────────


def test_etat_oauth_usage_unique_lie_a_la_session_et_au_fournisseur(bases):
    users, _, _ = bases
    _, jeton = _navigateur(users)
    _, jeton_autre = _navigateur(users)

    users.enregistrer_etat_oauth("gh.abc", "github", jeton)
    assert users.consommer_etat_oauth("gh.abc", "github", jeton_autre) is False  # autre navigateur
    users.enregistrer_etat_oauth("gh.abc", "github", jeton)
    assert users.consommer_etat_oauth("gh.abc", "google", jeton) is False  # autre fournisseur
    users.enregistrer_etat_oauth("gh.abc", "github", jeton)
    assert users.consommer_etat_oauth("gh.abc", "github", jeton) is True
    assert users.consommer_etat_oauth("gh.abc", "github", jeton) is False  # rejoué
    assert users.consommer_etat_oauth("inconnu", "github", jeton) is False
    assert users.consommer_etat_oauth("", "github", jeton) is False


def test_etat_oauth_expire(bases):
    users, _, _ = bases
    _, jeton = _navigateur(users)
    users.enregistrer_etat_oauth("ggl.x", "google", jeton)
    with sqlite3.connect(users.chemin) as conn:
        conn.execute("UPDATE oauth_etats SET expire_le = ?", ((datetime.now(timezone.utc) - timedelta(1)).isoformat(),))
    assert users.consommer_etat_oauth("ggl.x", "google", jeton) is False


# ── Test 5 : changement de mode ─────────────────────────────────────────────


def test_connexion_puis_deconnexion_sans_melange(bases):
    users, histo, _ = bases
    invite, jeton_invite = _navigateur(users)
    cid_invite = histo.creer_conversation("invité", owner_id=invite["id"])

    compte = users.upsert_google("g-5", email="e@gmail.com")
    jeton_compte = ouvrir_session_compte(users, compte, jeton_invite)
    assert jeton_compte != jeton_invite
    assert users.valider_session(jeton_invite) is None  # rotation : ancien jeton révoqué
    assert users.valider_session(jeton_compte)["id"] == compte["id"]
    cid_compte = histo.creer_conversation("compte", owner_id=compte["id"])
    assert [c["id"] for c in histo.lister_conversations(owner_id=compte["id"])] == [cid_compte]

    nouvel_invite, jeton_nouveau = fermer_session(users, jeton_compte)
    assert users.valider_session(jeton_compte) is None
    assert nouvel_invite["id"] not in {invite["id"], compte["id"]}
    assert histo.lister_conversations(owner_id=nouvel_invite["id"]) == []
    # L'ancien invité n'est pas fusionné dans le compte
    assert [c["id"] for c in histo.lister_conversations(owner_id=invite["id"])] == [cid_invite]
    assert users.valider_session(jeton_nouveau)["id"] == nouvel_invite["id"]


def test_compte_suspendu_perd_sa_session(bases):
    users, _, _ = bases
    compte = users.upsert_github("9", "x")
    jeton = users.creer_session(compte["id"])
    users.suspendre(compte["id"], True)
    assert users.valider_session(jeton) is None


# ── Tests 6 et 7 : accès direct, modification, suppression ──────────────────


def test_acces_direct_modification_et_suppression_refuses(bases):
    users, histo, _ = bases
    a, _ = _navigateur(users)
    b, _ = _navigateur(users)
    cid = histo.creer_conversation("A", owner_id=a["id"])
    histo.sauvegarder_conversation(cid, "A", MSGS, owner_id=a["id"])

    with pytest.raises(AccesRefuse):
        histo.sauvegarder_conversation(cid, "piraté", [{"role": "user", "content": "x"}], owner_id=b["id"])
    assert histo.renommer_conversation(cid, "piraté", owner_id=b["id"]) is False
    assert histo.figer_conversation(cid, True, owner_id=b["id"]) is False
    assert histo.supprimer_conversation(cid, owner_id=b["id"]) is False
    with pytest.raises(AccesRefuse):
        histo.enregistrer_feedback(cid, 1, 1, owner_id=b["id"])

    assert histo.obtenir_conversation(cid, owner_id=a["id"])["titre"] == "A"
    assert histo.charger_messages(cid, owner_id=a["id"]) == MSGS


def test_vue_proprietaire_refuse_un_owner_fourni_par_l_appelant(bases):
    _, histo, _ = bases
    vue = VueProprietaire(histo, "u-a")
    with pytest.raises(TypeError):
        vue.lister_conversations(owner_id="u-b")
    with pytest.raises(AttributeError):
        vue._connect()


def test_donnees_sans_proprietaire_en_quarantaine(bases):
    users, histo, _ = bases
    with sqlite3.connect(histo.chemin) as conn:
        conn.execute(
            "INSERT INTO conversations (id, owner_id, titre, cree_le, maj_le) VALUES ('legacy', NULL, 'Ancienne', 'x', 'x')"
        )
    a, _ = _navigateur(users)
    assert histo.lister_conversations(owner_id=a["id"]) == []
    with pytest.raises(AccesRefuse):
        histo.sauvegarder_conversation("legacy", "vol", MSGS, owner_id=a["id"])
    assert histo.compter_quarantaine() == 1


# ── Test 8 : export ─────────────────────────────────────────────────────────


def test_export_reserve_au_proprietaire(bases):
    users, histo, _ = bases
    a, _ = _navigateur(users)
    b, _ = _navigateur(users)
    cid = histo.creer_conversation("Export A", owner_id=a["id"])
    histo.sauvegarder_conversation(cid, "Export A", MSGS, owner_id=a["id"])

    md = exporter_conversation(histo, cid, owner_id=a["id"])
    assert "Question A" in md
    with pytest.raises(AccesRefuse):
        exporter_conversation(histo, cid, owner_id=b["id"])
    with pytest.raises(AccesRefuse):
        exporter_conversation(histo, "inexistante", owner_id=a["id"])


# ── Test 9 : favoris, préférences et quotas ─────────────────────────────────


def test_favoris_isoles(bases):
    users, _, fav = bases
    a, _ = _navigateur(users)
    b, _ = _navigateur(users)
    col_a = fav.creer_collection("A", owner_id=a["id"])
    fid = fav.ajouter_favori({"nom_complet": "o/r", "source_file": "f.md"}, col_a, owner_id=a["id"])

    assert fav.lister_favoris(owner_id=b["id"]) == []
    assert col_a not in {c["id"] for c in fav.lister_collections(owner_id=b["id"])}
    assert fav.est_deja_favori("o/r", "f.md", owner_id=b["id"]) is False
    assert fav.supprimer_favori(fid, owner_id=b["id"]) is False
    assert fav.supprimer_collection(col_a, owner_id=b["id"]) is False
    with pytest.raises(AccesRefuse):
        fav.ajouter_favori({"nom_complet": "x"}, col_a, owner_id=b["id"])
    assert len(fav.lister_favoris(owner_id=a["id"])) == 1


def test_quotas_par_identite(bases):
    users, _, _ = bases
    a, _ = _navigateur(users)
    b, _ = _navigateur(users)
    for _ in range(3):
        users.enregistrer_usage(a["id"], "ask", {})
    assert users.compter_requetes_jour(a["id"]) == 3
    assert users.compter_requetes_jour(b["id"]) == 0


def test_memoire_long_terme_isolee(tmp_path):
    m = MemoireLongue(tmp_path / "prefs.db")
    m.definir("langage_prefere", "python", user_id="u-a")
    assert m.charger("u-b") == {}
    assert m.charger(None) == {}
    assert m.charger("u-a")["langage_prefere"] == "python"


# ── Test 10 : sessions simultanées ──────────────────────────────────────────


def test_sessions_simultanees_sans_fuite(bases):
    users, histo, _ = bases
    erreurs = []
    resultats = {}

    def session(n):
        try:
            u, _ = _navigateur(users)
            cids = set()
            for i in range(5):
                cid = histo.creer_conversation(f"{n}-{i}", owner_id=u["id"])
                histo.sauvegarder_conversation(
                    cid, f"{n}-{i}", [{"role": "user", "content": f"secret-{n}-{i}"}], owner_id=u["id"]
                )
                cids.add(cid)
            resultats[n] = (u["id"], cids)
        except Exception as exc:  # pragma: no cover - remonté par l'assertion
            erreurs.append(exc)

    threads = [threading.Thread(target=session, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert erreurs == []
    assert len({uid for uid, _ in resultats.values()}) == 8
    for n, (uid, cids) in resultats.items():
        vues = histo.lister_conversations(owner_id=uid)
        assert {c["id"] for c in vues} == cids
        for c in vues:
            contenu = histo.charger_messages(c["id"], owner_id=uid)[0]["content"]
            assert contenu.startswith(f"secret-{n}-")


# ── API FastAPI : le propriétaire vient de la clé, jamais du client ─────────


def test_api_feedback_isolation(tmp_path, monkeypatch):
    pytest.importorskip("fastapi.testclient")
    from fastapi.testclient import TestClient

    import api.main_api as api

    histo = HistoriqueSQLite(tmp_path / "api.db")
    monkeypatch.setattr(api, "historique", lambda: histo)
    cid = histo.creer_conversation("alice", owner_id="api:alice")
    client = TestClient(api.app)

    monkeypatch.setattr("api.auth.charger_api_keys", lambda: {"cle-a": "alice", "cle-b": "bob"})
    corps = {"conversation_id": cid, "message_idx": 0, "note": 1, "owner_id": "api:alice"}
    assert client.post("/feedback", json=corps, headers={"X-API-Key": "cle-b"}).status_code == 404
    assert client.post("/feedback", json=corps, headers={"X-API-Key": "cle-a"}).status_code == 200
    assert client.post("/feedback", json=corps).status_code == 401

    # Mode anonyme (aucune clé configurée) : aucune conversation accessible
    monkeypatch.setattr("api.auth.charger_api_keys", lambda: {})
    assert client.post("/feedback", json=corps).status_code == 404
    assert client.post("/feedback", json={"message_idx": 0, "note": 1}).status_code == 200
    assert api.proprietaire_api("anonymous") is None


# ── Cookie navigateur ───────────────────────────────────────────────────────


def test_script_cookie_attributs_et_echappement():
    js = script_cookie("ancien", 'nouveau"</script>', 3600)
    assert "SameSite=Lax" in js and "Max-Age=" in js and "Secure" in js and "Path=/" in js
    assert js.count("</script>") == 1  # la valeur ne peut pas fermer la balise


def test_identite_statut():
    assert Identite("u", "guest", "").est_invitee
    assert Identite("u", "github", "x").est_authentifiee
    assert Identite("u", "admin", "x").est_admin
