"""Paramètres IA runtime (éditables depuis l'Admin, sans redémarrer tout le .env)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

import sys

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

load_dotenv(config.PROJECT_ROOT / ".env", override=True)

RUNTIME_FILE = config.DB_DIR / "runtime_ia.json"

_FALLBACKS: Dict[str, Any] = {
    "LLM_MODEL": "openai/gpt-oss-120b",
    "LLM_TEMPERATURE": 0.3,
    "LLM_TOP_P": 0.95,
    "LLM_PRESENCE_PENALTY": 0.0,
    "LLM_FREQUENCY_PENALTY": 0.2,
    "MAX_TOKENS": 3000,
    "GROQ_VISION_MODEL": "groq/compound",
    "QUOTA_GUEST_REQ": 12,
    "QUOTA_EMAIL_REQ": 80,
    "QUOTA_GITHUB_REQ": 200,
    "DESACTIVER_WEB_SEARCH": "false",
}


def _defaults_depuis_env() -> Dict[str, Any]:
    """Relit le .env à chaque appel (pas de valeurs figées à l'import)."""
    return {
        "LLM_MODEL": os.getenv("LLM_MODEL", str(_FALLBACKS["LLM_MODEL"])),
        "LLM_TEMPERATURE": float(
            os.getenv("LLM_TEMPERATURE", str(_FALLBACKS["LLM_TEMPERATURE"]))
        ),
        "LLM_TOP_P": float(os.getenv("LLM_TOP_P", str(_FALLBACKS["LLM_TOP_P"]))),
        "LLM_PRESENCE_PENALTY": float(
            os.getenv("LLM_PRESENCE_PENALTY", str(_FALLBACKS["LLM_PRESENCE_PENALTY"]))
        ),
        "LLM_FREQUENCY_PENALTY": float(
            os.getenv(
                "LLM_FREQUENCY_PENALTY", str(_FALLBACKS["LLM_FREQUENCY_PENALTY"])
            )
        ),
        "MAX_TOKENS": int(os.getenv("MAX_TOKENS", str(_FALLBACKS["MAX_TOKENS"]))),
        "GROQ_VISION_MODEL": os.getenv(
            "GROQ_VISION_MODEL", str(_FALLBACKS["GROQ_VISION_MODEL"])
        ),
        "QUOTA_GUEST_REQ": int(
            os.getenv("QUOTA_GUEST_REQ", str(_FALLBACKS["QUOTA_GUEST_REQ"]))
        ),
        "QUOTA_EMAIL_REQ": int(
            os.getenv("QUOTA_EMAIL_REQ", str(_FALLBACKS["QUOTA_EMAIL_REQ"]))
        ),
        "QUOTA_GITHUB_REQ": int(
            os.getenv("QUOTA_GITHUB_REQ", str(_FALLBACKS["QUOTA_GITHUB_REQ"]))
        ),
        "DESACTIVER_WEB_SEARCH": os.getenv(
            "DESACTIVER_WEB_SEARCH", str(_FALLBACKS["DESACTIVER_WEB_SEARCH"])
        ),
    }


# Compat : certains modules importent encore DEFAULTS
DEFAULTS = _defaults_depuis_env()


def charger() -> Dict[str, Any]:
    data = _defaults_depuis_env()
    if RUNTIME_FILE.exists():
        try:
            saved = json.loads(RUNTIME_FILE.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                # Ne pas garder un modèle Groq retiré sauvegardé en admin
                modele = str(saved.get("LLM_MODEL") or "")
                if "llama-3.3-70b" in modele or "llama-3.1-8b-instant" in modele:
                    saved = {**saved, "LLM_MODEL": data["LLM_MODEL"]}
                vision = str(saved.get("GROQ_VISION_MODEL") or "")
                if "llama-4-scout" in vision:
                    saved = {**saved, "GROQ_VISION_MODEL": data["GROQ_VISION_MODEL"]}
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
