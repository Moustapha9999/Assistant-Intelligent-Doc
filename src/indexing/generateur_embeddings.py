"""
Module de génération des embeddings
"""

import sys
import yaml
from pathlib import Path
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
import numpy as np

# Rendre le projet importable (src/ sur le path) quel que soit le CWD
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config


class GenerateurEmbeddings:
    def __init__(self, nom_modele=config.MODELE_EMBEDDINGS):
        """
        Initialise le générateur d'embeddings

        Args:
            nom_modele: Nom du modèle d'embeddings à utiliser
        """
        print(f" A- Chargement du modèle {nom_modele}...")

        # Contournement SSL optionnel (uniquement si DISABLE_SSL_VERIFY=1)
        config.configurer_ssl()

        # Cache des modèles unifié dans models_cache/
        cache_dir = config.MODELS_CACHE_DIR
        cache_dir.mkdir(parents=True, exist_ok=True)

        self.modele = SentenceTransformer(nom_modele, cache_folder=str(cache_dir))
        # Compatibilité : la méthode a été renommée dans les versions récentes
        if hasattr(self.modele, 'get_embedding_dimension'):
            self.dimension = self.modele.get_embedding_dimension()
        else:
            self.dimension = self.modele.get_sentence_embedding_dimension()
        print(f" Modèle chargé (dimension: {self.dimension})")

    def generer_embedding(self, texte):
        """Génère l'embedding pour un texte"""
        return self.modele.encode(texte, convert_to_numpy=True)

    def generer_embeddings_batch(self, textes, batch_size=32):
        """Génère les embeddings pour un batch de textes"""
        return self.modele.encode(
            textes,
            convert_to_numpy=True,
            batch_size=batch_size,
            show_progress_bar=True
        )

    def generer_pour_chunks(self, fichier_chunks=config.CHUNKS_FILE,
                            fichier_sortie=config.EMBEDDINGS_FILE):
        """Génère les embeddings pour tous les chunks"""

        # Charger les chunks
        print(f" B- Chargement des chunks depuis {fichier_chunks}...")
        with open(fichier_chunks, 'r', encoding='utf-8') as f:
            chunks = yaml.safe_load(f)

        print(f" {len(chunks)} chunks à traiter")

        # Extraire les textes
        textes = [chunk['texte'] for chunk in chunks]

        # Générer les embeddings
        print(f" C- Génération des embeddings...")
        embeddings = self.generer_embeddings_batch(textes)

        # Sauvegarder
        print(f" D- Sauvegarde dans {fichier_sortie}...")
        Path(fichier_sortie).parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            fichier_sortie,
            embeddings=embeddings,
            chunks=chunks
        )

        print(f" {len(embeddings)} embeddings générés et sauvegardés")
        print(f"   Dimension: {embeddings.shape}")

        return embeddings, chunks


if __name__ == "__main__":
    generateur = GenerateurEmbeddings()
    embeddings, chunks = generateur.generer_pour_chunks()
