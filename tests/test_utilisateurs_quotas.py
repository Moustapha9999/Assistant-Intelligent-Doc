import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.quotas import quota_pour
from app.utilisateurs_sqlite import UtilisateursSQLite


def test_quotas_tiers():
    assert quota_pour("guest").requetes_par_jour > 0
    assert quota_pour("email").requetes_par_jour > quota_pour("guest").requetes_par_jour
    assert quota_pour("github").requetes_par_jour > quota_pour("email").requetes_par_jour
    assert quota_pour("admin").requetes_par_jour == -1


def test_inscription_et_quota(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "secretadmin")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@test.local")
    db = UtilisateursSQLite(tmp_path / "users.db")
    user, msg = db.inscrire_email("alice@test.com", "abcdef", "Alice")
    assert user is not None
    assert user["tier"] == "email"
    ok, _ = db.verifier_quota(user)
    assert ok is True
    for _ in range(quota_pour("email").requetes_par_jour):
        db.enregistrer_usage(user["id"], "ask", {})
    ok2, msg2 = db.verifier_quota(user)
    assert ok2 is False
    assert "Quota" in msg2


def test_invite_et_github_upsert(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "secretadmin")
    db = UtilisateursSQLite(tmp_path / "users2.db")
    invite = db.creer_invite("Guest1")
    assert invite["tier"] == "guest"
    gh = db.upsert_github("12345", "octocat", email="octo@github.com")
    assert gh["tier"] == "github"
    gh2 = db.upsert_github("12345", "octocat")
    assert gh2["id"] == gh["id"]


def test_admin_suspend_tier(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "secretadmin")
    db = UtilisateursSQLite(tmp_path / "users3.db")
    user, _ = db.inscrire_email("bob@test.com", "abcdef", "Bob")
    assert db.set_tier(user["id"], "github", admin_id="admin")
    assert db.obtenir(user["id"])["tier"] == "github"
    assert db.suspendre(user["id"], True, admin_id="admin")
    ok, msg = db.verifier_quota(db.obtenir(user["id"]))
    assert ok is False
    assert "suspendu" in msg.lower()
