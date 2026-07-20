"""Client de recherche web (DuckDuckGo Instant Answer + HTML)."""

from __future__ import annotations

from typing import Dict, List

import requests

from web.config import DDG_API, DDG_HTML, USER_AGENT, web_search_desactive, web_timeout
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

    def rechercher_multi(self, question: str) -> List[Dict]:
        tous: List[Dict] = []
        tous.extend(self.rechercher(question))
        tous.extend(self.rechercher(f"{question} wikipedia", 2))
        tous.extend(self.rechercher_html(question, 4))
        tous.extend(self.rechercher_ressources_apprentissage(question))
        return dedupliquer_ressources(tous, max_items=10)

    def formater(self, resultats: List[Dict]) -> str:
        return formater_ressources(resultats)
