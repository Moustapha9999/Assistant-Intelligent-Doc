"""Dépendances FastAPI (clés API + secret webhook + admin + limitation de débit)."""

from __future__ import annotations

import os
import secrets
import threading
import time
from collections import defaultdict, deque
from functools import lru_cache
from typing import Deque, Dict, Optional

from fastapi import Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from securite.identifiants import charger_api_keys

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


@lru_cache(maxsize=1)
def _journal():
    from app.utilisateurs_sqlite import UtilisateursSQLite

    return UtilisateursSQLite()


def journaliser(action: str, gravite: str, details: str) -> None:
    try:
        _journal().evenement_securite(action, gravite, details, acteur="api")
    except Exception as exc:
        print(f"   ⚠️  Journal API indisponible : {type(exc).__name__}")


def exiger_api_key(api_key: Optional[str] = Security(API_KEY_HEADER)) -> str:
    """
    Dépendance FastAPI. Retourne le propriétaire de la clé.
    Si API_KEYS est vide → autorise (owner=anonymous).
    """
    known = charger_api_keys()
    if not known:
        return "anonymous"
    proprietaire = next((o for k, o in known.items() if api_key and secrets.compare_digest(k, api_key)), None)
    if proprietaire is None:
        journaliser("api_acces_refuse", "faible", "Clé API absente ou invalide")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clé API manquante ou invalide (header X-API-Key).",
        )
    return proprietaire


def verifier_secret_webhook(secret_recu: Optional[str]) -> None:
    attendu = os.getenv("INGEST_WEBHOOK_SECRET", "").strip()
    if not attendu:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="INGEST_WEBHOOK_SECRET non configuré.",
        )
    if not secret_recu or not secrets.compare_digest(secret_recu, attendu):
        journaliser("api_acces_refuse", "moyenne", "Secret de webhook invalide")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Secret webhook invalide.",
        )


def exiger_admin_api(
    x_admin_key: Optional[str] = Header(default=None, alias="X-Admin-Key"),
) -> str:
    """
    Garde d'administration pour les routes FastAPI sensibles.
    Attend le header X-Admin-Key égal à ADMIN_API_KEY (clé dédiée : le mot de passe
    administrateur n'est jamais accepté comme clé d'API).
    """
    attendu = os.getenv("ADMIN_API_KEY", "").strip()
    if not attendu:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_API_KEY non configuré — routes admin indisponibles.",
        )
    if not x_admin_key or not secrets.compare_digest(x_admin_key, attendu):
        journaliser("api_acces_refuse", "elevee", "Route d'administration de l'API : clé refusée")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès refusé : rôle administrateur requis.",
        )
    return "admin"


class LimiteurDebit:
    """Fenêtre glissante en mémoire, par propriétaire de clé (processus unique)."""

    def __init__(self, fenetre_s: float = 60.0):
        self.fenetre_s = fenetre_s
        self._appels: Dict[str, Deque[float]] = defaultdict(deque)
        self._verrou = threading.Lock()

    def autoriser(self, cle: str, maximum: int, maintenant: Optional[float] = None) -> bool:
        t = time.monotonic() if maintenant is None else maintenant
        with self._verrou:
            appels = self._appels[cle]
            while appels and appels[0] <= t - self.fenetre_s:
                appels.popleft()
            if len(appels) >= maximum:
                return False
            appels.append(t)
            return True


LIMITEUR = LimiteurDebit()


def limiter(owner: str) -> None:
    try:
        maximum = max(1, int(os.getenv("API_LIMITE_PAR_MINUTE", "30")))
    except ValueError:
        maximum = 30
    if not LIMITEUR.autoriser(owner or "anonymous", maximum):
        journaliser("api_limite", "faible", f"Limite de {maximum} requêtes/min atteinte")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de requêtes. Réessayez dans une minute.",
            headers={"Retry-After": "60"},
        )
