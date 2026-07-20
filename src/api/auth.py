"""Dépendances FastAPI (clés API + secret webhook)."""

from __future__ import annotations

import os
import secrets
from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from securite.identifiants import charger_api_keys

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def exiger_api_key(api_key: Optional[str] = Security(API_KEY_HEADER)) -> str:
    """
    Dépendance FastAPI. Retourne le propriétaire de la clé.
    Si API_KEYS est vide → autorise (owner=anonymous).
    """
    known = charger_api_keys()
    if not known:
        return "anonymous"
    if not api_key or api_key not in known:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clé API manquante ou invalide (header X-API-Key).",
        )
    return known[api_key]


def verifier_secret_webhook(secret_recu: Optional[str]) -> None:
    attendu = os.getenv("INGEST_WEBHOOK_SECRET", "").strip()
    if not attendu:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="INGEST_WEBHOOK_SECRET non configuré.",
        )
    if not secret_recu or not secrets.compare_digest(secret_recu, attendu):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Secret webhook invalide.",
        )
