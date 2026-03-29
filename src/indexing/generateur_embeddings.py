"""
Module de génération des embeddings
"""

import os
import ssl
import yaml
from pathlib import Path
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
import numpy as np


class GenerateurEmbeddings:
    def __init__(self, nom_modele='sentence-transformers/all-MiniLM-L6-v2'):
        """
        Initialise le générateur d'embeddings
        
        Args:
            nom_modele: Nom du modèle d'embeddings à utiliser
        """
        print(f" A- Chargement du modèle {nom_modele}...")
        
        # FIX : Désactiver la vérification SSL (temporaire pour développement)
        import ssl
        ssl._create_default_https_context = ssl._create_unverified_context
        
        # Configurer le cache dans le projet
        os.environ['HF_HOME'] = str(Path(__file__).parent.parent.parent / 'cache_huggingface')
        os.environ['TRANSFORMERS_CACHE'] = str(Path(__file__).parent.parent.parent / 'cache_huggingface')
        
        # Charger le modèle
        try:
            self.modele = SentenceTransformer(nom_modele)
            self.dimension = self.modele.get_sentence_embedding_dimension()
            print(f" Modèle chargé (dimension: {self.dimension})")
        except Exception as e:
            print(f" Erreur lors du chargement du modèle: {e}")
            print(" Essai avec un chemin local...")
            
            # Fallback : essayer de charger depuis le cache local
            cache_dir = Path(__file__).parent.parent.parent / 'cache_huggingface'
            cache_dir.mkdir(parents=True, exist_ok=True)
            
            self.modele = SentenceTransformer(nom_modele, cache_folder=str(cache_dir))
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
    
    def generer_pour_chunks(self, fichier_chunks='data/processed/chunks/tous_chunks.yaml',
                           fichier_sortie='data/processed/chunks/chunks_avec_embeddings.npz'):
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