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

# Date de la sélection GitHub figée (data/raw/repos_selectionnes.yaml) :
# les étoiles affichées proviennent de l'API GitHub à cette date.
DATE_COLLECTE_GITHUB = os.getenv("DATE_COLLECTE_GITHUB", "2026-06-11")

# --- Upload / sécurité --------------------------------------------------------
UPLOAD_MAX_BYTES = int(os.getenv("UPLOAD_MAX_BYTES", str(10 * 1024 * 1024)))  # 10 Mo
UPLOAD_EXTENSIONS_OK = {
    ".pdf", ".docx", ".md", ".txt", ".rst",
    ".xlsx", ".xls", ".csv", ".tsv", ".pptx",
    ".py", ".js", ".ts", ".java", ".go", ".rs", ".c", ".cpp", ".h",
    ".json", ".yaml", ".yml", ".toml", ".sql", ".sh", ".xml", ".html", ".htm",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
    ".wav", ".mp3", ".m4a", ".ogg", ".webm",
}
# Formats reconnus mais refusés faute de conversion fiable (aucun LibreOffice côté serveur)
UPLOAD_FORMATS_REFUSES = {
    ".doc": "Word 97-2003 (.doc) n'est pas pris en charge : enregistrez le document en .docx.",
    ".ppt": "PowerPoint 97-2003 (.ppt) n'est pas pris en charge : enregistrez la présentation en .pptx.",
    ".xlsm": "Les classeurs avec macros (.xlsm) sont refusés : enregistrez-le en .xlsx (sans macros).",
    ".docm": "Les documents avec macros (.docm) sont refusés : enregistrez-le en .docx.",
    ".svg": "Les images SVG ne sont pas prises en charge : exportez-la en PNG.",
}
FICHIERS_MAX_PAR_MESSAGE = int(os.getenv("FICHIERS_MAX_PAR_MESSAGE", "8"))
FICHIERS_MAX_IMAGES_VISION = int(os.getenv("FICHIERS_MAX_IMAGES_VISION", "5"))
# Budget de caractères du contexte « fichiers » injecté dans le prompt (limite TPM Groq)
FICHIERS_MAX_CHARS_PROMPT = int(os.getenv("FICHIERS_MAX_CHARS_PROMPT", "12000"))
# Texte extrait conservé en base par fichier (questions de suivi après rechargement)
FICHIERS_PERSIST_MAX_CHARS = int(os.getenv("FICHIERS_PERSIST_MAX_CHARS", "60000"))
FICHIERS_TIMEOUT_EXTRACTION_S = float(os.getenv("FICHIERS_TIMEOUT_EXTRACTION_S", "60"))
PDF_MAX_PAGES = int(os.getenv("PDF_MAX_PAGES", "300"))
PDF_OCR_MAX_PAGES = int(os.getenv("PDF_OCR_MAX_PAGES", "5"))
PDF_FIGURES_MAX_PAGES = int(os.getenv("PDF_FIGURES_MAX_PAGES", "3"))
TABLEUR_MAX_LIGNES = int(os.getenv("TABLEUR_MAX_LIGNES", "5000"))
ARCHIVE_MAX_DECOMPRESSE = int(os.getenv("ARCHIVE_MAX_DECOMPRESSE", str(200 * 1024 * 1024)))
ARCHIVE_MAX_MEMBRES = int(os.getenv("ARCHIVE_MAX_MEMBRES", "5000"))
IMAGE_MAX_PIXELS = int(os.getenv("IMAGE_MAX_PIXELS", str(40_000_000)))


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
            "score_threshold": 0.25,
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


def parametres_qdrant() -> Dict[str, Any]:
    """
    QDRANT_URL (+ QDRANT_API_KEY) cible une instance distante (Qdrant Cloud) ;
    sinon QDRANT_HOST / QDRANT_PORT (local ou service Docker).
    """
    timeout = int(os.getenv("QDRANT_TIMEOUT", "30"))
    url = os.getenv("QDRANT_URL", "").strip()
    if url:
        return {"url": url, "api_key": os.getenv("QDRANT_API_KEY") or None, "timeout": timeout}
    return {
        "host": os.getenv("QDRANT_HOST", "localhost"),
        "port": int(os.getenv("QDRANT_PORT", "6333")),
        "timeout": timeout,
    }


def creer_client_qdrant():
    from qdrant_client import QdrantClient

    return QdrantClient(**parametres_qdrant())


def decrire_cible_qdrant() -> str:
    p = parametres_qdrant()
    return p.get("url") or f"{p['host']}:{p['port']}"


CORPUS_MEMBRES = (
    "tous_chunks.json",
    "bm25_cache/meta.json",
    "bm25_cache/vocab.json",
    "bm25_cache/idf.npy",
    "bm25_cache/poids.npz",
)


def assurer_corpus(destination: Path = CHUNKS_DIR) -> bool:
    """
    Déploiement cloud : si tous_chunks.json est absent, télécharge l'archive CORPUS_URL
    (tous_chunks.json + cache BM25, produite par scripts/preparer_corpus_deploiement.py),
    vérifie CORPUS_SHA256 si défini, puis l'extrait dans `destination`.
    """
    if (destination / "tous_chunks.json").exists():
        return True
    url = os.getenv("CORPUS_URL", "").strip()
    if not url:
        return False

    import hashlib
    import tempfile
    import zipfile

    import requests

    destination.mkdir(parents=True, exist_ok=True)
    print(f"[*] Téléchargement du corpus : {url}")
    h = hashlib.sha256()
    with tempfile.NamedTemporaryFile(dir=destination, suffix=".zip", delete=False) as tmp:
        chemin_zip = Path(tmp.name)
        with requests.get(url, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            for bloc in resp.iter_content(chunk_size=4 * 1024 * 1024):
                tmp.write(bloc)
                h.update(bloc)
    try:
        attendu = os.getenv("CORPUS_SHA256", "").strip().lower()
        if attendu and h.hexdigest() != attendu:
            raise ValueError("CORPUS_SHA256 ne correspond pas à l'archive téléchargée")
        with zipfile.ZipFile(chemin_zip) as archive:
            # tous_chunks.json en dernier : sa présence signifie « installation complète »
            for membre in sorted(CORPUS_MEMBRES, key=lambda m: m == "tous_chunks.json"):
                if membre not in archive.namelist():
                    continue
                cible = destination / membre
                cible.parent.mkdir(parents=True, exist_ok=True)
                partiel = cible.with_suffix(cible.suffix + ".part")
                with archive.open(membre) as src, open(partiel, "wb") as dst:
                    while bloc := src.read(4 * 1024 * 1024):
                        dst.write(bloc)
                os.replace(partiel, cible)
    finally:
        chemin_zip.unlink(missing_ok=True)
    print("   [OK] Corpus installé")
    return (destination / "tous_chunks.json").exists()


def configurer_ssl():
    """
    Désactive la vérification SSL UNIQUEMENT si DISABLE_SSL_VERIFY=1.

    À n'utiliser qu'en dépannage (proxy d'entreprise). Jamais en production.
    """
    if os.getenv("DISABLE_SSL_VERIFY") == "1":
        ssl._create_default_https_context = ssl._create_unverified_context
        print("  SSL: vérification désactivée (DISABLE_SSL_VERIFY=1)")
