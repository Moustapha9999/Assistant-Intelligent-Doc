import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from web.extracteur import decoder_url_ddg, extraire_resultats_html, normaliser_item_api
from web.ressources import dedupliquer_ressources, formater_ressources, liens_youtube
from web.search import WebSearcher


def test_decoder_url_ddg():
    brut = "https://duckduckgo.com/l/?uddg=https%3A%2F%2Ffastapi.tiangolo.com%2F&rut=x"
    assert decoder_url_ddg(brut) == "https://fastapi.tiangolo.com/"


def test_extraire_resultats_html():
    html = '''
    <a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.python.org%2F">Python docs</a>
    <a class="result__a" href="https://example.com/page">Example</a>
    '''
    res = extraire_resultats_html(html, nb_resultats=5)
    assert len(res) == 2
    assert res[0]["url"] == "https://docs.python.org/"
    assert "Python" in res[0]["titre"]


def test_normaliser_item_api():
    item = {"FirstURL": "https://x.test", "Text": "Hello world"}
    n = normaliser_item_api(item)
    assert n["url"] == "https://x.test"
    assert n["titre"] == "Hello world"


def test_dedup_et_format():
    items = [
        {"titre": "A", "url": "https://a.test", "source": "Web"},
        {"titre": "A2", "url": "https://a.test", "source": "Web"},
        {"titre": "DDG", "url": "https://duckduckgo.com/x", "source": "Web"},
        {"titre": "B", "url": "https://b.test", "source": "Web"},
    ]
    uniques = dedupliquer_ressources(items, max_items=10)
    assert len(uniques) == 2
    txt = formater_ressources(uniques)
    assert "https://a.test" in txt
    assert "https://b.test" in txt


def test_liens_youtube():
    liens = liens_youtube("FastAPI JWT auth")
    assert len(liens) == 2
    assert "youtube.com" in liens[0]["url"]


def test_rechercher_multi_parallele_et_ordonne(monkeypatch):
    import time

    monkeypatch.delenv("DESACTIVER_WEB_SEARCH", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    s = WebSearcher()

    def faux_api(requete, nb_resultats=5):
        time.sleep(0.3)
        return [{"titre": f"api {requete}", "url": f"https://api.test/{len(requete)}", "source": "Web"}]

    def faux_html(requete, nb_resultats=5):
        time.sleep(0.3)
        return [{"titre": f"html {requete}", "url": f"https://html.test/{len(requete)}", "source": "Web"}]

    monkeypatch.setattr(s, "rechercher", faux_api)
    monkeypatch.setattr(s, "rechercher_html", faux_html)
    t0 = time.perf_counter()
    res = s.rechercher_multi("fastapi")
    assert time.perf_counter() - t0 < 1.0
    titres = [r["titre"] for r in res]
    assert titres[:3] == ["api fastapi", "api fastapi wikipedia", "html fastapi"]


def test_tavily_prioritaire_quand_cle_definie(monkeypatch):
    import web.search as module_search

    monkeypatch.delenv("DESACTIVER_WEB_SEARCH", raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    appels = {}

    class _Reponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": [
                {"title": "Multi-stage builds", "url": "https://docs.docker.com/build/building/multi-stage/",
                 "content": "Use multi-stage builds to keep images small."},
                {"title": "sans url", "url": ""},
            ]}

    def faux_post(url, json=None, headers=None, timeout=None):
        appels.update(url=url, json=json, headers=headers)
        return _Reponse()

    def interdit(*a, **k):
        raise AssertionError("DuckDuckGo ne doit pas être appelé quand Tavily est configuré")

    monkeypatch.setattr(module_search.requests, "post", faux_post)
    monkeypatch.setattr(module_search.requests, "get", interdit)
    res = WebSearcher().rechercher_multi("Dockerfile multi-stage")
    assert appels["headers"]["Authorization"] == "Bearer tvly-test"
    assert appels["json"]["query"] == "Dockerfile multi-stage"
    assert res[0]["url"] == "https://docs.docker.com/build/building/multi-stage/"
    assert res[0]["source"] == "docs.docker.com"
    assert "multi-stage" in res[0]["extrait"]
    assert all(r["url"] for r in res)


def test_tavily_en_erreur_renvoie_vide(monkeypatch):
    import web.search as module_search

    monkeypatch.delenv("DESACTIVER_WEB_SEARCH", raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")

    def faux_post(*a, **k):
        raise module_search.requests.Timeout("lent")

    monkeypatch.setattr(module_search.requests, "post", faux_post)
    assert WebSearcher().rechercher_tavily("fastapi") == []


def test_websearcher_desactive_via_env(monkeypatch):
    monkeypatch.setenv("DESACTIVER_WEB_SEARCH", "true")
    s = WebSearcher()
    assert s.desactive is True
    assert s.rechercher("fastapi") == []
    assert s.rechercher_html("fastapi") == []
