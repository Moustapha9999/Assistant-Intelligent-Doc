"""Assemblage et formatage des ressources web."""

from __future__ import annotations

from typing import Dict, List, Sequence
from urllib.parse import quote_plus

TYPE_LIEN_RECHERCHE = "lien_recherche"


def dedupliquer_ressources(ressources: Sequence[Dict], max_items: int = 10) -> List[Dict]:
    vus = set()
    uniques: List[Dict] = []
    for r in ressources:
        url = (r.get("url") or "").strip()
        if not url or url in vus or "duckduckgo.com" in url:
            continue
        vus.add(url)
        uniques.append(r)
        if len(uniques) >= max_items:
            break
    return uniques


def liens_youtube(question: str) -> List[Dict]:
    """Génère des liens YouTube (sans requête réseau)."""
    mots = quote_plus(" ".join(question.split()[:6]))
    return [
        {
            "titre": f"🎥 Vidéos YouTube : {question[:50]}",
            "url": f"https://www.youtube.com/results?search_query={mots}+tutoriel+français",
            "extrait": "Tutoriels vidéo sur le sujet",
            "source": "YouTube",
            "type": TYPE_LIEN_RECHERCHE,
        },
        {
            "titre": f"🎥 YouTube (EN) : {question[:50]}",
            "url": f"https://www.youtube.com/results?search_query={mots}+tutorial",
            "extrait": "Video tutorials",
            "source": "YouTube",
            "type": TYPE_LIEN_RECHERCHE,
        },
    ]


def est_lien_recherche(ressource: Dict) -> bool:
    """Lien de recherche généré localement : aucune page n'a été consultée, ce n'est pas une source."""
    return ressource.get("type") == TYPE_LIEN_RECHERCHE


def sources_web_reelles(ressources: List[Dict]) -> List[Dict]:
    return [r for r in ressources or [] if not est_lien_recherche(r)]


def formater_ressources(resultats: List[Dict]) -> str:
    if not resultats:
        return "Aucune ressource web disponible."
    lignes = []
    for r in resultats:
        if r.get("url") and r.get("titre"):
            titre = r["titre"][:80].strip()
            lignes.append(f"- [{titre}]({r['url']}) ({r.get('source', '')})")
    return "\n".join(lignes) if lignes else "Aucune ressource web disponible."
