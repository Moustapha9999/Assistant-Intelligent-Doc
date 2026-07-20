"""Recherche dense Qdrant."""

from __future__ import annotations

from typing import Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels


def construire_filtre_qdrant(filtres: Optional[Dict]) -> Optional[qmodels.Filter]:
    if not filtres:
        return None
    must = []
    if filtres.get("langage") and filtres["langage"] != "Tous":
        must.append(
            qmodels.FieldCondition(
                key="langage",
                match=qmodels.MatchValue(value=filtres["langage"]),
            )
        )
    if filtres.get("repo"):
        must.append(
            qmodels.FieldCondition(
                key="nom_complet",
                match=qmodels.MatchValue(value=filtres["repo"]),
            )
        )
    if filtres.get("stars_min") is not None:
        must.append(
            qmodels.FieldCondition(
                key="etoiles",
                range=qmodels.Range(gte=int(filtres["stars_min"])),
            )
        )
    return qmodels.Filter(must=must) if must else None


def doc_from_payload(payload: dict, score_dense: float = 0.0) -> Dict:
    ligne = payload.get("ligne_debut")
    try:
        ligne_debut = int(ligne) if ligne not in (None, "") else None
    except (TypeError, ValueError):
        ligne_debut = None
    return {
        "texte": payload.get("texte", ""),
        "nom_complet": payload.get("nom_complet", ""),
        "langage": payload.get("langage", ""),
        "url": payload.get("url", ""),
        "section_titre": payload.get("section_titre", ""),
        "source_file": payload.get("source_file", ""),
        "ligne_debut": ligne_debut,
        "etoiles": payload.get("etoiles", 0) or 0,
        "mis_a_jour_le": payload.get("mis_a_jour_le", ""),
        "version": payload.get("version", ""),
        "type_chunk": payload.get("type_chunk", ""),
        "score_dense": float(score_dense),
        "score_bm25": 0.0,
        "score_final": 0.0,
        "score_confiance": 0.0,
    }


def recherche_dense(
    qdrant: QdrantClient,
    collection_name: str,
    encodeur,
    requete: str,
    top_k: int,
    score_threshold: float,
    filtres: Optional[Dict] = None,
) -> List[Dict]:
    vecteur = encodeur.encode(requete).tolist()
    qfilter = construire_filtre_qdrant(filtres)
    kwargs = {
        "collection_name": collection_name,
        "query_vector": vecteur,
        "limit": top_k,
        "score_threshold": score_threshold,
    }
    if qfilter is not None:
        kwargs["query_filter"] = qfilter
    try:
        resultats = qdrant.search(**kwargs)
    except AttributeError:
        response = qdrant.query_points(
            collection_name=collection_name,
            query=vecteur,
            limit=top_k,
            score_threshold=score_threshold,
            query_filter=qfilter,
        )
        resultats = response.points
    except Exception as e:
        if qfilter is not None:
            print(f"   ⚠️  Filtre Qdrant ignoré ({e})")
            kwargs.pop("query_filter", None)
            try:
                resultats = qdrant.search(**kwargs)
            except AttributeError:
                response = qdrant.query_points(
                    collection_name=collection_name,
                    query=vecteur,
                    limit=top_k,
                    score_threshold=score_threshold,
                )
                resultats = response.points
        else:
            raise

    return [
        doc_from_payload(getattr(hit, "payload", {}) or {}, float(getattr(hit, "score", 0)))
        for hit in resultats
    ]

