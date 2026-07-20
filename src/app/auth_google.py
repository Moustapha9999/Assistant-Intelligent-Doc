"""OAuth Google (activé si GOOGLE_OAUTH_CLIENT_ID / SECRET présents)."""

from __future__ import annotations

import os
import secrets
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

import httpx


def google_oauth_configure() -> bool:
    return bool(
        os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
        and os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    )


def url_autorisation(redirect_uri: str, state: str) -> str:
    params = {
        "client_id": os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip(),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)


def echanger_code(code: str, redirect_uri: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Échange le code OAuth contre le profil Google."""
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None, "Google OAuth non configuré."
    try:
        with httpx.Client(timeout=20.0) as client:
            token_r = client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            token_r.raise_for_status()
            token_data = token_r.json()
            access = token_data.get("access_token")
            if not access:
                return None, token_data.get("error_description") or "Token Google refusé."

            user_r = client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {access}"},
            )
            user_r.raise_for_status()
            profile = user_r.json()
            google_id = str(profile.get("sub") or "").strip()
            if not google_id:
                return None, "Profil Google invalide (sub manquant)."
            email = (profile.get("email") or "").strip().lower() or None
            if email and profile.get("email_verified") is False:
                # Accepter quand même si Google renvoie l'email (souvent True)
                pass
            return {
                "google_id": google_id,
                "email": email,
                "name": profile.get("name")
                or profile.get("given_name")
                or (email.split("@")[0] if email else "Google"),
                "picture": profile.get("picture") or "",
            }, "ok"
    except Exception as exc:
        return None, f"Erreur OAuth Google : {exc}"


def nouveau_state() -> str:
    return "ggl." + secrets.token_urlsafe(24)
