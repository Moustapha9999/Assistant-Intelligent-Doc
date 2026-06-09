"""
Module de retrieval hybride : Dense (Qdrant) + Sparse (BM25) + Reranking (Cross-encoder)
"""

import os
import ssl
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

# Qdrant
from qdrant_client import QdrantClient

# Embeddings
from sentence_transformers import SentenceTransformer, CrossEncoder

# BM25
from rank_bm25 import BM25Okapi

# YAML pour charger les chunks bruts (BM25)
import yaml

load_dotenv()


class RetrievalHybride:
    """
    Moteur de recherche hybride combinant :
    - Recherche dense  : similarité vectorielle via Qdrant
    - Recherche sparse : BM25 sur les textes bruts
    - Reranking        : Cross-encoder pour affiner le top-K
    """

    def __init__(self):
        """Initialise les composants du retrieval hybride"""

        # ── Config ──────────────────────────────────────────────────
        self.qdrant_host       = os.getenv("QDRANT_HOST", "localhost")
        self.qdrant_port       = int(os.getenv("QDRANT_PORT", 6333))
        self.collection_name   = os.getenv("QDRANT_COLLECTION_NAME", "github_docs")
        self.embedding_model   = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

        # Chemins
        self.base_dir          = Path(__file__).resolve().parent.parent
        self.cache_folder      = str(self.base_dir / "models_cache")
        self.chunks_file = str(
        self.base_dir.parent / "data" / "processed" / "chunks" / "tous_chunks.yaml"
        )

        # ── SSL fix (développement local) ───────────────────────────
        ssl._create_default_https_context = ssl._create_unverified_context

        # ── Connexion Qdrant ─────────────────────────────────────────
        print("🔌 Connexion à Qdrant...")
        self.qdrant = QdrantClient(host=self.qdrant_host, port=self.qdrant_port)
        print(f"   ✅ Qdrant connecté ({self.qdrant_host}:{self.qdrant_port})")

        # ── Modèle d'embeddings ──────────────────────────────────────
        print(f"📦 Chargement du modèle d'embeddings ({self.embedding_model})...")
        self.encodeur = SentenceTransformer(
            self.embedding_model,
            cache_folder=self.cache_folder
        )
        print("   ✅ Modèle d'embeddings chargé")

        # ── Cross-encoder (reranking) ────────────────────────────────
        print("📦 Chargement du cross-encoder...")
        self.cross_encoder = CrossEncoder(
            "cross-encoder/ms-marco-MiniLM-L-6-v2",
            max_length=512,
            device="cpu"
        )
        print("   ✅ Cross-encoder chargé")

        # ── Index BM25 ───────────────────────────────────────────────
        print("📑 Construction de l'index BM25...")
        self.chunks_bruts, self.bm25_index = self._construire_index_bm25()
        print(f"   ✅ Index BM25 construit ({len(self.chunks_bruts)} documents)")

    # ────────────────────────────────────────────────────────────────
    # CONSTRUCTION INDEX BM25
    # ────────────────────────────────────────────────────────────────

    def _construire_index_bm25(self):
        """
        Charge les chunks depuis le fichier YAML et construit l'index BM25.
        Retourne (liste_chunks, index_bm25).
        """
        if not os.path.exists(self.chunks_file):
            print(f"   ⚠️  Fichier chunks introuvable : {self.chunks_file}")
            return [], None

        with open(self.chunks_file, "r", encoding="utf-8") as f:
            chunks = yaml.safe_load(f)

        # Tokenisation simple : minuscules + split
        corpus_tokenise = [
            chunk.get("texte", "").lower().split()
            for chunk in chunks
        ]
        index = BM25Okapi(corpus_tokenise)
        return chunks, index

    # ────────────────────────────────────────────────────────────────
    # RECHERCHE DENSE (Qdrant)
    # ────────────────────────────────────────────────────────────────

    def _recherche_dense(self, requete: str, top_k: int = 20) -> List[Dict]:
        """
        Recherche par similarité vectorielle dans Qdrant.
        Retourne une liste de documents avec scores normalisés [0-1].
        """
        vecteur = self.encodeur.encode(requete).tolist()

        try:
            resultats = self.qdrant.search(
                collection_name=self.collection_name,
                query_vector=vecteur,
                limit=top_k
            )
        except AttributeError:
            response = self.qdrant.query_points(
                collection_name=self.collection_name,
                query=vecteur,
                limit=top_k
            )
            resultats = response.points

        documents = []
        for hit in resultats:
            payload = getattr(hit, "payload", {})
            documents.append({
                "texte"         : payload.get("texte", ""),
                "nom_complet"   : payload.get("nom_complet", ""),
                "langage"       : payload.get("langage", ""),
                "url"           : payload.get("url", ""),
                "section_titre" : payload.get("section_titre", ""),
                "source_file"   : payload.get("source_file", ""),
                "score_dense"   : float(getattr(hit, "score", 0)),
                "score_bm25"    : 0.0,
                "score_final"   : 0.0,
            })
        return documents

    # ────────────────────────────────────────────────────────────────
    # RECHERCHE SPARSE (BM25)
    # ────────────────────────────────────────────────────────────────

    def _recherche_bm25(self, requete: str, top_k: int = 20) -> List[Dict]:
        """
        Recherche BM25 sur les chunks bruts.
        Retourne une liste de documents avec scores normalisés [0-1].
        """
        if self.bm25_index is None:
            return []

        tokens = requete.lower().split()
        scores = self.bm25_index.get_scores(tokens)

        # Normalisation des scores BM25 entre 0 et 1
        score_max = scores.max() if scores.max() > 0 else 1.0
        scores_normalises = scores / score_max

        # Récupérer les top_k indices
        indices_top = np.argsort(scores_normalises)[::-1][:top_k]

        documents = []
        for idx in indices_top:
            if scores_normalises[idx] <= 0:
                continue
            chunk = self.chunks_bruts[idx]
            meta  = chunk.get("metadonnees", {})
            documents.append({
                "texte"         : chunk.get("texte", ""),
                "nom_complet"   : meta.get("nom_complet", ""),
                "langage"       : meta.get("langage", ""),
                "url"           : meta.get("url", ""),
                "section_titre" : meta.get("section_titre", ""),
                "source_file"   : meta.get("source_file", ""),
                "score_dense"   : 0.0,
                "score_bm25"    : float(scores_normalises[idx]),
                "score_final"   : 0.0,
            })
        return documents

    # ────────────────────────────────────────────────────────────────
    # FUSION RRF (Reciprocal Rank Fusion)
    # ────────────────────────────────────────────────────────────────

    def _fusionner_rrf(
        self,
        docs_dense : List[Dict],
        docs_bm25  : List[Dict],
        k          : int = 60,
        poids_dense: float = 0.6,
        poids_bm25 : float = 0.4,
    ) -> List[Dict]:
        """
        Fusionne les résultats dense et BM25 via Reciprocal Rank Fusion.
        score_rrf = Σ poids_i / (k + rang_i)
        """
        scores_rrf: Dict[str, float] = {}
        docs_map  : Dict[str, Dict]  = {}

        # Clé unique = texte tronqué à 200 chars (évite les doublons)
        def cle(doc: Dict) -> str:
            return doc["texte"][:200]

        # Contribution dense
        for rang, doc in enumerate(docs_dense, start=1):
            c = cle(doc)
            scores_rrf[c] = scores_rrf.get(c, 0) + poids_dense / (k + rang)
            if c not in docs_map:
                docs_map[c] = doc
            else:
                docs_map[c]["score_dense"] = doc["score_dense"]

        # Contribution BM25
        for rang, doc in enumerate(docs_bm25, start=1):
            c = cle(doc)
            scores_rrf[c] = scores_rrf.get(c, 0) + poids_bm25 / (k + rang)
            if c not in docs_map:
                docs_map[c] = doc
            else:
                docs_map[c]["score_bm25"] = doc["score_bm25"]

        # Tri par score RRF décroissant
        for c, score in scores_rrf.items():
            docs_map[c]["score_final"] = score

        fusionnes = sorted(docs_map.values(), key=lambda d: d["score_final"], reverse=True)
        return fusionnes

    # ────────────────────────────────────────────────────────────────
    # RERANKING (Cross-encoder)
    # ────────────────────────────────────────────────────────────────

    def _reranker(self, requete: str, documents: List[Dict], top_k: int = 5) -> List[Dict]:
        """
        Affine le classement avec un cross-encoder question/document.
        Retourne les top_k documents reclassés.
        """
        if not documents:
            return []

        paires = [(requete, doc["texte"][:512]) for doc in documents]
        scores_rerank = self.cross_encoder.predict(paires)

        for doc, score in zip(documents, scores_rerank):
            doc["score_rerank"] = float(score)

        reclasses = sorted(documents, key=lambda d: d.get("score_rerank", 0), reverse=True)
        return reclasses[:top_k]

    # ────────────────────────────────────────────────────────────────
    # POINT D'ENTRÉE PRINCIPAL
    # ────────────────────────────────────────────────────────────────

    def rechercher(
        self,
        requete         : str,
        top_k_retrieval : int = 20,
        top_k_final     : int = 5,
        filtres         : Optional[Dict] = None,
    ) -> List[Dict]:
        """
        Pipeline complet de recherche hybride.

        Args:
            requete          : Question de l'utilisateur (en français ou anglais)
            top_k_retrieval  : Nombre de documents récupérés par chaque moteur
            top_k_final      : Nombre de documents renvoyés après reranking
            filtres          : Filtres optionnels ex: {"langage": "Python"}

        Returns:
            Liste de documents classés par pertinence avec métadonnées et scores
        """
        print(f"\n🔍 Recherche hybride : « {requete} »")

        # 1. Recherche dense
        print("   → Recherche dense (Qdrant)...")
        docs_dense = self._recherche_dense(requete, top_k=top_k_retrieval)
        print(f"      {len(docs_dense)} résultats")

        # 2. Recherche sparse BM25
        print("   → Recherche sparse (BM25)...")
        docs_bm25 = self._recherche_bm25(requete, top_k=top_k_retrieval)
        print(f"      {len(docs_bm25)} résultats")

        # 3. Fusion RRF
        print("   → Fusion RRF...")
        docs_fusionnes = self._fusionner_rrf(docs_dense, docs_bm25)
        print(f"      {len(docs_fusionnes)} documents uniques après fusion")

        # 4. Filtre optionnel sur langage
        if filtres and "langage" in filtres:
            lang = filtres["langage"].lower()
            docs_fusionnes = [
                d for d in docs_fusionnes
                if d.get("langage", "").lower() == lang
            ]
            print(f"   → Filtre langage='{lang}' : {len(docs_fusionnes)} documents")

        # 5. Reranking cross-encoder
        print("   → Reranking (cross-encoder)...")
        docs_finaux = self._reranker(requete, docs_fusionnes, top_k=top_k_final)
        print(f"      ✅ {len(docs_finaux)} documents finaux")

        return docs_finaux

    # ────────────────────────────────────────────────────────────────
    # UTILITAIRE : AFFICHAGE DES RÉSULTATS
    # ────────────────────────────────────────────────────────────────

    def afficher_resultats(self, resultats: List[Dict]) -> None:
        """Affiche les résultats de façon lisible dans le terminal"""
        if not resultats:
            print("   ⚠️  Aucun résultat trouvé.")
            return

        print(f"\n📋 {len(resultats)} résultat(s) :\n")
        for i, doc in enumerate(resultats, 1):
            print(f"  {'─' * 60}")
            print(f"  [{i}] {doc.get('section_titre', 'Sans titre')}")
            print(f"       Repo    : {doc.get('nom_complet', 'N/A')}")
            print(f"       Langage : {doc.get('langage', 'N/A')}")
            print(f"       URL     : {doc.get('url', 'N/A')}")
            print(f"       Scores  → dense={doc.get('score_dense', 0):.3f} "
                  f"| bm25={doc.get('score_bm25', 0):.3f} "
                  f"| rerank={doc.get('score_rerank', 0):.3f}")
            print(f"       Extrait : {doc.get('texte', '')[:200]}...")
        print(f"  {'─' * 60}\n")


# ────────────────────────────────────────────────────────────────────
# TEST RAPIDE
# ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    moteur = RetrievalHybride()

    requetes_test = [
        "Comment créer une API REST avec Python ?",
        "How to implement authentication with JWT?",
        "gestion des erreurs en JavaScript",
    ]

    for requete in requetes_test:
        resultats = moteur.rechercher(requete, top_k_retrieval=20, top_k_final=5)
        moteur.afficher_resultats(resultats)