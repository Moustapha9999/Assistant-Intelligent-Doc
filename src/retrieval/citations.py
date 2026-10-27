"""Formatage des citations expert (fichier:ligne, commits, confiance)."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from web.ressources import est_lien_recherche

PROVENANCE_GITHUB = "github"
PROVENANCE_GUIDE = "guide_interne"
PROVENANCE_INCONNUE = "inconnue"

_PREFIXES_INTERNES = ("enrichissement/", "knowledge/")
_NOM_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def determiner_provenance(doc: Dict) -> str:
    """
    `github` uniquement si le dépôt et l'URL concordent (https://github.com/<owner>/<repo>).
    Les guides rédigés pour le projet sont `guide_interne`, jamais présentés comme dépôts.
    """
    nom = str(doc.get("nom_complet") or "").strip()
    src = str(doc.get("source_file") or doc.get("chemin_fichier") or "").strip()
    if doc.get("source_enrichissement") or nom.startswith(_PREFIXES_INTERNES) or src.startswith(_PREFIXES_INTERNES):
        return PROVENANCE_GUIDE
    if not _NOM_REPO.match(nom):
        return PROVENANCE_INCONNUE
    url = str(doc.get("url") or "").strip().rstrip("/")
    if url.lower() == f"https://github.com/{nom}".lower():
        return PROVENANCE_GITHUB
    return PROVENANCE_INCONNUE


def _repo_github(url: str, nom_complet: str) -> Optional[str]:
    doc = {"url": url, "nom_complet": nom_complet}
    if determiner_provenance(doc) == PROVENANCE_GITHUB:
        return nom_complet.strip()
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
    """Retourne (url_blob_ou_repo, url_commits) — uniquement pour une provenance GitHub vérifiée."""
    if determiner_provenance(doc) != PROVENANCE_GITHUB:
        return None, None
    base = f"https://github.com/{str(doc.get('nom_complet')).strip()}"
    src = str(doc.get("source_file") or doc.get("chemin_fichier") or "").strip()
    ligne = doc.get("ligne_debut")
    blob = base
    if src:
        blob = f"{base}/blob/HEAD/{src.lstrip('/')}"
        if isinstance(ligne, int) and ligne > 0:
            blob += f"#L{ligne}"
    return blob, f"{base}/commits"


def enrichir_document(doc: Dict) -> Dict:
    out = dict(doc)
    out["provenance"] = determiner_provenance(doc)
    out["citation_courte"] = citation_courte(doc)
    out.pop("url_blob", None)
    out.pop("url_commits", None)
    blob, commits = liens_github(doc)
    if blob:
        out["url_blob"] = blob
    if commits:
        out["url_commits"] = commits
    if out["provenance"] != PROVENANCE_GITHUB:
        # Ni URL ni étoiles inventées pour une source non vérifiable
        out["url"] = ""
        out["etoiles"] = None
    return out


def construire_bloc_citations(
    documents: List[Dict],
    ressources: List[Dict],
    mode_expert: bool = False,
) -> str:
    docs = [enrichir_document(d) for d in (documents or [])][:5]
    github = [(i, d) for i, d in enumerate(docs, 1) if d["provenance"] == PROVENANCE_GITHUB]
    internes = [(i, d) for i, d in enumerate(docs, 1) if d["provenance"] != PROVENANCE_GITHUB]
    lignes: List[str] = []
    if github:
        titre = "📚 **Sources GitHub (citations expert) :**" if mode_expert else "📚 **Sources GitHub :**"
        lignes.append(titre)
        for i, doc in github:
            repo = doc.get("nom_complet", "N/A")
            cite = doc.get("citation_courte") or citation_courte(doc)
            conf = doc.get("score_confiance")
            conf_s = f" · confiance {conf:.0%}" if isinstance(conf, (int, float)) else ""
            blob = doc.get("url_blob") or ""
            commits = doc.get("url_commits") or ""
            lien = f"[{repo}]({blob})" if blob else repo
            extras = []
            if commits and mode_expert:
                extras.append(f"[commits]({commits})")
            extra = (" · " + " · ".join(extras)) if extras else ""
            lignes.append(f"[{i}] {lien} `{cite}`{conf_s}{extra}")
    if internes:
        if lignes:
            lignes.append("")
        lignes.append("📘 **Guides internes AssistDoc (hors dépôts GitHub) :**")
        for i, doc in internes:
            titre_doc = (doc.get("section_titre") or doc.get("nom_complet") or "guide").strip()
            conf = doc.get("score_confiance")
            conf_s = f" · confiance {conf:.0%}" if isinstance(conf, (int, float)) else ""
            lignes.append(f"[{i}] {titre_doc[:80]}{conf_s}")
    web = [r for r in ressources or [] if r.get("url") and r.get("titre")]
    consultees = [r for r in web if not est_lien_recherche(r)]
    pistes = [r for r in web if est_lien_recherche(r)]
    if consultees:
        lignes.append("\n🌐 **Ressources web :**")
        for r in consultees[:6]:
            lignes.append(f"- [{r['titre'][:70]}]({r['url']})")
    if pistes:
        lignes.append("\n🔎 **Pour aller plus loin (recherches suggérées, non consultées) :**")
        for r in pistes[:2]:
            lignes.append(f"- [{r['titre'][:70]}]({r['url']})")
    return "\n".join(lignes).strip()
