"""Paramètres IA runtime (éditables depuis l'Admin, sans redémarrer tout le .env)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

RUNTIME_FILE = config.DB_DIR / "runtime_ia.json"

DEFAULTS: Dict[str, Any] = {
    "LLM_MODEL": os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
    "LLM_TEMPERATURE": float(os.getenv("LLM_TEMPERATURE", "0.3")),
    "LLM_TOP_P": float(os.getenv("LLM_TOP_P", "0.95")),
    "LLM_PRESENCE_PENALTY": float(os.getenv("LLM_PRESENCE_PENALTY", "0")),
    "LLM_FREQUENCY_PENALTY": float(os.getenv("LLM_FREQUENCY_PENALTY", "0.2")),
    "MAX_TOKENS": int(os.getenv("MAX_TOKENS", "3000")),
    "GROQ_VISION_MODEL": os.getenv(
        "GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"
    ),
    "QUOTA_GUEST_REQ": int(os.getenv("QUOTA_GUEST_REQ", "12")),
    "QUOTA_EMAIL_REQ": int(os.getenv("QUOTA_EMAIL_REQ", "80")),
    "QUOTA_GITHUB_REQ": int(os.getenv("QUOTA_GITHUB_REQ", "200")),
    "DESACTIVER_WEB_SEARCH": os.getenv("DESACTIVER_WEB_SEARCH", "false"),
}


def charger() -> Dict[str, Any]:
    data = dict(DEFAULTS)
    if RUNTIME_FILE.exists():
        try:
            saved = json.loads(RUNTIME_FILE.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                data.update(saved)
        except (OSError, json.JSONDecodeError):
            pass
    return data


def sauvegarder(valeurs: Dict[str, Any]) -> None:
    actuel = charger()
    actuel.update(valeurs)
    RUNTIME_FILE.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_FILE.write_text(
        json.dumps(actuel, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Appliquer aussi en variables d'environnement pour le process courant
    for k, v in actuel.items():
        os.environ[str(k)] = str(v)


def get(cle: str, default: Any = None) -> Any:
    return charger().get(cle, default)
