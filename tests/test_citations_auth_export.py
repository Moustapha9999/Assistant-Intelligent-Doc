import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.export_conversation import export_markdown, export_pdf
from retrieval.citations import citation_courte, construire_bloc_citations, enrichir_document
from securite.identifiants import charger_api_keys, verifier_utilisateur


def test_citation_avec_ligne():
    doc = {"source_file": "src/app.py", "ligne_debut": 42, "section_titre": "main"}
    assert citation_courte(doc) == "[src/app.py:42]"


def test_citation_avec_section():
    doc = {"source_file": "README.md", "section_titre": "Installation"}
    assert citation_courte(doc) == "[README.md § Installation]"


def test_enrichir_liens_github():
    doc = {
        "nom_complet": "tiangolo/fastapi",
        "source_file": "docs/tutorial.md",
        "ligne_debut": 10,
        "url": "https://github.com/tiangolo/fastapi",
        "score_confiance": 0.8,
    }
    out = enrichir_document(doc)
    assert out["citation_courte"] == "[docs/tutorial.md:10]"
    assert "blob/HEAD/docs/tutorial.md#L10" in out["url_blob"]
    assert out["url_commits"].endswith("/commits")


def test_bloc_citations_expert():
    docs = [{
        "nom_complet": "pallets/flask",
        "source_file": "README.md",
        "section_titre": "Quickstart",
        "url": "https://github.com/pallets/flask",
        "score_confiance": 0.7,
    }]
    bloc = construire_bloc_citations(docs, [], mode_expert=True)
    assert "citations expert" in bloc
    assert "[README.md § Quickstart]" in bloc
    assert "commits" in bloc


def test_api_keys_parsing(monkeypatch):
    monkeypatch.setenv("API_KEYS", "k1:alice,k2:bob")
    keys = charger_api_keys()
    assert keys["k1"] == "alice"
    assert keys["k2"] == "bob"
    monkeypatch.delenv("API_KEYS", raising=False)
    assert charger_api_keys() == {}


def test_verifier_utilisateur(monkeypatch):
    monkeypatch.setenv("STREAMLIT_USERS", "alice:secret")
    monkeypatch.delenv("STREAMLIT_PASSWORD", raising=False)
    assert verifier_utilisateur("alice", "secret") is True
    assert verifier_utilisateur("alice", "wrong") is False


def test_export_markdown_et_pdf():
    messages = [
        {"role": "user", "content": "Bonjour"},
        {
            "role": "assistant",
            "content": "Salut",
            "docs": [{
                "nom_complet": "demo/repo",
                "source_file": "a.py",
                "ligne_debut": 3,
                "score_confiance": 0.9,
                "url": "https://github.com/demo/repo",
            }],
        },
    ]
    md = export_markdown(messages)
    assert "AssistDoc" in md
    assert "demo/repo" in md
    pdf = export_pdf(messages)
    assert pdf[:4] == b"%PDF"
