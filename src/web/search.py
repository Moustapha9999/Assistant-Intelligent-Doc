"""Client de recherche web : Tavily si TAVILY_API_KEY est défini, sinon DuckDuckGo (API + HTML)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List
from urllib.parse import urlparse

import requests

from web.config import (
    DDG_API,
    DDG_HTML,
    TAVILY_SEARCH,
    USER_AGENT,
    tavily_api_key,
    web_search_desactive,
    web_timeout,
)
from web.extracteur import extraire_resultats_html, normaliser_item_api
from web.ressources import dedupliquer_ressources, formater_ressources, liens_youtube


class WebSearcher:
    """Recherche web via DuckDuckGo (API + fallback HTML)."""

    def __init__(self):
        self.base_url = DDG_API
        self.headers = {"User-Agent": USER_AGENT}
        # Si une recherche échoue (connexion bloquée), on coupe pour la session
        self._desactive_runtime = False

    @property
    def desactive(self) -> bool:
        return web_search_desactive() or self._desactive_runtime

    def set_actif(self, actif: bool) -> None:
        """Active/désactive la recherche pour la session courante."""
        self._desactive_runtime = not actif

    def rechercher(self, requete: str, nb_resultats: int = 5) -> List[Dict]:
        if self.desactive:
            return []
        resultats: List[Dict] = []
        try:
            params = {
                "q": requete,
                "format": "json",
                "no_html": 1,
                "skip_disambig": 1,
            }
            resp = requests.get(
                self.base_url,
                params=params,
                headers=self.headers,
                timeout=web_timeout(),
            )
            data = resp.json()

            if data.get("AbstractText") and data.get("AbstractURL"):
                resultats.append({
                    "titre": data.get("Heading", requete),
                    "url": data.get("AbstractURL", ""),
                    "extrait": data.get("AbstractText", "")[:300],
                    "source": data.get("AbstractSource", "Wikipedia"),
                })

            for item in data.get("RelatedTopics", [])[:nb_resultats]:
                normalise = normaliser_item_api(item)
                if normalise:
                    resultats.append(normalise)
                elif isinstance(item, dict) and "Topics" in item:
                    for sous in item["Topics"][:3]:
                        n2 = normaliser_item_api(sous)
                        if n2:
                            resultats.append(n2)
        except Exception:
            print("   ⚠️  Web search indisponible (coupé pour la session)")
            self._desactive_runtime = True

        return resultats[:nb_resultats]

    def rechercher_html(self, requete: str, nb_resultats: int = 5) -> List[Dict]:
        """Fallback : scrape la page HTML de DuckDuckGo pour des résultats organiques."""
        if self.desactive:
            return []
        try:
            resp = requests.get(
                DDG_HTML,
                params={"q": requete},
                headers=self.headers,
                timeout=web_timeout(),
            )
            return extraire_resultats_html(resp.text, nb_resultats=nb_resultats)
        except Exception:
            self._desactive_runtime = True
            return []

    def rechercher_ressources_apprentissage(self, question: str) -> List[Dict]:
        """Tutoriels / docs + liens YouTube générés."""
        ressources: List[Dict] = []
        ressources.extend(self.rechercher_html(f"{question} tutoriel", 3))
        ressources.extend(self.rechercher_html(f"{question} documentation officielle", 2))
        try:
            ressources.extend(liens_youtube(question))
        except Exception:
            pass
        return ressources

    def rechercher_tavily(self, requete: str, nb_resultats: int = 6) -> List[Dict]:
        """Résultats organiques Tavily (titre, URL, extrait de la page consultée)."""
        cle = tavily_api_key()
        if self.desactive or not cle:
            return []
        try:
            resp = requests.post(
                TAVILY_SEARCH,
                json={
                    "query": requete,
                    "search_depth": "basic",
                    "max_results": nb_resultats,
                    "include_answer": False,
                },
                headers={"Authorization": f"Bearer {cle}", "User-Agent": USER_AGENT},
                timeout=max(web_timeout(), 10),
            )
            resp.raise_for_status()
            resultats = []
            for item in resp.json().get("results", [])[:nb_resultats]:
                url = (item.get("url") or "").strip()
                if not url:
                    continue
                resultats.append({
                    "titre": (item.get("title") or url)[:120],
                    "url": url,
                    "extrait": (item.get("content") or "")[:300],
                    "source": urlparse(url).netloc,
                })
            return resultats
        except Exception as exc:
            code = getattr(getattr(exc, "response", None), "status_code", "")
            print(f"   ⚠️  Tavily indisponible {code}".rstrip())
            return []

    def rechercher_multi(self, question: str) -> List[Dict]:
        """Requêtes lancées en parallèle : la latence est celle de la plus lente, pas la somme."""
        if self.desactive:
            return []
        if tavily_api_key():
            tous = self.rechercher_tavily(question)
            tous.extend(liens_youtube(question))
            return dedupliquer_ressources(tous, max_items=10)
        taches = [
            (self.rechercher, (question,)),
            (self.rechercher, (f"{question} wikipedia", 2)),
            (self.rechercher_html, (question, 4)),
            (self.rechercher_html, (f"{question} tutoriel", 3)),
            (self.rechercher_html, (f"{question} documentation officielle", 2)),
        ]
        tous: List[Dict] = []
        with ThreadPoolExecutor(max_workers=len(taches)) as pool:
            futurs = [pool.submit(fn, *args) for fn, args in taches]
            for futur in futurs:
                try:
                    tous.extend(futur.result())
                except Exception:
                    continue
        try:
            tous.extend(liens_youtube(question))
        except Exception:
            pass
        return dedupliquer_ressources(tous, max_items=10)

    def formater(self, resultats: List[Dict]) -> str:
        return formater_ressources(resultats)
