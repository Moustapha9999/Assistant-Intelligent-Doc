"""Quotas d'utilisation par niveau de compte."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class QuotaTier:
    """Limites quotidiennes (requêtes chat) et minutes de session indicatives."""

    requetes_par_jour: int  # -1 = illimité
    minutes_session: int  # -1 = illimité
    label: str


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


QUOTAS: Dict[str, QuotaTier] = {
    "guest": QuotaTier(
        requetes_par_jour=_int_env("QUOTA_GUEST_REQ", 12),
        minutes_session=_int_env("QUOTA_GUEST_MIN", 30),
        label="Invité (sans compte)",
    ),
    "email": QuotaTier(
        requetes_par_jour=_int_env("QUOTA_EMAIL_REQ", 80),
        minutes_session=_int_env("QUOTA_EMAIL_MIN", 180),
        label="Compte email",
    ),
    "github": QuotaTier(
        requetes_par_jour=_int_env("QUOTA_GITHUB_REQ", 200),
        minutes_session=_int_env("QUOTA_GITHUB_MIN", 480),
        label="Compte GitHub",
    ),
    "google": QuotaTier(
        requetes_par_jour=_int_env("QUOTA_GOOGLE_REQ", 120),
        minutes_session=_int_env("QUOTA_GOOGLE_MIN", 360),
        label="Compte Google",
    ),
    "apple": QuotaTier(
        requetes_par_jour=_int_env("QUOTA_APPLE_REQ", 120),
        minutes_session=_int_env("QUOTA_APPLE_MIN", 360),
        label="Compte Apple",
    ),
    "admin": QuotaTier(
        requetes_par_jour=-1,
        minutes_session=-1,
        label="Administrateur",
    ),
}


def quota_pour(tier: str) -> QuotaTier:
    base = QUOTAS.get((tier or "guest").lower(), QUOTAS["guest"])
    # Surcharge runtime Admin si présente
    try:
        from app.runtime_config import charger

        rt = charger()
        key = {
            "guest": "QUOTA_GUEST_REQ",
            "email": "QUOTA_EMAIL_REQ",
            "github": "QUOTA_GITHUB_REQ",
            "google": "QUOTA_GOOGLE_REQ",
            "apple": "QUOTA_APPLE_REQ",
        }.get((tier or "guest").lower())
        if key and key in rt and base.requetes_par_jour >= 0:
            return QuotaTier(
                requetes_par_jour=int(rt[key]),
                minutes_session=base.minutes_session,
                label=base.label,
            )
    except Exception:
        pass
    return base
