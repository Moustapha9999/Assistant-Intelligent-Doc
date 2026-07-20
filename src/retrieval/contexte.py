"""Compression contextuelle et résumé extractif des chunks avant LLM."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;:\n])\s+|(?<=\n)")
_TOKEN = re.compile(r"[a-zA-Zàâäéèêëïîôùûüç0-9_]{2,}")

STOPWORDS = frozenset({
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "a", "à",
    "en", "dans", "sur", "pour", "avec", "sans", "par", "au", "aux", "ce",
    "cette", "ces", "qui", "que", "est", "sont", "the", "and", "or", "of",
    "to", "in", "on", "for", "with", "is", "are", "this", "that", "from",
    "as", "be", "by", "an", "it", "you", "we", "can", "will", "if",
})

THEME_MOTIFS: Dict[str, Tuple[str, ...]] = {
    "fastapi": ("fastapi", "uvicorn", "pydantic", "depends", "@app."),
    "flask": ("flask", "werkzeug", "jinja", "@app.route", "jsonify"),
    "django": ("django", "queryset", "select_related", "models.py"),
    "react": ("react", "usestate", "useeffect", "jsx", "component"),
    "docker": ("docker", "dockerfile", "compose", "container"),
    "jwt": ("jwt", "pyjwt", "bearer", "oauth", "token"),
    "sql": ("sql", "postgres", "mysql", "query", "orm", "sqlalchemy"),
    "python": ("python", "pathlib", "asyncio", "pytest", "typing"),
    "architecture": ("architecture", "microservice", "pattern", "layered"),
    "security": ("security", "xss", "csrf", "owasp", "auth"),
}


def _tokens(texte: str) -> List[str]:
    return [t for t in _TOKEN.findall((texte or "").lower()) if t not in STOPWORDS]


def _split_phrases(texte: str) -> List[str]:
    brut = [p.strip() for p in _SENTENCE_SPLIT.split(texte or "") if p and p.strip()]
    # Fusionner les trop courtes avec la suivante
    phrases: List[str] = []
    buffer = ""
    for p in brut:
        if len(p) < 40 and buffer:
            buffer = f"{buffer} {p}".strip()
            phrases.append(buffer)
            buffer = ""
        elif len(p) < 40:
            buffer = p
        else:
            if buffer:
                phrases.append(f"{buffer} {p}".strip())
                buffer = ""
            else:
                phrases.append(p)
    if buffer:
        phrases.append(buffer)
    return phrases or ([texte.strip()] if texte and texte.strip() else [])


def detecter_theme_doc(doc: Dict) -> str:
    """Infère un thème à partir du repo, de la section et du texte."""
    blob = " ".join(
        str(doc.get(k) or "")
        for k in ("nom_complet", "section_titre", "langage", "texte")
    ).lower()
    scores = {
        theme: sum(1 for m in motifs if m in blob)
        for theme, motifs in THEME_MOTIFS.items()
    }
    best = max(scores, key=scores.get) if scores else "general"
    return best if scores.get(best, 0) > 0 else "general"


def score_phrase_vs_requete(phrase: str, termes_requete: Sequence[str]) -> float:
    if not phrase or not termes_requete:
        return 0.0
    tokens = set(_tokens(phrase))
    if not tokens:
        return 0.0
    hits = sum(1 for t in termes_requete if t in tokens or t in phrase.lower())
    densite = hits / max(1, len(set(termes_requete)))
    # Bonus phrases moyennes (ni trop courtes ni trop longues)
    longueur = len(phrase)
    bonus_len = 0.1 if 60 <= longueur <= 280 else 0.0
    # Bonus code / API markers
    bonus_code = 0.15 if any(x in phrase for x in ("```", "@app.", "def ", "class ", "import ")) else 0.0
    return densite + bonus_len + bonus_code


def resumer_chunk(
    texte: str,
    requete: str = "",
    max_chars: int = 700,
    max_phrases: int = 4,
) -> str:
    """
    Résumé extractif orienté requête : garde les phrases les plus pertinentes
    tout en conservant un peu de contexte d'ouverture.
    """
    texte = (texte or "").strip()
    if not texte:
        return ""
    if len(texte) <= max_chars:
        return texte

    phrases = _split_phrases(texte)
    if len(phrases) == 1:
        return texte[:max_chars].rstrip() + " ..."

    termes = _tokens(requete) if requete else []
    notes = []
    for i, phrase in enumerate(phrases):
        score = score_phrase_vs_requete(phrase, termes)
        # Garde un peu la première phrase (contexte)
        if i == 0:
            score += 0.25
        notes.append((score, i, phrase))

    notes.sort(key=lambda x: (-x[0], x[1]))
    retenues_idx = sorted({n[1] for n in notes[:max_phrases]})
    resume = " ".join(phrases[i] for i in retenues_idx).strip()

    if len(resume) > max_chars:
        # Couper proprement sur une phrase déjà retenue
        coupe = []
        total = 0
        for i in retenues_idx:
            p = phrases[i]
            if total + len(p) + 1 > max_chars:
                reste = max_chars - total - 4
                if reste > 40:
                    coupe.append(p[:reste].rstrip() + " ...")
                break
            coupe.append(p)
            total += len(p) + 1
        resume = " ".join(coupe).strip()
    return resume or texte[:max_chars].rstrip() + " ..."


def grouper_par_theme(documents: List[Dict]) -> Dict[str, List[Dict]]:
    groupes: Dict[str, List[Dict]] = defaultdict(list)
    for doc in documents:
        theme = doc.get("theme") or detecter_theme_doc(doc)
        doc["theme"] = theme
        groupes[theme].append(doc)
    return dict(groupes)


def compresser_documents(
    documents: List[Dict],
    max_docs: int = 5,
    max_chars: int = 900,
    requete: str = "",
    resumer: bool = True,
    diversifier_themes: bool = True,
) -> List[Dict]:
    """
    Compresse le contexte documentaire pour le LLM :
    - ranking / diversification légère par thème
    - résumé extractif par chunk (si resumer=True)
    - conservation des métadonnées et scores
    """
    if not documents:
        return []

    selection = list(documents[: max(max_docs * 3, max_docs)])
    for doc in selection:
        if not doc.get("theme"):
            doc["theme"] = detecter_theme_doc(doc)

    if diversifier_themes and len(selection) > max_docs:
        selection = _diversifier_par_theme(selection, max_docs)
    else:
        selection = selection[:max_docs]

    compacts: List[Dict] = []
    for doc in selection:
        copie = dict(doc)
        texte = copie.get("texte", "") or ""
        if resumer:
            resume = resumer_chunk(texte, requete=requete, max_chars=max_chars)
            copie["texte_brut"] = texte
            copie["texte"] = resume
            copie["resume_auto"] = True
            copie["chars_originaux"] = len(texte)
            copie["chars_resume"] = len(resume)
        elif len(texte) > max_chars:
            copie["texte"] = texte[:max_chars].rstrip() + " ..."
            copie["resume_auto"] = False
        else:
            copie["resume_auto"] = False
        compacts.append(copie)
    return compacts


def _diversifier_par_theme(documents: List[Dict], max_docs: int) -> List[Dict]:
    """Round-robin inter-thèmes pour éviter 5 chunks du même repo/sujet."""
    groupes = grouper_par_theme(documents)
    # Thèmes triés par meilleur score interne
    def best_score(docs: List[Dict]) -> float:
        return max(
            float(d.get("score_rerank") or d.get("score_confiance") or d.get("score_final") or 0)
            for d in docs
        )

    themes_ordonnes = sorted(groupes.keys(), key=lambda t: best_score(groupes[t]), reverse=True)
    files = {t: list(groupes[t]) for t in themes_ordonnes}
    out: List[Dict] = []
    while len(out) < max_docs and any(files.values()):
        for theme in themes_ordonnes:
            if len(out) >= max_docs:
                break
            if files[theme]:
                out.append(files[theme].pop(0))
    return out


def resume_contexte_global(
    documents: Sequence[Dict],
    requete: str = "",
    max_chars_total: int = 3500,
) -> str:
    """Produit un bloc texte déjà compressé, groupé par thème, prêt pour le prompt."""
    if not documents:
        return "Aucun document RAG."

    groupes = grouper_par_theme(list(documents))
    blocs: List[str] = []
    budget = max_chars_total

    for theme, docs in groupes.items():
        lignes = [f"### Thème : {theme}"]
        for i, doc in enumerate(docs, 1):
            texte = doc.get("texte") or ""
            if requete and not doc.get("resume_auto"):
                texte = resumer_chunk(texte, requete=requete, max_chars=min(700, budget // 2))
            meta = (
                f"[Doc {theme}/{i}] repo={doc.get('nom_complet', 'N/A')} | "
                f"section={doc.get('section_titre', 'N/A')} | "
                f"score={doc.get('score_confiance', doc.get('score_rerank', 0))}"
            )
            bloc = f"{meta}\n{texte}"
            if len(bloc) > budget:
                bloc = bloc[:budget].rstrip() + " ..."
            lignes.append(bloc)
            budget -= len(bloc) + 2
            if budget < 200:
                break
        blocs.append("\n\n".join(lignes))
        if budget < 200:
            break
    return "\n\n".join(blocs)
