"""Recherche web : configuration et constantes."""

from __future__ import annotations

import os


def web_search_desactive() -> bool:
    return os.getenv("DESACTIVER_WEB_SEARCH", "false").lower() == "true"


def web_timeout() -> int:
    return int(os.getenv("WEB_TIMEOUT", "5"))


USER_AGENT = "Mozilla/5.0 AssistDoc/1.0"
DDG_API = "https://api.duckduckgo.com/"
DDG_HTML = "https://html.duckduckgo.com/html/"
