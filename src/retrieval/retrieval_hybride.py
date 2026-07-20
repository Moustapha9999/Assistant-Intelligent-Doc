"""
Module de retrieval hybride : Dense (Qdrant) + Sparse (BM25) + Reranking (Cross-encoder)

Améliorations :
- lit configs/qdrant_config.yaml
- SSL optionnel uniquement
- filtres Qdrant natifs
- score_threshold dense
- ranking par fraîcheur
- boosts lexicales modérés
- score de confiance + abstention
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from sentence_transformers import CrossEncoder, SentenceTransformer
from retrieval.bm25 import construire_index_bm25, recherche_bm25
from retrieval.contexte import compresser_documents
from retrieval.dedup import booster_lexical, dedupliquer_documents, injecter_hits_termes
from retrieval.dense import construire_filtre_qdrant, doc_from_payload, recherche_dense
from retrieval.fusion import (
    appliquer_fraicheur,
    classer_par_theme,
    fusionner_rrf,
    normaliser_confiance,
    parse_date,
    reranker_documents,
)
from retrieval.query_rewriter import EXPANSIONS_REQUETE, fusionner_requetes, reecrire_requete

import config

load_dotenv()

BOOST_TERMES = {
    "flask": ["flask", "@app.route", "jsonify"],
    "django": ["django", "select_related", "prefetch_related"],
    "react": ["react", "usestate", "useeffect", "hooks"],
    "jwt": ["jwt", "pyjwt", "bearer"],
    "fastapi": ["fastapi", "uvicorn", "pydantic"],
    "docker": ["docker", "dockerfile", "compose"],
    "fichier": ["open(", "with open", "pathlib"],
}

REPO_PREFERENCE = {
    "flask": ["pallets/flask"],
    "django": ["django/django"],
    "react": ["facebook/react"],
    "jwt": ["jpadilla/pyjwt"],
    "fastapi": ["tiangolo/fastapi", "fastapi/fastapi"],
    "docker": ["docker/docs", "compose-spec"],
}

BRUIT_REPOS = ("the-art-of-command-line", "nodebestpractices", "awesome-", "how-to-write")

TERMES_FORCES = {
    "flask": ["@app.route", "jsonify", "Flask("],
    "django": ["select_related", "prefetch_related"],
    "fastapi": ["FastAPI", "@app.get", "@app.post"],
    "react": ["useState", "useEffect"],
    "jwt": ["jwt.encode", "jwt.decode", "PyJWT"],
    "docker": ["Dockerfile", "docker compose"],
}


def _normaliser_confiance(score_rerank: float, score_dense: float = 0.0) -> float:
    """Wrapper compatibilité tests/imports existants."""
    return normaliser_confiance(score_rerank, score_dense)


def _parse_date(valeur: Any) -> Optional[datetime]:
    return parse_date(valeur)


class RetrievalHybride:
    """Dense + BM25 + RRF + Cross-encoder + filtres + fraîcheur."""

    def __init__(self):
        self.cfg = config.charger_qdrant_config()
        search_cfg = self.cfg.get("search", {})
        self.score_threshold = float(search_cfg.get("score_threshold", 0.35))
        self.abstention_threshold = float(search_cfg.get("abstention_threshold", 0.12))
        self.freshness_weight = float(search_cfg.get("freshness_weight", 0.08))
        self.default_limit = int(search_cfg.get("default_limit", 5))

        self.qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        self.qdrant_port = int(os.getenv("QDRANT_PORT", 6333))
        self.collection_name = os.getenv(
            "QDRANT_COLLECTION_NAME",
            self.cfg.get("collection", {}).get("name", "github_docs"),
        )
        self.embedding_model = config.MODELE_EMBEDDINGS
        self.chunks_file = str(config.CHUNKS_FILE)
        self.cache_folder = str(config.MODELS_CACHE_DIR)

        config.configurer_ssl()

        print("🔌 Connexion à Qdrant...")
        self.qdrant = QdrantClient(host=self.qdrant_host, port=self.qdrant_port)
        print(f"   ✅ Qdrant connecté ({self.qdrant_host}:{self.qdrant_port})")

        print(f"📦 Chargement embeddings ({self.embedding_model})...")
        Path(self.cache_folder).mkdir(parents=True, exist_ok=True)
        self.encodeur = SentenceTransformer(self.embedding_model, cache_folder=self.cache_folder)
        print("   ✅ Embeddings chargés")

        print("📦 Chargement cross-encoder...")
        self.cross_encoder = CrossEncoder(config.MODELE_RERANKER, max_length=512, device="cpu")
        print("   ✅ Cross-encoder chargé")

        print("📑 Construction index BM25...")
        self.chunks_bruts, self.bm25_index = self._construire_index_bm25()
        print(f"   ✅ BM25 ({len(self.chunks_bruts)} docs)")

    def _construire_index_bm25(self):
        return construire_index_bm25(self.chunks_file)

    def _construire_filtre_qdrant(self, filtres: Optional[Dict]):
        return construire_filtre_qdrant(filtres)

    def _doc_from_payload(self, payload: dict, score_dense: float = 0.0) -> Dict:
        return doc_from_payload(payload, score_dense)

    def _recherche_dense(self, requete: str, top_k: int = 20, filtres: Optional[Dict] = None) -> List[Dict]:
        return recherche_dense(
            qdrant=self.qdrant,
            collection_name=self.collection_name,
            encodeur=self.encodeur,
            requete=requete,
            top_k=top_k,
            score_threshold=self.score_threshold,
            filtres=filtres,
        )

    def _recherche_bm25(self, requete: str, top_k: int = 20, filtres: Optional[Dict] = None) -> List[Dict]:
        return recherche_bm25(
            bm25_index=self.bm25_index,
            chunks_bruts=self.chunks_bruts,
            requete=requete,
            top_k=top_k,
            passe_filtres=self._passe_filtres,
            filtres=filtres,
        )

    def _passe_filtres(self, doc: Dict, filtres: Optional[Dict]) -> bool:
        if not filtres:
            return True
        if filtres.get("langage") and filtres["langage"] != "Tous":
            if (doc.get("langage") or "").lower() != filtres["langage"].lower():
                return False
        if filtres.get("repo"):
            if filtres["repo"].lower() not in (doc.get("nom_complet") or "").lower():
                return False
        if filtres.get("stars_min") is not None:
            try:
                if int(doc.get("etoiles") or 0) < int(filtres["stars_min"]):
                    return False
            except (TypeError, ValueError):
                return False
        if filtres.get("date_min"):
            dt = _parse_date(doc.get("mis_a_jour_le"))
            dt_min = _parse_date(filtres["date_min"])
            if dt_min and (dt is None or dt < dt_min):
                return False
        return True

    def _fusionner_rrf(
        self,
        docs_dense: List[Dict],
        docs_bm25: List[Dict],
        k: int = 60,
        poids_dense: float = 0.6,
        poids_bm25: float = 0.4,
    ) -> List[Dict]:
        return fusionner_rrf(docs_dense, docs_bm25, k=k, poids_dense=poids_dense, poids_bm25=poids_bm25)

    def _reranker(self, requete: str, documents: List[Dict], top_k: int = 5) -> List[Dict]:
        return reranker_documents(self.cross_encoder, requete, documents, top_k=top_k)

    def _enrichir_requete(self, requete: str) -> str:
        info = reecrire_requete(requete, EXPANSIONS_REQUETE)
        return fusionner_requetes(info.reecrite, info.variantes)

    def _reecrire_requete(self, requete: str):
        return reecrire_requete(requete, EXPANSIONS_REQUETE)

    def _booster_lexical(self, requete: str, documents: List[Dict]) -> List[Dict]:
        return booster_lexical(
            requete=requete,
            documents=documents,
            boost_termes=BOOST_TERMES,
            repo_preference=REPO_PREFERENCE,
            bruit_repos=BRUIT_REPOS,
        )

    def _appliquer_fraicheur(self, documents: List[Dict]) -> List[Dict]:
        return appliquer_fraicheur(documents, self.freshness_weight)

    def _injecter_hits_termes(self, requete: str, documents: List[Dict], max_inject: int = 8) -> List[Dict]:
        return injecter_hits_termes(
            requete=requete,
            documents=documents,
            chunks_bruts=self.chunks_bruts,
            termes_forces=TERMES_FORCES,
            max_inject=max_inject,
        )

    def doit_sabstenir(self, documents: List[Dict]) -> bool:
        """True si la confiance du meilleur doc est sous le seuil."""
        if not documents:
            return True
        best = max(float(d.get("score_confiance") or 0) for d in documents)
        return best < self.abstention_threshold

    def rechercher(
        self,
        requete: str,
        top_k_retrieval: int = 20,
        top_k_final: int = 5,
        filtres: Optional[Dict] = None,
        avec_rerank: bool = True,
        mode: str = "hybride",  # dense | bm25 | hybride
    ) -> List[Dict]:
        print(f"\n🔍 Recherche ({mode}) : « {requete} »")
        info_requete = self._reecrire_requete(requete)
        requete_recherche = fusionner_requetes(info_requete.reecrite, info_requete.variantes)
        if info_requete.reecrite != requete:
            print(f"   ↔ Rewrite ({info_requete.intention}) : « {info_requete.reecrite[:120]} »")
        top_k_final = top_k_final or self.default_limit

        docs_dense, docs_bm25 = [], []
        if mode in ("dense", "hybride"):
            print("   → Dense (Qdrant)...")
            docs_dense = self._recherche_dense(requete_recherche, top_k=top_k_retrieval, filtres=filtres)
            print(f"      {len(docs_dense)} résultats")
        if mode in ("bm25", "hybride"):
            print("   → BM25...")
            docs_bm25 = self._recherche_bm25(requete_recherche, top_k=top_k_retrieval, filtres=filtres)
            print(f"      {len(docs_bm25)} résultats")

        if mode == "dense":
            docs_fusionnes = docs_dense
        elif mode == "bm25":
            docs_fusionnes = docs_bm25
        else:
            docs_fusionnes = self._fusionner_rrf(docs_dense, docs_bm25)

        # Filtres complémentaires (date / repo partiel) côté Python
        if filtres:
            docs_fusionnes = [d for d in docs_fusionnes if self._passe_filtres(d, filtres)]

        docs_fusionnes = dedupliquer_documents(docs_fusionnes)
        docs_fusionnes = self._injecter_hits_termes(requete, docs_fusionnes)

        if avec_rerank:
            print("   → Reranking...")
            candidats = self._reranker(requete_recherche, docs_fusionnes, top_k=max(top_k_final * 4, 20))
            candidats = self._booster_lexical(requete, candidats)
            candidats = self._appliquer_fraicheur(candidats)
        else:
            candidats = docs_fusionnes
            for d in candidats:
                d["score_confiance"] = _normaliser_confiance(
                    d.get("score_final", 0) * 10, d.get("score_dense", 0)
                )

        print("   → Classement thématique...")
        candidats = classer_par_theme(
            candidats,
            themes_requete=info_requete.themes,
            top_k=max(top_k_final * 2, top_k_final),
            diversifier=True,
        )
        docs_finaux = compresser_documents(
            candidats,
            max_docs=top_k_final,
            max_chars=900,
            requete=requete,
            resumer=True,
            diversifier_themes=True,
        )
        for d in docs_finaux:
            d["score_confiance"] = round(float(d.get("score_confiance") or 0), 3)
            d["requete_reecrite"] = info_requete.reecrite
            d["intention_requete"] = info_requete.intention
        print(f"      ✅ {len(docs_finaux)} documents finaux (thèmes={[d.get('theme') for d in docs_finaux]})")
        return docs_finaux

    def afficher_resultats(self, resultats: List[Dict]) -> None:
        if not resultats:
            print("   ⚠️  Aucun résultat.")
            return
        for i, doc in enumerate(resultats, 1):
            print(f"  [{i}] {doc.get('section_titre', 'Sans titre')}")
            print(f"       Repo={doc.get('nom_complet')} conf={doc.get('score_confiance', 0):.2f}")


if __name__ == "__main__":
    moteur = RetrievalHybride()
    for q in ["Comment créer une API REST avec FastAPI ?", "JWT authentication Python"]:
        res = moteur.rechercher(q)
        moteur.afficher_resultats(res)
        print("Abstention?", moteur.doit_sabstenir(res))
