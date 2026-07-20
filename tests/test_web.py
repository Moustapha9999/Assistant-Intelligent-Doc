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


def test_websearcher_desactive_via_env(monkeypatch):
    monkeypatch.setenv("DESACTIVER_WEB_SEARCH", "true")
    s = WebSearcher()
    assert s.desactive is True
    assert s.rechercher("fastapi") == []
    assert s.rechercher_html("fastapi") == []
