"""Extraction / parsing des résultats HTML DuckDuckGo."""

from __future__ import annotations

import re
import urllib.parse
from typing import Dict, List


_RE_LIEN = re.compile(r'class="result__a"[^>]*href="([^"]+)"')
_RE_TITRE = re.compile(r'class="result__a"[^>]*>([^<]+)<')


def decoder_url_ddg(url: str) -> str:
    """Décode une URL DuckDuckGo (`uddg=`) vers l'URL réelle."""
    if "uddg=" not in url:
        return url
    try:
        return urllib.parse.unquote(url.split("uddg=")[1].split("&")[0])
    except Exception:
        return url


def extraire_resultats_html(html: str, nb_resultats: int = 5) -> List[Dict]:
    """Parse la page HTML DuckDuckGo et retourne des résultats normalisés."""
    if not html:
        return []
    liens = _RE_LIEN.findall(html)
    titres = _RE_TITRE.findall(html)
    resultats: List[Dict] = []
    for url, titre in zip(liens[:nb_resultats], titres[:nb_resultats]):
        url = decoder_url_ddg(url)
        if not url.startswith("http"):
            continue
        resultats.append({
            "titre": titre.strip(),
            "url": url,
            "extrait": "",
            "source": "Web",
        })
    return resultats


def normaliser_item_api(item: dict, source: str = "DuckDuckGo") -> Dict | None:
    """Normalise un item RelatedTopics de l'API Instant Answer."""
    if not isinstance(item, dict):
        return None
    if item.get("FirstURL"):
        return {
            "titre": (item.get("Text") or "")[:100],
            "url": item.get("FirstURL", ""),
            "extrait": (item.get("Text") or "")[:200],
            "source": source,
        }
    return None
