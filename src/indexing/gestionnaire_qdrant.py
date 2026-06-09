"""
Module de gestion de la base vectorielle Qdrant
"""

import os
import sys
import yaml
import numpy as np
from qdrant_client import QdrantClient
# Importation de QueryResponse pour la compatibilité
from qdrant_client.models import Distance, VectorParams, PointStruct
from dotenv import load_dotenv
from tqdm import tqdm
import uuid
from pathlib import Path

# Rendre le projet importable (src/ sur le path) quel que soit le CWD
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

load_dotenv()

class GestionnaireQdrant:
    def __init__(self):
        """Initialise la connexion à Qdrant"""
        self.host = os.getenv('QDRANT_HOST', 'localhost')
        self.port = int(os.getenv('QDRANT_PORT', 6333))
        self.collection_name = os.getenv('QDRANT_COLLECTION_NAME', 'github_docs')
        
        print(f"🔌 Connexion à Qdrant ({self.host}:{self.port})...")
        
        try:
            # On force le client synchrone standard
            self.client = QdrantClient(host=self.host, port=self.port)
            # Petit test de connexion immédiat
            self.client.get_collections()
            print("  Connexion réussie à Qdrant")
        except Exception as e:
            print(f"  Erreur de connexion à Qdrant: {e}")
            raise

    def creer_collection(self, dimension=384):
        """Crée la collection dans Qdrant"""
        try:
            self.client.delete_collection(collection_name=self.collection_name)
            print(f"  Collection '{self.collection_name}' supprimée")
        except:
            pass
        
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(
                size=dimension,
                distance=Distance.COSINE
            )
        )
        print(f"  Collection '{self.collection_name}' créée (dimension: {dimension})")

    def indexer_chunks(self, fichier_embeddings=config.EMBEDDINGS_FILE):
        """Indexe les chunks avec leurs embeddings dans Qdrant"""
        if not os.path.exists(fichier_embeddings):
            print(f"  Fichier introuvable: {fichier_embeddings}")
            return

        print(f"  Chargement des données depuis {fichier_embeddings}...")
        data = np.load(fichier_embeddings, allow_pickle=True)
        embeddings = data['embeddings']
        chunks = data['chunks'].tolist()
        
        dimension = embeddings.shape[1]
        self.creer_collection(dimension=dimension)
        
        points = []
        for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            point_id = str(uuid.uuid4())
            payload = {
                'texte': chunk.get('texte', ''),
                'nom_complet': chunk.get('metadonnees', {}).get('nom_complet', ''),
                'langage': chunk.get('metadonnees', {}).get('langage', ''),
                'url': chunk.get('metadonnees', {}).get('url', ''),
                'section_titre': chunk.get('metadonnees', {}).get('section_titre', ''),
                'source_file': chunk.get('metadonnees', {}).get('source_file', '')
            }
            
            points.append(PointStruct(
                id=point_id,
                vector=embedding.tolist(),
                payload=payload
            ))
        
        batch_size = 100
        print(f"  Indexation de {len(points)} points...")
        for i in tqdm(range(0, len(points), batch_size), desc="Upload Qdrant"):
            batch = points[i:i + batch_size]
            self.client.upsert(
                collection_name=self.collection_name,
                points=batch
            )
        print(f"  Indexation terminée.")

    def tester_recherche(self, requete="How to create a REST API?", top_k=3):
        """Teste la recherche avec gestion d'erreur sur la méthode search"""
        from sentence_transformers import SentenceTransformer

        # Contournement SSL optionnel + cache unifié (identique au générateur)
        config.configurer_ssl()
        cache_folder = str(config.MODELS_CACHE_DIR)

        print(f" 🔍 Recherche: '{requete}'")
        modele = SentenceTransformer(config.MODELE_EMBEDDINGS, cache_folder=cache_folder)
        query_vector = modele.encode(requete).tolist()
        
        try:
            # Tentative avec la méthode standard
            resultats = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=top_k
            )
        except AttributeError:
            # Si 'search' n'existe pas, on tente la nouvelle API 'query_points'
            print("  Méthode .search() introuvable, tentative avec .query_points()...")
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=top_k
            )
            resultats = response.points

        print(f"\n  Top {len(resultats)} résultats :")
        for i, hit in enumerate(resultats, 1):
            # Selon la méthode, l'objet hit peut varier, on harmonise :
            score = getattr(hit, 'score', 0)
            payload = getattr(hit, 'payload', {})
            print(f" {i}. [Score: {score:.4f}] {payload.get('section_titre', 'N/A')}")
            print(f"    Texte: {payload.get('texte', '')[:150]}...")

if __name__ == "__main__":
    gestionnaire = GestionnaireQdrant()
    # On peut tester directement la recherche si l'indexation a déjà réussi
    gestionnaire.tester_recherche()