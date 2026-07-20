"""Fusion, reranking, classement thématique et scores de confiance."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from retrieval.contexte import THEME_MOTIFS, detecter_theme_doc


def normaliser_confiance(score_rerank: float, score_dense: float = 0.0) -> float:
    try:
        s = 1.0 / (1.0 + np.exp(-float(score_rerank) / 3.0))
    except Exception:
        s = 0.0
    d = max(0.0, min(1.0, float(score_dense or 0.0)))
    return float(0.7 * s + 0.3 * d)


def parse_date(valeur: Any) -> Optional[datetime]:
    if not valeur:
        return None
    if isinstance(valeur, datetime):
        return valeur if valeur.tzinfo else valeur.replace(tzinfo=timezone.utc)
    texte = str(valeur).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(texte.replace("+00:00", "Z").replace("Z", ""), fmt.replace("%z", "").replace("Z", ""))
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(texte.replace("Z", "+00:00"))
    except ValueError:
        return None


def fusionner_rrf(
    docs_dense: List[Dict],
    docs_bm25: List[Dict],
    k: int = 60,
    poids_dense: float = 0.6,
    poids_bm25: float = 0.4,
) -> List[Dict]:
    scores_rrf: Dict[str, float] = {}
    docs_map: Dict[str, Dict] = {}

    def cle(doc: Dict) -> str:
        return doc["texte"][:200]

    for rang, doc in enumerate(docs_dense, start=1):
        c = cle(doc)
        scores_rrf[c] = scores_rrf.get(c, 0) + poids_dense / (k + rang)
        docs_map.setdefault(c, doc)
        docs_map[c]["score_dense"] = max(docs_map[c].get("score_dense", 0), doc.get("score_dense", 0))

    for rang, doc in enumerate(docs_bm25, start=1):
        c = cle(doc)
        scores_rrf[c] = scores_rrf.get(c, 0) + poids_bm25 / (k + rang)
        if c not in docs_map:
            docs_map[c] = doc
        else:
            docs_map[c]["score_bm25"] = doc["score_bm25"]

    for c, score in scores_rrf.items():
        docs_map[c]["score_final"] = score
    return sorted(docs_map.values(), key=lambda d: d["score_final"], reverse=True)


def reranker_documents(cross_encoder, requete: str, documents: List[Dict], top_k: int = 5) -> List[Dict]:
    if not documents:
        return []
    paires = [(requete, doc["texte"][:512]) for doc in documents]
    scores = cross_encoder.predict(paires)
    for doc, score in zip(documents, scores):
        doc["score_rerank"] = float(score)
        doc["score_confiance"] = normaliser_confiance(float(score), doc.get("score_dense", 0))
    return sorted(documents, key=lambda d: d.get("score_rerank", 0), reverse=True)[:top_k]


def appliquer_fraicheur(documents: List[Dict], freshness_weight: float) -> List[Dict]:
    if not documents or freshness_weight <= 0:
        return documents
    now = datetime.now(timezone.utc)
    for doc in documents:
        dt = parse_date(doc.get("mis_a_jour_le"))
        if dt is None:
            continue
        age_jours = max(0, (now - dt).days)
        bonus = freshness_weight * max(0.0, 1.0 - age_jours / 730.0)
        doc["score_rerank"] = float(doc.get("score_rerank", 0)) + bonus
        doc["boost_fraicheur"] = bonus
        doc["score_confiance"] = normaliser_confiance(
            doc.get("score_rerank", 0), doc.get("score_dense", 0)
        )
    return sorted(documents, key=lambda d: d.get("score_rerank", 0), reverse=True)


def _score_doc(doc: Dict) -> float:
    return float(
        doc.get("score_rerank")
        or doc.get("score_confiance")
        or doc.get("score_final")
        or doc.get("score_dense")
        or 0.0
    )


def annoter_themes(documents: List[Dict], themes_requete: Optional[Sequence[str]] = None) -> List[Dict]:
    """Ajoute `theme` + bonus si le thème du doc matche la requête."""
    themes_req = {t.lower() for t in (themes_requete or [])}
    for doc in documents:
        theme = detecter_theme_doc(doc)
        doc["theme"] = theme
        bonus = 0.0
        if theme in themes_req:
            bonus += 0.18
        # Match partiel via motifs connus
        blob = f"{doc.get('nom_complet', '')} {doc.get('section_titre', '')}".lower()
        for t in themes_req:
            if t and t in blob:
                bonus += 0.05
                break
        if bonus:
            doc["score_rerank"] = float(doc.get("score_rerank", 0)) + bonus
            doc["boost_theme"] = bonus
            doc["score_confiance"] = normaliser_confiance(
                doc.get("score_rerank", 0), doc.get("score_dense", 0)
            )
        else:
            doc.setdefault("boost_theme", 0.0)
    return documents


def classer_par_theme(
    documents: List[Dict],
    themes_requete: Optional[Sequence[str]] = None,
    top_k: Optional[int] = None,
    diversifier: bool = True,
) -> List[Dict]:
    """
    Classement final par pertinence + alignement thématique.
    Si diversifier=True, alterne les thèmes pour enrichir le contexte LLM.
    """
    if not documents:
        return []

    docs = annoter_themes([dict(d) for d in documents], themes_requete)
    docs = sorted(docs, key=_score_doc, reverse=True)

    if not diversifier:
        return docs[:top_k] if top_k else docs

    groupes: Dict[str, List[Dict]] = defaultdict(list)
    for doc in docs:
        groupes[doc.get("theme") or "general"].append(doc)

    # Prioriser les thèmes demandés, puis les mieux scorés
    themes_req = [t.lower() for t in (themes_requete or []) if t]
    autres = sorted(
        (t for t in groupes if t not in themes_req),
        key=lambda t: _score_doc(groupes[t][0]) if groupes[t] else 0,
        reverse=True,
    )
    ordre_themes = []
    for t in themes_req:
        if t in groupes and t not in ordre_themes:
            ordre_themes.append(t)
    for t in autres:
        if t not in ordre_themes:
            ordre_themes.append(t)
    if "general" in groupes and "general" not in ordre_themes:
        ordre_themes.append("general")

    files = {t: list(groupes[t]) for t in ordre_themes}
    out: List[Dict] = []
    limite = top_k or len(docs)
    while len(out) < limite and any(files.values()):
        for theme in ordre_themes:
            if len(out) >= limite:
                break
            if files.get(theme):
                out.append(files[theme].pop(0))
    return out


def themes_disponibles() -> List[str]:
    return sorted(THEME_MOTIFS.keys())

