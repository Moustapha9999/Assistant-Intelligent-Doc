"""
Configuration centrale du projet.

Source unique de vérité pour :
- les chemins (toujours ancrés sur la racine du projet, peu importe le CWD)
- l'emplacement du cache des modèles (unifié)
- la config Qdrant (YAML)
- le contournement SSL (désactivé par défaut)
"""

import os
import ssl
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml

# --- Racine du projet ---------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# --- Dossiers de données ------------------------------------------------------
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
CHUNKS_DIR = PROCESSED_DIR / "chunks"
DB_DIR = DATA_DIR / "app"
DB_DIR.mkdir(parents=True, exist_ok=True)

# Fichiers clés du pipeline (JSON = format réel produit par le découpeur)
REPOS_SELECTIONNES_FILE = RAW_DIR / "repos_selectionnes.yaml"
READMES_RAW_DIR = RAW_DIR / "readmes"
READMES_NETTOYES_DIR = PROCESSED_DIR / "readmes_nettoyes"
CHUNKS_FILE = CHUNKS_DIR / "tous_chunks.json"
EMBEDDINGS_FILE = CHUNKS_DIR / "chunks_avec_embeddings.npz"
HISTORIQUE_DB = DB_DIR / "historique.db"
FEEDBACK_DB = DB_DIR / "feedback.db"

# --- Configurations -----------------------------------------------------------
CONFIGS_DIR = PROJECT_ROOT / "configs"
REPOS_CONFIG_FILE = CONFIGS_DIR / "repos_github.yaml"
QDRANT_CONFIG_FILE = CONFIGS_DIR / "qdrant_config.yaml"

# --- Modèle & cache -----------------------------------------------------------
MODELS_CACHE_DIR = PROJECT_ROOT / "models_cache"
# Multilingue FR/EN (384 dims — compatible collection existante après ré-indexation)
MODELE_EMBEDDINGS = os.getenv(
    "EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)
MODELE_RERANKER = os.getenv(
    "RERANKER_MODEL",
    "cross-encoder/ms-marco-MiniLM-L-6-v2",
)

# --- Upload / sécurité --------------------------------------------------------
UPLOAD_MAX_BYTES = int(os.getenv("UPLOAD_MAX_BYTES", str(10 * 1024 * 1024)))  # 10 Mo
UPLOAD_EXTENSIONS_OK = {
    ".pdf", ".docx", ".doc", ".md", ".txt", ".rst",
    ".py", ".js", ".ts", ".java", ".go", ".rs", ".c", ".cpp", ".h",
    ".json", ".yaml", ".yml", ".toml", ".sql", ".sh",
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".wav", ".mp3", ".m4a", ".ogg", ".webm",
}


@lru_cache(maxsize=1)
def charger_qdrant_config() -> Dict[str, Any]:
    """Charge configs/qdrant_config.yaml (avec valeurs par défaut)."""
    defaults: Dict[str, Any] = {
        "collection": {
            "name": "github_docs",
            "vector_params": {"size": 384, "distance": "COSINE"},
        },
        "indexing": {"batch_size": 100, "optimize_after": True},
        "search": {
            "default_limit": 5,
            "score_threshold": 0.35,
            "abstention_threshold": 0.15,
            "freshness_weight": 0.08,
        },
    }
    if not QDRANT_CONFIG_FILE.exists():
        return defaults
    with open(QDRANT_CONFIG_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    # Fusion shallow des sections
    for cle, val in defaults.items():
        if isinstance(val, dict):
            data[cle] = {**val, **(data.get(cle) or {})}
            if cle == "collection":
                vp = {**val.get("vector_params", {}), **(data[cle].get("vector_params") or {})}
                data[cle]["vector_params"] = vp
        else:
            data.setdefault(cle, val)
    return data


def configurer_ssl():
    """
    Désactive la vérification SSL UNIQUEMENT si DISABLE_SSL_VERIFY=1.

    À n'utiliser qu'en dépannage (proxy d'entreprise). Jamais en production.
    """
    if os.getenv("DISABLE_SSL_VERIFY") == "1":
        ssl._create_default_https_context = ssl._create_unverified_context
        print("  SSL: vérification désactivée (DISABLE_SSL_VERIFY=1)")
