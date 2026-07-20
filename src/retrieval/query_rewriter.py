"""Réécriture intelligente et expansion bilingue des requêtes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Sequence


EXPANSIONS_REQUETE: Dict[str, str] = {
    "api rest": "REST API Flask FastAPI routes endpoints HTTP",
    "rest": "REST API HTTP endpoints CRUD",
    "flask": "Flask Python microframework @app.route jsonify Blueprint",
    "authentification": "authentication JWT OAuth login token bearer",
    "auth": "authentication JWT OAuth login token",
    "jwt": "JWT JSON Web Token bearer authorization PyJWT encode decode",
    "optimiser": "optimize performance N+1 query caching latency",
    "requêtes sql": "SQL queries ORM select_related prefetch_related JOIN",
    "django": "Django ORM queryset select_related prefetch_related ModelViewSet",
    "fastapi": "FastAPI Python @app.get @app.post Pydantic uvicorn Depends",
    "hooks": "React hooks useState useEffect custom hook functional components",
    "react": "React hooks useState useEffect JSX component props state",
    "fichiers": "files open read write context manager pathlib",
    "python": "Python typing pathlib asyncio",
    "docker": "Docker container Dockerfile compose image volumes network",
    "microservice": "microservices architecture service discovery API gateway",
    "architecture": "software architecture patterns layered hexagonal clean",
    "test": "pytest unittest mock fixture coverage",
    "async": "asyncio async await concurrency aiohttp",
    "websocket": "WebSocket realtime bidirectional socketio",
    "cors": "CORS middleware Access-Control-Allow-Origin",
    "middleware": "middleware middleware stack request response pipeline",
    "pydantic": "Pydantic BaseModel validation Field schema",
    "sqlalchemy": "SQLAlchemy ORM session query relationship",
    "postgres": "PostgreSQL SQL index transaction ACID",
    "cache": "caching Redis memoization TTL",
    "sécurité": "security OWASP XSS CSRF injection HTTPS",
    "deploiement": "deployment CI CD Docker production hosting",
    "déploiement": "deployment CI CD Docker production hosting",
}

# Patterns FR → formulation de recherche plus nette
PATTERNS_INTENTION = (
    (re.compile(r"^(comment|comment faire pour)\s+", re.I), "how to "),
    (re.compile(r"^(explique[rz]?|explique-moi|qu['’]est-ce que|c['’]est quoi)\s+", re.I), ""),
    (re.compile(r"^(montre[rz]?[- ]moi|donne[rz]?[- ]moi|écris|implemente|implémente)\s+", re.I), ""),
    (re.compile(r"\s+(s['’]il te pla[iî]t|stp|please)\s*$", re.I), ""),
)

STOPWORDS_FR = frozenset({
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "a", "à",
    "en", "dans", "sur", "pour", "avec", "sans", "par", "au", "aux", "ce",
    "cette", "ces", "mon", "ma", "mes", "ton", "ta", "tes", "son", "sa",
    "ses", "qui", "que", "quoi", "dont", "où", "est", "sont", "être", "avoir",
    "faire", "peux", "peut", "pouvez", "voudrais", "veux", "besoin", "moi",
    "toi", "nous", "vous", "ils", "elles", "je", "tu", "il", "elle", "on",
    "the", "a", "an", "of", "to", "in", "on", "for", "with", "is", "are",
})

MOTIFS_ERREUR = (
    "erreur", "error", "exception", "traceback", "bug", "crash", "fail",
    "ne marche pas", "doesn't work", "does not work", "undefined", "noneType",
)

MOTIFS_COMPARAISON = (
    "vs", "versus", "compar", "différence", "difference", "avantage", "inconvénient",
)

MOTIFS_HOWTO = (
    "comment", "how to", "étape", "tutoriel", "guide", "mettre en place", "créer",
    "installer", "configurer",
)


@dataclass
class RequeteEnrichie:
    originale: str
    reecrite: str
    variantes: List[str] = field(default_factory=list)
    themes: List[str] = field(default_factory=list)
    intention: str = "general"
    expansions: List[str] = field(default_factory=list)


def _nettoyer(texte: str) -> str:
    texte = re.sub(r"[`*_#>\{\}\[\]\(\)]", " ", texte)
    texte = re.sub(r"\s+", " ", texte).strip()
    return texte


def _detecter_intention(q_low: str) -> str:
    if any(m in q_low for m in MOTIFS_ERREUR):
        return "debug"
    if any(m in q_low for m in MOTIFS_COMPARAISON):
        return "comparaison"
    if any(m in q_low for m in MOTIFS_HOWTO):
        return "howto"
    if any(m in q_low for m in ("qu'est-ce", "c'est quoi", "définition", "definition", "explique")):
        return "definition"
    return "general"


def _detecter_themes(q_low: str, expansions: Dict[str, str]) -> List[str]:
    themes = []
    for motif in expansions:
        if motif in q_low:
            themes.append(motif.split()[0])
    # Ordre stable, unique
    vus = set()
    out = []
    for t in themes:
        if t not in vus:
            vus.add(t)
            out.append(t)
    return out[:6]


def _extraire_mots_cles(requete: str) -> List[str]:
    tokens = re.findall(r"[a-zA-Zàâäéèêëïîôùûüç0-9_@.+-]{2,}", requete.lower())
    return [t for t in tokens if t not in STOPWORDS_FR]


def _reformuler_base(requete: str) -> str:
    base = _nettoyer(requete)
    for pattern, remp in PATTERNS_INTENTION:
        base = pattern.sub(remp, base)
    return _nettoyer(base)


def reecrire_requete(
    requete: str,
    expansions: Dict[str, str] | None = None,
    max_variantes: int = 3,
) -> RequeteEnrichie:
    """
    Réécrit une question naturelle en requête de recherche plus discriminative.

    - retire le bruit conversationnel
    - détecte l'intention (howto / debug / comparaison / définition)
    - ajoute des expansions FR→EN ciblées
    - propose des variantes courtes pour multi-query éventuel
    """
    table = expansions or EXPANSIONS_REQUETE
    originale = (requete or "").strip()
    if not originale:
        return RequeteEnrichie(originale="", reecrite="", intention="general")

    q_low = originale.lower()
    intention = _detecter_intention(q_low)
    themes = _detecter_themes(q_low, table)
    base = _reformuler_base(originale)

    extras: List[str] = []
    for motif, exp in table.items():
        if motif in q_low:
            extras.append(exp)

    # Renfort intentionnel
    if intention == "debug":
        extras.append("error exception traceback fix cause solution")
    elif intention == "comparaison":
        extras.append("comparison differences pros cons tradeoffs")
    elif intention == "howto":
        extras.append("example tutorial steps implementation")
    elif intention == "definition":
        extras.append("definition overview concepts basics")

    mots_cles = _extraire_mots_cles(base)
    noyau = " ".join(mots_cles) if mots_cles else base
    expansion_txt = " ".join(dict.fromkeys(" ".join(extras).split())) if extras else ""
    reecrite = _nettoyer(f"{noyau} {expansion_txt}".strip()) or originale

    variantes: List[str] = []
    if themes:
        variantes.append(" ".join(themes[:3]))
    if intention == "howto" and themes:
        variantes.append(f"how to {' '.join(themes[:2])} example")
    if intention == "debug" and themes:
        variantes.append(f"{' '.join(themes[:2])} error fix")
    if noyau and noyau != reecrite:
        variantes.append(noyau)

    # Dédupliquer / limiter
    vues = {reecrite.lower(), originale.lower()}
    variantes_uniques = []
    for v in variantes:
        v = _nettoyer(v)
        if v and v.lower() not in vues:
            vues.add(v.lower())
            variantes_uniques.append(v)
        if len(variantes_uniques) >= max_variantes:
            break

    return RequeteEnrichie(
        originale=originale,
        reecrite=reecrite,
        variantes=variantes_uniques,
        themes=themes,
        intention=intention,
        expansions=extras,
    )


def enrichir_requete(requete: str, expansions: Dict[str, str] | None = None) -> str:
    """Compatibilité : retourne uniquement la requête enrichie (str)."""
    return reecrire_requete(requete, expansions=expansions).reecrite


def fusionner_requetes(principale: str, variantes: Sequence[str], max_chars: int = 280) -> str:
    """Fusionne requête principale + variantes pour un passage dense/BM25 unique."""
    parts = [principale] + list(variantes)
    fusion = " ".join(dict.fromkeys(" ".join(parts).split()))
    if len(fusion) <= max_chars:
        return fusion
    return fusion[:max_chars].rsplit(" ", 1)[0]
