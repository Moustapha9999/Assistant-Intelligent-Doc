"""Helpers OAuth communs (PKCE, messages inter-fenêtres, erreurs fournisseur).

Aucune donnée sensible n'est transportée vers le frontend : les messages entre
fenêtres ne portent que le type d'issue (ok / erreur / annule). La session
reste établie uniquement côté serveur.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Any, Tuple
from urllib.parse import urlparse, urlunparse

SOURCE_MESSAGE = "assistdoc-oauth"
CANAL_MESSAGE = "assistdoc-oauth"
NOM_FENETRE = "assistdoc-oauth"
TYPES_MESSAGE = ("ok", "erreur", "annule")
CHAMPS_INTERDITS = (
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "code",
    "secret",
    "client_secret",
    "code_verifier",
)


def pkce_paire() -> Tuple[str, str]:
    """Retourne (code_verifier, code_challenge S256)."""
    verifieur = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifieur.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    return verifieur, challenge


def normaliser_redirect_uri(uri: str) -> str:
    """Aligné sur les règles Google : schéma, hôte et slash final identiques."""
    brut = (uri or "").strip()
    if not brut:
        return brut
    analyse = urlparse(brut)
    if not analyse.scheme or not analyse.netloc:
        return brut
    chemin = analyse.path or "/"
    if chemin == "":
        chemin = "/"
    return urlunparse((analyse.scheme, analyse.netloc, chemin, "", "", ""))


def email_verifie(valeur: Any) -> bool:
    return valeur in (True, "true", "True", "1", 1)


def message_oauth_valide(origine: str, attendue: str, payload: Any) -> bool:
    """True seulement pour un message de contrôle issu de la même origine.

    Un message « ok » n'est jamais une preuve d'authentification : il sert
    uniquement à demander un nouveau rendu, qui relit la session serveur.
    """
    if not origine or not attendue or origine != attendue:
        return False
    if not isinstance(payload, dict):
        return False
    if payload.get("source") != SOURCE_MESSAGE:
        return False
    if payload.get("type") not in TYPES_MESSAGE:
        return False
    for champ in CHAMPS_INTERDITS:
        if payload.get(champ):
            return False
    return True


def fournisseur_depuis_etat(state: str) -> str:
    etat = str(state or "")
    if etat.startswith("ggl."):
        return "google"
    if etat.startswith("gh."):
        return "github"
    if etat.startswith("apl."):
        return "apple"
    return ""


def url_autorisation_autorisee(url: str) -> bool:
    try:
        analyse = urlparse(url)
    except Exception:
        return False
    if analyse.scheme != "https":
        return False
    if analyse.netloc == "accounts.google.com" and analyse.path.startswith("/o/oauth2/"):
        return True
    if analyse.netloc == "github.com" and analyse.path == "/login/oauth/authorize":
        return True
    return False


def message_annulation(erreur: str) -> bool:
    return (erreur or "").strip().lower() in {
        "access_denied",
        "user_cancelled",
        "user_canceled",
        "cancelled",
        "canceled",
        "consent_required",
    }


def detail_erreur_jeton(reponse: Any) -> str:
    """Extrait un motif affichable, sans jeton ni secret."""
    statut = getattr(reponse, "status_code", None)
    try:
        data = reponse.json()
    except Exception:
        return f"HTTP {statut}" if statut else "réponse invalide"
    if not isinstance(data, dict):
        return f"HTTP {statut}" if statut else "réponse invalide"
    for champ in CHAMPS_INTERDITS:
        data.pop(champ, None)
    motif = (data.get("error_description") or data.get("error") or "").strip()
    if motif:
        return motif[:300]
    return f"HTTP {statut}" if statut else "réponse invalide"
