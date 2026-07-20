"""Chargement des chunks et recherche sparse BM25."""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

import numpy as np
from rank_bm25 import BM25Okapi


def construire_index_bm25(chunks_file: str) -> Tuple[List[Dict], Optional[BM25Okapi]]:
    if not os.path.exists(chunks_file):
        print(f"   ⚠️  Chunks introuvables : {chunks_file}")
        return [], None
    with open(chunks_file, "r", encoding="utf-8") as f:
        chunks = json.load(f)
    corpus = [c.get("texte", "").lower().split() for c in chunks]
    return chunks, BM25Okapi(corpus)


def recherche_bm25(
    bm25_index: Optional[BM25Okapi],
    chunks_bruts: List[Dict],
    requete: str,
    top_k: int,
    passe_filtres,
    filtres: Optional[Dict] = None,
) -> List[Dict]:
    if bm25_index is None:
        return []
    tokens = requete.lower().split()
    scores = bm25_index.get_scores(tokens)
    score_max = scores.max() if scores.max() > 0 else 1.0
    scores_n = scores / score_max
    indices = np.argsort(scores_n)[::-1][: top_k * 3]

    documents = []
    for idx in indices:
        if scores_n[idx] <= 0:
            continue
        chunk = chunks_bruts[idx]
        doc = {
            "texte": chunk.get("texte", ""),
            "nom_complet": chunk.get("nom_complet", ""),
            "langage": chunk.get("langage", ""),
            "url": chunk.get("url", ""),
            "section_titre": chunk.get("section_titre", ""),
            "source_file": chunk.get("chemin_fichier", chunk.get("source_file", "")),
            "etoiles": chunk.get("etoiles", 0) or 0,
            "mis_a_jour_le": chunk.get("mis_a_jour_le", ""),
            "version": chunk.get("version", ""),
            "type_chunk": chunk.get("type_chunk", ""),
            "score_dense": 0.0,
            "score_bm25": float(scores_n[idx]),
            "score_final": 0.0,
            "score_confiance": 0.0,
        }
        if passe_filtres(doc, filtres):
            documents.append(doc)
        if len(documents) >= top_k:
            break
    return documents

