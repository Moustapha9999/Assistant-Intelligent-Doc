"""Déduplication, injections de termes et boosts lexicaux."""

from __future__ import annotations

from typing import Dict, Iterable, List, Sequence

from retrieval.fusion import normaliser_confiance


def dedupliquer_documents(documents: Sequence[Dict], key_chars: int = 200) -> List[Dict]:
    vus = set()
    uniques = []
    for doc in documents:
        cle = (doc.get("texte") or "")[:key_chars]
        if not cle or cle in vus:
            continue
        vus.add(cle)
        uniques.append(doc)
    return uniques


def injecter_hits_termes(
    requete: str,
    documents: List[Dict],
    chunks_bruts: List[Dict],
    termes_forces: Dict[str, Iterable[str]],
    max_inject: int = 8,
) -> List[Dict]:
    if not chunks_bruts:
        return documents
    q = requete.lower()
    termes = []
    for cle, liste in termes_forces.items():
        if cle in q:
            termes.extend(liste)
    if not termes:
        return documents

    existants = {d.get("texte", "")[:200] for d in documents}
    ajoutes = []
    for chunk in chunks_bruts:
        texte = chunk.get("texte", "")
        if not any(t in texte for t in termes):
            continue
        cle = texte[:200]
        if cle in existants:
            continue
        ajoutes.append({
            "texte": texte,
            "nom_complet": chunk.get("nom_complet", ""),
            "langage": chunk.get("langage", ""),
            "url": chunk.get("url", ""),
            "section_titre": chunk.get("section_titre", ""),
            "source_file": chunk.get("chemin_fichier", ""),
            "etoiles": chunk.get("etoiles", 0) or 0,
            "mis_a_jour_le": chunk.get("mis_a_jour_le", ""),
            "version": chunk.get("version", ""),
            "score_dense": 0.0,
            "score_bm25": 0.4,
            "score_final": 0.4,
            "score_rerank": 0.3,
            "score_confiance": 0.35,
        })
        existants.add(cle)
        if len(ajoutes) >= max_inject:
            break
    return dedupliquer_documents(documents + ajoutes)


def booster_lexical(
    requete: str,
    documents: List[Dict],
    boost_termes: Dict[str, List[str]],
    repo_preference: Dict[str, List[str]],
    bruit_repos: Iterable[str],
) -> List[Dict]:
    if not documents:
        return documents
    q = requete.lower()
    termes, repos = [], []
    for cle, syns in boost_termes.items():
        if cle in q:
            termes.extend(syns)
    for cle, liste in repo_preference.items():
        if cle in q:
            repos.extend(liste)

    for doc in documents:
        texte = f"{doc.get('texte', '')} {doc.get('nom_complet', '')} {doc.get('section_titre', '')}".lower()
        hits = sum(1 for t in termes if t.lower() in texte)
        bonus = min(0.20, 0.05 * hits)
        repo = (doc.get("nom_complet") or "").lower()
        if any(r.lower() in repo for r in repos):
            bonus += 0.15
        if "enrichissement/" in repo or "knowledge/" in repo:
            bonus += 0.20
        if any(b in repo for b in bruit_repos):
            if not any(k in q for k in ("linux", "bash", "shell", "cli", "node")):
                bonus -= 0.8
        doc["score_rerank"] = float(doc.get("score_rerank", 0)) + bonus
        doc["boost_lexical"] = bonus
        doc["score_confiance"] = normaliser_confiance(
            doc.get("score_rerank", 0), doc.get("score_dense", 0)
        )
    return sorted(documents, key=lambda d: d.get("score_rerank", 0), reverse=True)

