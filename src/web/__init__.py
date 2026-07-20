"""Module web : recherche, extraction et formatage de ressources."""

from web.ressources import dedupliquer_ressources, formater_ressources, liens_youtube
from web.search import WebSearcher

__all__ = [
    "WebSearcher",
    "dedupliquer_ressources",
    "formater_ressources",
    "liens_youtube",
]
