"""Déploiement cloud : téléchargement du corpus (config.assurer_corpus) et dépendances."""

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

import config

ROOT = Path(__file__).resolve().parent.parent


def _archive() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("tous_chunks.json", json.dumps([{"texte": "x"}]))
        z.writestr("bm25_cache/meta.json", "{}")
        z.writestr("autre/intrus.txt", "ne doit pas être extrait")
    return buf.getvalue()


class _Reponse:
    def __init__(self, contenu: bytes):
        self.contenu = contenu

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        for i in range(0, len(self.contenu), chunk_size):
            yield self.contenu[i : i + chunk_size]


@pytest.fixture
def faux_telechargement(monkeypatch):
    contenu = _archive()
    appels = []

    def get(url, stream, timeout):
        appels.append(url)
        return _Reponse(contenu)

    import requests

    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setenv("CORPUS_URL", "https://exemple.test/corpus.zip")
    return contenu, appels


def test_corpus_present_aucun_telechargement(tmp_path, faux_telechargement):
    (tmp_path / "tous_chunks.json").write_text("[]", encoding="utf-8")
    assert config.assurer_corpus(tmp_path) is True
    assert faux_telechargement[1] == []


def test_sans_url_retourne_faux(tmp_path, monkeypatch):
    monkeypatch.delenv("CORPUS_URL", raising=False)
    assert config.assurer_corpus(tmp_path) is False


def test_telechargement_extrait_seulement_les_membres_attendus(tmp_path, faux_telechargement, monkeypatch):
    contenu, appels = faux_telechargement
    monkeypatch.setenv("CORPUS_SHA256", hashlib.sha256(contenu).hexdigest())
    assert config.assurer_corpus(tmp_path) is True
    assert appels == ["https://exemple.test/corpus.zip"]
    assert json.loads((tmp_path / "tous_chunks.json").read_text(encoding="utf-8")) == [{"texte": "x"}]
    assert (tmp_path / "bm25_cache" / "meta.json").exists()
    assert not (tmp_path / "autre").exists()
    assert not list(tmp_path.glob("*.zip")) and not list(tmp_path.rglob("*.part"))


def test_empreinte_incorrecte_refusee(tmp_path, faux_telechargement, monkeypatch):
    monkeypatch.setenv("CORPUS_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="CORPUS_SHA256"):
        config.assurer_corpus(tmp_path)
    assert not (tmp_path / "tous_chunks.json").exists()
    assert not list(tmp_path.glob("*.zip"))


def test_signature_bm25_independante_de_la_date(tmp_path):
    import os

    from retrieval.bm25 import _signature

    f = tmp_path / "c.json"
    f.write_text("[1, 2]", encoding="utf-8")
    avant = _signature(str(f))
    os.utime(f, (1, 1))
    assert _signature(str(f)) == avant
    f.write_text("[1, 3]", encoding="utf-8")
    assert _signature(str(f)) != avant


def test_requirements_execution_sans_outils_evaluation():
    import re

    texte = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    paquets = {
        re.split(r"[<>=\[ ]", ligne.strip())[0]
        for ligne in texte.splitlines()
        if ligne.strip() and not ligne.lstrip().startswith(("#", "-"))
    }
    assert not paquets & {"ragas", "langchain", "pytest", "fastapi", "pandas", "rank-bm25"}
    assert {"streamlit", "torch", "qdrant-client", "scipy"} <= paquets
    assert "download.pytorch.org/whl/cpu" in texte
    assert "-r requirements.txt" in (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
