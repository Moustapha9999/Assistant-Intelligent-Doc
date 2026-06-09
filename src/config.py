"""
Configuration centrale du projet.

Source unique de vérité pour :
- les chemins (toujours ancrés sur la racine du projet, peu importe le CWD)
- l'emplacement du cache des modèles (unifié)
- le contournement SSL (désactivé par défaut, activable pour dépannage réseau)
"""

import os
import ssl
from pathlib import Path

# --- Racine du projet ---------------------------------------------------------
# Ce fichier est dans src/, donc la racine est un niveau au-dessus.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# --- Dossiers de données (ancrés sur la racine) -------------------------------
DATA_DIR = PROJECT_ROOT / 'data'
RAW_DIR = DATA_DIR / 'raw'
PROCESSED_DIR = DATA_DIR / 'processed'
CHUNKS_DIR = PROCESSED_DIR / 'chunks'

# Fichiers clés du pipeline
REPOS_SELECTIONNES_FILE = RAW_DIR / 'repos_selectionnes.yaml'
READMES_RAW_DIR = RAW_DIR / 'readmes'
READMES_NETTOYES_DIR = PROCESSED_DIR / 'readmes_nettoyes'
CHUNKS_FILE = CHUNKS_DIR / 'tous_chunks.yaml'
EMBEDDINGS_FILE = CHUNKS_DIR / 'chunks_avec_embeddings.npz'

# --- Configurations -----------------------------------------------------------
CONFIGS_DIR = PROJECT_ROOT / 'configs'
REPOS_CONFIG_FILE = CONFIGS_DIR / 'repos_github.yaml'
QDRANT_CONFIG_FILE = CONFIGS_DIR / 'qdrant_config.yaml'

# --- Modèle & cache (unifié : un seul emplacement) ----------------------------
MODELS_CACHE_DIR = PROJECT_ROOT / 'models_cache'
MODELE_EMBEDDINGS = 'sentence-transformers/all-MiniLM-L6-v2'


def configurer_ssl():
    """
    Désactive la vérification SSL UNIQUEMENT si la variable d'environnement
    DISABLE_SSL_VERIFY=1 est définie.

    À n'utiliser qu'en dépannage (réseau d'entreprise/école avec proxy qui
    casse la chaîne de certificats). Ne jamais activer en production.
    """
    if os.getenv('DISABLE_SSL_VERIFY') == '1':
        ssl._create_default_https_context = ssl._create_unverified_context
        print("  SSL: vérification désactivée (DISABLE_SSL_VERIFY=1)")
