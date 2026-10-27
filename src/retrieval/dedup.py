"""Déduplication, injections de termes et boosts lexicaux."""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Sequence

_LANGUES = (
    "chinese|japanese|korean|french|hebrew|basque|russian|polish|turkish|brazilian|spanish|"
    "indonesian|german|italian|ukrainian|vietnamese|arabic|persian|portuguese"
)
_CODES = "de|fr|es|it|pt|ru|ja|ko|zh|tr|pl|uk|vi|ar|fa|id|he|nl|sv|cs|hu|ro|el|th|hi|bn"
_TRADUCTION = re.compile(
    rf"[._-](?:{_LANGUES}|(?:{_CODES})(?:[-_][a-z]{{2,4}})?)\.(?:md|rst|txt)$"
    rf"|(?:^|/)docs/(?:{_CODES})(?:[-_][a-z]{{2,4}})?/",
    re.IGNORECASE,
)


def est_traduction(chemin: str) -> bool:
    """`README.french.md`, `README.zh-CN.md`, `docs/de/...` : copie traduite d'un document original."""
    return bool(_TRADUCTION.search(chemin or ""))


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
    repos_preferes: Dict[str, Iterable[str]] | None = None,
) -> List[Dict]:
    """
    Ajoute des chunks contenant des marqueurs d'API exacts (`@app.get`, `Dockerfile`…),
    que la tokenisation BM25 par espaces rate. Les candidats sont classés (dépôt
    officiel, nombre de marqueurs distincts, original avant traduction) ; le cross-encoder
    les juge ensuite.
    """
    if not chunks_bruts:
        return documents
    q = requete.lower()
    termes: List[str] = []
    repos: List[str] = []
    for cle, liste in termes_forces.items():
        if cle in q:
            termes.extend(liste)
            repos.extend((repos_preferes or {}).get(cle, []))
    if not termes:
        return documents
    repos_low = [r.lower() for r in repos]

    existants = {d.get("texte", "")[:200] for d in documents}
    candidats = []
    for idx, chunk in enumerate(chunks_bruts):
        texte = chunk.get("texte", "")
        hits = sum(1 for t in termes if t in texte)
        if not hits or texte[:200] in existants:
            continue
        if chunk.get("source_enrichissement") or str(chunk.get("nom_complet", "")).startswith("enrichissement/"):
            continue
        officiel = any(r in str(chunk.get("nom_complet", "")).lower() for r in repos_low)
        original = not est_traduction(chunk.get("chemin_fichier") or chunk.get("source_file") or "")
        candidats.append((officiel, hits, original, -idx, chunk))
    candidats.sort(key=lambda c: c[:4], reverse=True)

    ajoutes = []
    for *_, chunk in candidats:
        cle = chunk.get("texte", "")[:200]
        if cle in existants:
            continue
        ajoutes.append({
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
            "score_bm25": 0.0,
            "score_final": 0.0,
            "score_confiance": 0.0,
            "injecte_par_termes": True,
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
        if any(b in repo for b in bruit_repos):
            if not any(k in q for k in ("linux", "bash", "shell", "cli", "node")):
                bonus -= 0.8
        # Le boost sert au classement ; score_confiance reste celui du cross-encoder
        doc["score_rerank"] = float(doc.get("score_rerank", 0)) + bonus
        doc["boost_lexical"] = bonus
    return sorted(documents, key=lambda d: d.get("score_rerank", 0), reverse=True)

