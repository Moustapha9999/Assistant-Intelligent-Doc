"""Formatage des citations expert (fichier:ligne, commits, confiance)."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple


def _repo_github(url: str, nom_complet: str) -> Optional[str]:
    if nom_complet and "/" in nom_complet and not nom_complet.startswith("enrichissement/"):
        return nom_complet.strip()
    m = re.search(r"github\.com/([^/]+/[^/]+)", url or "")
    if m:
        return m.group(1).rstrip(".git")
    return None


def citation_courte(doc: Dict) -> str:
    """Ex. `[README.md:42]` ou `[docs/guide.md § Installation]`."""
    src = (doc.get("source_file") or "").strip() or "source"
    ligne = doc.get("ligne_debut")
    section = (doc.get("section_titre") or "").strip()
    if isinstance(ligne, int) and ligne > 0:
        return f"[{src}:{ligne}]"
    if section:
        return f"[{src} § {section[:60]}]"
    return f"[{src}]"


def liens_github(doc: Dict) -> Tuple[Optional[str], Optional[str]]:
    """Retourne (url_blob_ou_repo, url_commits)."""
    url = (doc.get("url") or "").strip()
    repo = _repo_github(url, doc.get("nom_complet") or "")
    if not repo:
        return (url if url.startswith("http") else None, None)
    base = f"https://github.com/{repo}"
    src = (doc.get("source_file") or "").strip()
    ligne = doc.get("ligne_debut")
    blob = None
    if src and not src.startswith("enrichissement/"):
        blob = f"{base}/blob/HEAD/{src.lstrip('/')}"
        if isinstance(ligne, int) and ligne > 0:
            blob += f"#L{ligne}"
    elif url.startswith("http"):
        blob = url
    else:
        blob = base
    return blob, f"{base}/commits"


def enrichir_document(doc: Dict) -> Dict:
    out = dict(doc)
    out["citation_courte"] = citation_courte(doc)
    blob, commits = liens_github(doc)
    if blob:
        out["url_blob"] = blob
    if commits:
        out["url_commits"] = commits
    return out


def construire_bloc_citations(
    documents: List[Dict],
    ressources: List[Dict],
    mode_expert: bool = False,
) -> str:
    docs = [enrichir_document(d) for d in (documents or [])]
    lignes: List[str] = []
    if docs:
        titre = "📚 **Sources GitHub (citations expert) :**" if mode_expert else "📚 **Sources GitHub :**"
        lignes.append(titre)
        for i, doc in enumerate(docs[:5], 1):
            repo = doc.get("nom_complet", "N/A")
            cite = doc.get("citation_courte") or citation_courte(doc)
            conf = doc.get("score_confiance")
            conf_s = f" · confiance {conf:.0%}" if isinstance(conf, (int, float)) else ""
            blob = doc.get("url_blob") or doc.get("url") or ""
            commits = doc.get("url_commits") or ""
            lien = f"[{repo}]({blob})" if blob else repo
            extras = []
            if commits and mode_expert:
                extras.append(f"[commits]({commits})")
            extra = (" · " + " · ".join(extras)) if extras else ""
            lignes.append(f"[{i}] {lien} `{cite}`{conf_s}{extra}")
    if ressources:
        lignes.append("\n🌐 **Ressources web :**")
        for r in ressources[:6]:
            if r.get("url") and r.get("titre"):
                lignes.append(f"- [{r['titre'][:70]}]({r['url']})")
    return "\n".join(lignes).strip()
