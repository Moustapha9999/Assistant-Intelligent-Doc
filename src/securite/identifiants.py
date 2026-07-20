"""Parsing des utilisateurs Streamlit et des clés API (sans FastAPI)."""

from __future__ import annotations

import hashlib
import hmac
import os
from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class Utilisateur:
    username: str
    password_hash: str


def _hash(valeur: str) -> str:
    return hashlib.sha256(valeur.encode("utf-8")).hexdigest()


def charger_utilisateurs_streamlit() -> List[Utilisateur]:
    """
    Formats acceptés (env STREAMLIT_USERS) :
      alice:motdepasse,bob:autre
    Ou un seul mot de passe via STREAMLIT_PASSWORD (user=admin).
    """
    brut = os.getenv("STREAMLIT_USERS", "").strip()
    users: List[Utilisateur] = []
    if brut:
        for part in brut.split(","):
            part = part.strip()
            if not part or ":" not in part:
                continue
            username, password = part.split(":", 1)
            username, password = username.strip(), password.strip()
            if username and password:
                users.append(Utilisateur(username, _hash(password)))
    single = os.getenv("STREAMLIT_PASSWORD", "").strip()
    if single and not users:
        users.append(Utilisateur("admin", _hash(single)))
    return users


def verifier_utilisateur(username: str, password: str) -> bool:
    cible = _hash(password)
    for u in charger_utilisateurs_streamlit():
        if hmac.compare_digest(u.username, username) and hmac.compare_digest(
            u.password_hash, cible
        ):
            return True
    single = os.getenv("STREAMLIT_PASSWORD", "").strip()
    if single and hmac.compare_digest(_hash(password), _hash(single)):
        return True
    return False


def charger_admins() -> List[str]:
    """
    Liste des identifiants admin (env ADMIN_USERS, séparés par des virgules).
    Défaut : admin
    """
    brut = os.getenv("ADMIN_USERS", "admin").strip()
    if not brut:
        return ["admin"]
    return [u.strip().lower() for u in brut.split(",") if u.strip()]


def est_admin(username: str | None) -> bool:
    """True si l'utilisateur fait partie de ADMIN_USERS."""
    if not username:
        return False
    return username.strip().lower() in charger_admins()


def auth_streamlit_active() -> bool:
    """True si un mot de passe / multi-users est configuré."""
    return bool(
        os.getenv("STREAMLIT_USERS", "").strip()
        or os.getenv("STREAMLIT_PASSWORD", "").strip()
    )


def charger_api_keys() -> Dict[str, str]:
    """
    Formats (env API_KEYS) :
      cle1:alice,cle2:bob
    Si vide → auth API désactivée (accès libre, utile en local).
    """
    brut = os.getenv("API_KEYS", "").strip()
    keys: Dict[str, str] = {}
    if not brut:
        return keys
    for part in brut.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        key, owner = part.split(":", 1)
        key, owner = key.strip(), owner.strip()
        if key and owner:
            keys[key] = owner
    return keys
