"""
Module de gestion de la base vectorielle Qdrant
— lit configs/qdrant_config.yaml
— métadonnées riches + index payload
— création sûre (pas de delete silencieux sans confirmation)
"""

import os
import sys
import uuid
from pathlib import Path

import numpy as np
import yaml
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.models import Distance, PointStruct, VectorParams
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config

load_dotenv()


class GestionnaireQdrant:
    def __init__(self):
        """Initialise la connexion à Qdrant et charge la config YAML."""
        self.cfg = config.charger_qdrant_config()
        self.host = os.getenv("QDRANT_HOST", "localhost")
        self.port = int(os.getenv("QDRANT_PORT", 6333))
        self.collection_name = os.getenv(
            "QDRANT_COLLECTION_NAME",
            self.cfg.get("collection", {}).get("name", "github_docs"),
        )
        vp = self.cfg.get("collection", {}).get("vector_params", {})
        self.dimension = int(vp.get("size", 384))
        dist = str(vp.get("distance", "COSINE")).upper()
        self.distance = Distance.COSINE if dist == "COSINE" else Distance.COSINE
        self.batch_size = int(self.cfg.get("indexing", {}).get("batch_size", 100))

        print(f"🔌 Connexion à Qdrant ({self.host}:{self.port})...")
        try:
            self.client = QdrantClient(host=self.host, port=self.port)
            self.client.get_collections()
            print("  Connexion réussie à Qdrant")
        except Exception as e:
            print(f"  Erreur de connexion à Qdrant: {e}")
            raise

    def _payload_indexes(self):
        """Crée les index payload pour filtres natifs Qdrant."""
        champs = [
            ("langage", qmodels.PayloadSchemaType.KEYWORD),
            ("nom_complet", qmodels.PayloadSchemaType.KEYWORD),
            ("etoiles", qmodels.PayloadSchemaType.INTEGER),
            ("mis_a_jour_le", qmodels.PayloadSchemaType.KEYWORD),
            ("version", qmodels.PayloadSchemaType.KEYWORD),
            ("type_chunk", qmodels.PayloadSchemaType.KEYWORD),
        ]
        for nom, schema in champs:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=nom,
                    field_schema=schema,
                )
            except Exception:
                # Index déjà présent
                pass

    def creer_collection(self, dimension=None, recreer: bool = False):
        """
        Crée la collection. Si elle existe déjà :
        - recreer=False → réutilise (pas de delete)
        - recreer=True  → supprimer puis recréer (explicite)
        """
        dimension = dimension or self.dimension
        existe = False
        try:
            self.client.get_collection(self.collection_name)
            existe = True
        except Exception:
            existe = False

        if existe and not recreer:
            print(f"  Collection '{self.collection_name}' déjà présente — réutilisation")
            self._payload_indexes()
            return

        if existe and recreer:
            print(f"  Recréation demandée — suppression de '{self.collection_name}'...")
            self.client.delete_collection(collection_name=self.collection_name)

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=dimension, distance=self.distance),
        )
        print(f"  Collection '{self.collection_name}' créée (dimension: {dimension})")
        self._payload_indexes()

    @staticmethod
    def _extraire_payload(chunk: dict) -> dict:
        """Construit un payload riche à partir d'un chunk."""
        meta = chunk.get("metadonnees") if isinstance(chunk.get("metadonnees"), dict) else {}

        def g(*cles, default=""):
            for c in cles:
                if chunk.get(c) not in (None, ""):
                    return chunk.get(c)
                if meta.get(c) not in (None, ""):
                    return meta.get(c)
            return default

        etoiles = g("etoiles", "stars", default=0)
        try:
            etoiles = int(etoiles or 0)
        except (TypeError, ValueError):
            etoiles = 0

        ligne = g("ligne_debut", default="")
        try:
            ligne_debut = int(ligne) if ligne not in ("", None) else None
        except (TypeError, ValueError):
            ligne_debut = None

        return {
            "texte": chunk.get("texte", ""),
            "nom_complet": g("nom_complet"),
            "langage": g("langage"),
            "url": g("url"),
            "section_titre": g("section_titre"),
            "source_file": g("chemin_fichier", "source_file"),
            "ligne_debut": ligne_debut,
            "type_chunk": g("type_chunk", default="markdown"),
            "etoiles": etoiles,
            "mis_a_jour_le": str(g("mis_a_jour_le", "updated_at", default="")),
            "version": str(g("version", default="")),
            "licence": str(g("licence", "license", default="")),
        }

    def indexer_chunks(
        self,
        fichier_embeddings=config.EMBEDDINGS_FILE,
        recreer: bool = True,
    ):
        """Indexe les chunks avec leurs embeddings dans Qdrant."""
        if not os.path.exists(fichier_embeddings):
            print(f"  Fichier introuvable: {fichier_embeddings}")
            return

        print(f"  Chargement des données depuis {fichier_embeddings}...")
        data = np.load(fichier_embeddings, allow_pickle=True)
        embeddings = data["embeddings"]
        chunks = data["chunks"].tolist()

        dimension = embeddings.shape[1]
        self.creer_collection(dimension=dimension, recreer=recreer)

        points = []
        for chunk, embedding in zip(chunks, embeddings):
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding.tolist(),
                    payload=self._extraire_payload(chunk),
                )
            )

        print(f"  Indexation de {len(points)} points...")
        for i in tqdm(range(0, len(points), self.batch_size), desc="Upload Qdrant"):
            batch = points[i : i + self.batch_size]
            self.client.upsert(collection_name=self.collection_name, points=batch)
        print("  Indexation terminée.")

        if self.cfg.get("indexing", {}).get("optimize_after"):
            try:
                # API optionnelle selon version client
                self.client.update_collection(
                    collection_name=self.collection_name,
                    optimizer_config=qmodels.OptimizersConfigDiff(indexing_threshold=10000),
                )
            except Exception:
                pass

    def tester_recherche(self, requete="How to create a REST API?", top_k=3):
        """Teste la recherche dense."""
        from sentence_transformers import SentenceTransformer

        config.configurer_ssl()
        cache_folder = str(config.MODELS_CACHE_DIR)
        seuil = float(self.cfg.get("search", {}).get("score_threshold", 0.35))

        print(f" 🔍 Recherche: '{requete}'")
        modele = SentenceTransformer(config.MODELE_EMBEDDINGS, cache_folder=cache_folder)
        query_vector = modele.encode(requete).tolist()

        try:
            resultats = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=top_k,
                score_threshold=seuil,
            )
        except AttributeError:
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=top_k,
                score_threshold=seuil,
            )
            resultats = response.points

        print(f"\n  Top {len(resultats)} résultats :")
        for i, hit in enumerate(resultats, 1):
            score = getattr(hit, "score", 0)
            payload = getattr(hit, "payload", {})
            print(f" {i}. [Score: {score:.4f}] {payload.get('section_titre', 'N/A')}")
            print(f"    Texte: {payload.get('texte', '')[:150]}...")


if __name__ == "__main__":
    gestionnaire = GestionnaireQdrant()
    gestionnaire.tester_recherche()
