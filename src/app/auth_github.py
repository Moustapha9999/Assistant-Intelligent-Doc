"""OAuth GitHub (activé si GITHUB_OAUTH_CLIENT_ID / SECRET présents)."""

from __future__ import annotations

import os
import secrets
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

import httpx


def github_oauth_configure() -> bool:
    return bool(
        os.getenv("GITHUB_OAUTH_CLIENT_ID", "").strip()
        and os.getenv("GITHUB_OAUTH_CLIENT_SECRET", "").strip()
    )


def url_autorisation(redirect_uri: str, state: str) -> str:
    params = {
        "client_id": os.getenv("GITHUB_OAUTH_CLIENT_ID", "").strip(),
        "redirect_uri": redirect_uri,
        "scope": "read:user user:email",
        "state": state,
    }
    return "https://github.com/login/oauth/authorize?" + urlencode(params)


def echanger_code(code: str, redirect_uri: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Échange le code OAuth contre le profil GitHub."""
    client_id = os.getenv("GITHUB_OAUTH_CLIENT_ID", "").strip()
    client_secret = os.getenv("GITHUB_OAUTH_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None, "GitHub OAuth non configuré."
    try:
        with httpx.Client(timeout=20.0) as client:
            token_r = client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            )
            token_r.raise_for_status()
            token_data = token_r.json()
            access = token_data.get("access_token")
            if not access:
                return None, token_data.get("error_description") or "Token GitHub refusé."

            user_r = client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access}",
                    "Accept": "application/vnd.github+json",
                },
            )
            user_r.raise_for_status()
            profile = user_r.json()

            email = profile.get("email")
            if not email:
                mails_r = client.get(
                    "https://api.github.com/user/emails",
                    headers={
                        "Authorization": f"Bearer {access}",
                        "Accept": "application/vnd.github+json",
                    },
                )
                if mails_r.status_code == 200:
                    for m in mails_r.json():
                        if m.get("primary") and m.get("verified"):
                            email = m.get("email")
                            break
            return {
                "github_id": str(profile.get("id")),
                "github_login": profile.get("login") or "",
                "email": email,
                "name": profile.get("name") or profile.get("login") or "",
            }, "ok"
    except Exception as exc:
        return None, f"Erreur OAuth GitHub : {exc}"


def nouveau_state() -> str:
    return "gh." + secrets.token_urlsafe(24)
