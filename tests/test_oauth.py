"""OAuth Google / GitHub : PKCE, erreurs fournisseur, messages inter-fenêtres."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.auth_github import echanger_code as echanger_github, url_autorisation as url_github
from app.auth_google import echanger_code as echanger_google, url_autorisation as url_google
from app.auth_oauth import (
    SOURCE_MESSAGE,
    message_oauth_valide,
    normaliser_redirect_uri,
    pkce_paire,
    url_autorisation_autorisee,
)
from app.identite import _JS_COOKIE
from app.utilisateurs_sqlite import UtilisateursSQLite


@pytest.fixture
def oauth_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "id-google.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "secret-google")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_ID", "id-github")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_SECRET", "secret-github")


def test_pkce_paire_s256():
    import base64
    import hashlib

    verifieur, challenge = pkce_paire()
    assert verifieur != challenge and len(verifieur) >= 43
    attendu = (
        base64.urlsafe_b64encode(hashlib.sha256(verifieur.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    assert challenge == attendu


def test_normaliser_redirect_uri_slash_final():
    assert normaliser_redirect_uri("http://localhost:8501") == "http://localhost:8501/"
    assert normaliser_redirect_uri("http://localhost:8501/") == "http://localhost:8501/"
    assert normaliser_redirect_uri("https://app.exemple/google") == "https://app.exemple/google"


def test_urls_autorisation_contiennent_pkce_et_pas_de_secret(oauth_env):
    g = urlparse(url_google("http://localhost:8501", "ggl.abc", "challenge-x"))
    h = urlparse(url_github("http://localhost:8501", "gh.abc", "challenge-y"))
    gq, hq = parse_qs(g.query), parse_qs(h.query)
    assert g.netloc == "accounts.google.com"
    assert h.netloc == "github.com" and h.path == "/login/oauth/authorize"
    assert gq["redirect_uri"] == ["http://localhost:8501/"]
    assert gq["code_challenge"] == ["challenge-x"] and gq["code_challenge_method"] == ["S256"]
    assert hq["code_challenge"] == ["challenge-y"]
    assert "secret" not in g.query and "secret" not in h.query
    assert url_autorisation_autorisee(g.geturl())
    assert url_autorisation_autorisee(h.geturl())
    assert not url_autorisation_autorisee("https://evil.exemple/login")


class _FauxHTTP:
    def __init__(self, routes):
        self.routes = routes
        self.appels = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, data=None, headers=None):
        self.appels.append(("POST", url, dict(data or {})))
        return self.routes[("POST", url)]

    def get(self, url, headers=None):
        self.appels.append(("GET", url, None))
        return self.routes[("GET", url)]


class _Reponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return dict(self._payload)


def test_echanger_google_envoie_pkce_et_accepte_email_verifie_texte(oauth_env, monkeypatch):
    routes = {
        ("POST", "https://oauth2.googleapis.com/token"): _Reponse(
            200, {"access_token": "atok"}
        ),
        ("GET", "https://www.googleapis.com/oauth2/v3/userinfo"): _Reponse(
            200,
            {
                "sub": "gid-1",
                "email": "eleve@exemple.com",
                "email_verified": "true",
                "name": "Élève",
            },
        ),
    }
    faux = _FauxHTTP(routes)
    monkeypatch.setattr("app.auth_google.httpx.Client", lambda timeout=None: faux)
    profil, err = echanger_google("code-x", "http://localhost:8501", "verif-pkce")
    assert err == "ok" and profil["google_id"] == "gid-1" and profil["email"] == "eleve@exemple.com"
    corps = faux.appels[0][2]
    assert corps["code_verifier"] == "verif-pkce"
    assert corps["redirect_uri"] == "http://localhost:8501/"
    assert "client_secret" in corps


def test_echanger_google_refuse_sans_exposer_le_jeton(oauth_env, monkeypatch):
    routes = {
        ("POST", "https://oauth2.googleapis.com/token"): _Reponse(
            400,
            {
                "error": "redirect_uri_mismatch",
                "error_description": "redirect_uri mismatch",
                "access_token": "ne-pas-fuiter",
            },
        ),
    }
    monkeypatch.setattr(
        "app.auth_google.httpx.Client", lambda timeout=None: _FauxHTTP(routes)
    )
    profil, err = echanger_google("code-x", "http://localhost:8501/", "verif")
    assert profil is None
    assert "redirect_uri mismatch" in err
    assert "ne-pas-fuiter" not in err
    assert "secret-google" not in err


def test_echanger_github_envoie_pkce(oauth_env, monkeypatch):
    routes = {
        ("POST", "https://github.com/login/oauth/access_token"): _Reponse(
            200, {"access_token": "ghtok"}
        ),
        ("GET", "https://api.github.com/user"): _Reponse(
            200, {"id": 42, "login": "alice", "email": "a@exemple.com", "name": "Alice"}
        ),
    }
    faux = _FauxHTTP(routes)
    monkeypatch.setattr("app.auth_github.httpx.Client", lambda timeout=None: faux)
    profil, err = echanger_github("code-gh", "https://app.exemple/github", "verif-gh")
    assert err == "ok" and profil["github_id"] == "42"
    assert faux.appels[0][2]["code_verifier"] == "verif-gh"


def test_message_oauth_origine_et_contenu():
    origine = "http://localhost:8501"
    assert message_oauth_valide(origine, origine, {"source": SOURCE_MESSAGE, "type": "ok"})
    assert not message_oauth_valide("https://evil.exemple", origine, {"source": SOURCE_MESSAGE, "type": "ok"})
    assert not message_oauth_valide(origine, origine, {"source": SOURCE_MESSAGE, "type": "ok", "access_token": "x"})
    assert not message_oauth_valide(origine, origine, {"source": SOURCE_MESSAGE, "type": "pirate"})
    assert not message_oauth_valide(origine, origine, "ok")


def test_js_fenetre_verifie_origine_et_ne_transporte_pas_de_jeton():
    assert "window.location.origin" in _JS_COOKIE
    assert "INTERDITS" in _JS_COOKIE
    assert "BroadcastChannel" in _JS_COOKIE
    assert "window.close" in _JS_COOKIE
    assert 'window.open(href, "assistdoc-oauth"' in _JS_COOKIE
    assert "accounts.google.com" in _JS_COOKIE
    assert "github.com" in _JS_COOKIE
    assert "preventDefault" in _JS_COOKIE
    assert "composedPath" in _JS_COOKIE


def test_migration_pkce_sur_ancienne_base(tmp_path, monkeypatch):
    """Une base Cloud créée avant pkce_verifier doit accepter un enregistrement OAuth."""
    import sqlite3

    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("STREAMLIT_PASSWORD", raising=False)
    chemin = tmp_path / "ancienne.db"
    with sqlite3.connect(chemin) as conn:
        conn.executescript(
            """
            CREATE TABLE users (
                id TEXT PRIMARY KEY, email TEXT, password_hash TEXT,
                display_name TEXT NOT NULL DEFAULT '', tier TEXT NOT NULL DEFAULT 'guest',
                suspended INTEGER NOT NULL DEFAULT 0, cree_le TEXT NOT NULL,
                derniere_connexion TEXT
            );
            CREATE TABLE admin_audit (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, cree_le TEXT);
            CREATE TABLE oauth_etats (
                etat_hash TEXT PRIMARY KEY,
                fournisseur TEXT NOT NULL,
                session_hash TEXT,
                expire_le TEXT NOT NULL
            );
            """
        )
    db = UtilisateursSQLite(chemin)
    db.enregistrer_etat_oauth("ggl.old", "google", "jeton-x", pkce_verifier="verif-old")
    recu: list = []
    assert db.consommer_etat_oauth(
        "ggl.old", "google", "jeton-x", pkce_out=recu
    ) is True
    assert recu == ["verif-old"]


def test_etat_oauth_conserve_pkce(tmp_path, monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("STREAMLIT_PASSWORD", raising=False)
    db = UtilisateursSQLite(tmp_path / "u.db")
    invite = db.creer_invite()
    jeton = db.creer_session(invite["id"])
    db.enregistrer_etat_oauth("ggl.pkce", "google", jeton, pkce_verifier="abc-verif")
    recu: list = []
    assert db.consommer_etat_oauth("ggl.pkce", "google", jeton, pkce_out=recu) is True
    assert recu == ["abc-verif"]
    assert db.consommer_etat_oauth("ggl.pkce", "google", jeton) is False


def test_signal_ok_ne_authentifie_pas_sans_session_serveur(tmp_path, monkeypatch):
    """Un message frontend « ok » ne crée pas de compte : seule la session SQL compte."""
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("STREAMLIT_PASSWORD", raising=False)
    db = UtilisateursSQLite(tmp_path / "u.db")
    invite, jeton = db.creer_invite(), None
    jeton = db.creer_session(invite["id"])
    assert message_oauth_valide("http://localhost:8501", "http://localhost:8501", {
        "source": SOURCE_MESSAGE, "type": "ok",
    })
    assert db.valider_session(jeton)["tier"] == "guest"
    assert not any(u.get("tier") == "google" for u in db.lister_users())
