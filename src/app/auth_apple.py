"""OAuth Sign in with Apple (Services ID + clé .p8).

Activé si :
  APPLE_OAUTH_CLIENT_ID  (Services ID, ex. com.assistdoc.web)
  APPLE_TEAM_ID
  APPLE_KEY_ID
  APPLE_PRIVATE_KEY ou APPLE_PRIVATE_KEY_PATH (.p8)

Apple envoie le retour en form_post → callback FastAPI
  POST /auth/apple/callback  → redirige vers Streamlit ?code=&state=
"""

from __future__ import annotations

import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

import httpx

try:
    import jwt
except ImportError:  # pragma: no cover
    jwt = None  # type: ignore


def apple_oauth_configure() -> bool:
    if jwt is None:
        return False
    has_key = bool(
        os.getenv("APPLE_PRIVATE_KEY", "").strip()
        or (
            os.getenv("APPLE_PRIVATE_KEY_PATH", "").strip()
            and Path(os.getenv("APPLE_PRIVATE_KEY_PATH", "").strip()).exists()
        )
    )
    return bool(
        os.getenv("APPLE_OAUTH_CLIENT_ID", "").strip()
        and os.getenv("APPLE_TEAM_ID", "").strip()
        and os.getenv("APPLE_KEY_ID", "").strip()
        and has_key
    )


def _lire_cle_privee() -> str:
    path = os.getenv("APPLE_PRIVATE_KEY_PATH", "").strip()
    if path and Path(path).exists():
        return Path(path).read_text(encoding="utf-8")
    raw = os.getenv("APPLE_PRIVATE_KEY", "").strip()
    return raw.replace("\\n", "\n")


def generer_client_secret() -> str:
    """JWT ES256 exigé par Apple comme client_secret."""
    if jwt is None:
        raise RuntimeError("Installez PyJWT : pip install 'PyJWT[crypto]'")
    now = int(time.time())
    headers = {"kid": os.getenv("APPLE_KEY_ID", "").strip(), "alg": "ES256"}
    payload = {
        "iss": os.getenv("APPLE_TEAM_ID", "").strip(),
        "iat": now,
        "exp": now + 86400 * 150,  # < 6 mois
        "aud": "https://appleid.apple.com",
        "sub": os.getenv("APPLE_OAUTH_CLIENT_ID", "").strip(),
    }
    return jwt.encode(payload, _lire_cle_privee(), algorithm="ES256", headers=headers)


def redirect_uri_apple() -> str:
    """URI enregistrée chez Apple (souvent le callback FastAPI)."""
    return (
        os.getenv("APPLE_OAUTH_REDIRECT_URI", "").strip()
        or "http://localhost:8000/auth/apple/callback"
    )


def url_autorisation(state: str) -> str:
    params = {
        "client_id": os.getenv("APPLE_OAUTH_CLIENT_ID", "").strip(),
        "redirect_uri": redirect_uri_apple(),
        "response_type": "code",
        "scope": "name email",
        "response_mode": "form_post",
        "state": state,
    }
    return "https://appleid.apple.com/auth/authorize?" + urlencode(params)


def _decoder_id_token(id_token: str) -> Dict[str, Any]:
    if jwt is None:
        return {}
    try:
        # Vérif. signature optionnelle en local ; on lit les claims
        return jwt.decode(
            id_token,
            options={"verify_signature": False, "verify_aud": False},
        )
    except Exception:
        return {}


def echanger_code(code: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Échange le code Apple contre profil (sub + email)."""
    if not apple_oauth_configure():
        return None, "Apple OAuth non configuré."
    try:
        client_secret = generer_client_secret()
        with httpx.Client(timeout=25.0) as client:
            token_r = client.post(
                "https://appleid.apple.com/auth/token",
                data={
                    "client_id": os.getenv("APPLE_OAUTH_CLIENT_ID", "").strip(),
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri_apple(),
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            if token_r.status_code >= 400:
                detail = token_r.text[:300]
                return None, f"Token Apple refusé ({token_r.status_code}) : {detail}"
            token_data = token_r.json()
            id_token = token_data.get("id_token") or ""
            claims = _decoder_id_token(id_token) if id_token else {}
            apple_id = str(claims.get("sub") or "").strip()
            if not apple_id:
                return None, "Profil Apple invalide (sub manquant)."
            email = (claims.get("email") or "").strip().lower() or None
            return {
                "apple_id": apple_id,
                "email": email,
                "email_verified": claims.get("email_verified"),
                "is_private_email": claims.get("is_private_email"),
            }, "ok"
    except Exception as exc:
        return None, f"Erreur OAuth Apple : {exc}"


def nouveau_state() -> str:
    return "apl." + secrets.token_urlsafe(24)
