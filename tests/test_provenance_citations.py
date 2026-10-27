import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.classificateur import ClassificateurAssistant
from retrieval.bm25 import BM25Creux, construire_index_bm25, tokeniser
from retrieval.citations import (
    PROVENANCE_GITHUB,
    PROVENANCE_GUIDE,
    PROVENANCE_INCONNUE,
    construire_bloc_citations,
    determiner_provenance,
    enrichir_document,
    liens_github,
)
from retrieval.dedup import booster_lexical, injecter_hits_termes
from retrieval.fusion import (
    appliquer_fraicheur,
    classer_par_theme,
    confiance_cross_encoder,
    reranker_documents,
    separer_par_pertinence,
)
from retrieval.query_rewriter import reecrire_requete

REPO_FASTAPI = {
    "nom_complet": "fastapi/fastapi",
    "url": "https://github.com/fastapi/fastapi",
    "source_file": "README.md",
    "ligne_debut": 42,
    "etoiles": 90000,
    "texte": "@app.get('/items/{item_id}') async def read_item(item_id: int): ...",
}
GUIDE = {
    "nom_complet": "enrichissement/fastapi",
    "url": "https://github.com/enrichissement/fastapi",
    "source_file": "enrichissement/fastapi_routes.md",
    "section_titre": "Routes GET avec FastAPI",
    "etoiles": 50000,
    "source_enrichissement": True,
    "texte": "Guide interne : @app.get FastAPI route GET",
}


# --- Provenance -----------------------------------------------------------------

def test_provenance_github_exige_url_concordante():
    assert determiner_provenance(REPO_FASTAPI) == PROVENANCE_GITHUB
    assert determiner_provenance({**REPO_FASTAPI, "url": "https://github.com/fastapi/fastapi/"}) == PROVENANCE_GITHUB
    assert determiner_provenance({**REPO_FASTAPI, "url": "https://github.com/autre/fastapi"}) == PROVENANCE_INCONNUE
    assert determiner_provenance({**REPO_FASTAPI, "url": "https://gitlab.com/fastapi/fastapi"}) == PROVENANCE_INCONNUE
    assert determiner_provenance({**REPO_FASTAPI, "url": ""}) == PROVENANCE_INCONNUE


def test_provenance_nom_de_depot_invalide():
    assert determiner_provenance({"nom_complet": "fastapi", "url": "https://github.com/fastapi"}) == PROVENANCE_INCONNUE
    assert determiner_provenance({"nom_complet": "", "url": ""}) == PROVENANCE_INCONNUE


def test_guides_internes_jamais_github():
    assert determiner_provenance(GUIDE) == PROVENANCE_GUIDE
    sans_drapeau = {k: v for k, v in GUIDE.items() if k != "source_enrichissement"}
    assert determiner_provenance(sans_drapeau) == PROVENANCE_GUIDE
    assert determiner_provenance({"nom_complet": "x/y", "url": "https://github.com/x/y",
                                  "source_file": "knowledge/docker.md"}) == PROVENANCE_GUIDE


def test_score_dense_nul_ne_disqualifie_pas_un_vrai_depot():
    doc = {**REPO_FASTAPI, "score_dense": 0.0, "injecte_par_termes": True}
    assert determiner_provenance(doc) == PROVENANCE_GITHUB


# --- Liens et enrichissement ---------------------------------------------------

def test_liens_github_pointent_vers_fichier_et_ligne():
    blob, commits = liens_github(REPO_FASTAPI)
    assert blob == "https://github.com/fastapi/fastapi/blob/HEAD/README.md#L42"
    assert commits == "https://github.com/fastapi/fastapi/commits"


def test_pas_de_lien_ni_etoiles_pour_source_non_verifiable():
    for doc in (GUIDE, {**REPO_FASTAPI, "url": "https://github.com/autre/depot"}):
        assert liens_github(doc) == (None, None)
        out = enrichir_document({**doc, "url_blob": "https://github.com/faux", "url_commits": "x"})
        assert out["url"] == ""
        assert out["etoiles"] is None
        assert "url_blob" not in out and "url_commits" not in out


def test_enrichir_document_conserve_les_etoiles_github():
    out = enrichir_document(REPO_FASTAPI)
    assert out["provenance"] == PROVENANCE_GITHUB
    assert out["etoiles"] == 90000
    assert out["citation_courte"] == "[README.md:42]"


def test_bloc_citations_separe_github_et_guides():
    bloc = construire_bloc_citations([REPO_FASTAPI, GUIDE], [], mode_expert=True)
    partie_github, partie_guides = bloc.split("Guides internes")
    assert "fastapi/fastapi" in partie_github
    assert "blob/HEAD/README.md#L42" in partie_github
    assert "enrichissement" not in partie_github
    assert "Routes GET avec FastAPI" in partie_guides
    assert "github.com" not in partie_guides


def test_liens_de_recherche_ne_sont_pas_des_sources():
    from core.constructeur_prompt import ConstructeurPrompt
    from web.ressources import liens_youtube, sources_web_reelles

    page = {"titre": "Docs Docker", "url": "https://docs.docker.com/build/building/multi-stage/"}
    ressources = [page] + liens_youtube("Dockerfile multi-stage")
    assert sources_web_reelles(ressources) == [page]

    bloc = construire_bloc_citations([], ressources)
    web, pistes = bloc.split("Pour aller plus loin")
    assert "docs.docker.com" in web and "youtube.com" not in web
    assert "youtube.com" in pistes and "non consultées" in pistes

    prompt_web = ConstructeurPrompt()._formater_web(liens_youtube("Dockerfile multi-stage"))
    assert prompt_web == "Aucune ressource web."


def test_bloc_citations_sans_github_ne_titre_pas_sources_github():
    bloc = construire_bloc_citations([GUIDE], [{"titre": "Doc", "url": "https://docs.docker.com"}])
    assert "Sources GitHub" not in bloc
    assert "Guides internes" in bloc
    assert "https://docs.docker.com" in bloc


# --- Scores et classement ------------------------------------------------------

class _FauxCrossEncoder:
    def __init__(self, scores):
        self.scores = scores

    def predict(self, paires, **_):
        return np.array(self.scores[: len(paires)], dtype=float)


def test_confiance_issue_du_cross_encoder_seul():
    docs = [dict(REPO_FASTAPI, score_dense=0.0), dict(GUIDE, score_dense=0.9)]
    sortie = reranker_documents(_FauxCrossEncoder([4.0, -6.0]), "route GET", docs, top_k=2)
    assert sortie[0]["nom_complet"] == "fastapi/fastapi"
    assert sortie[0]["score_confiance"] == confiance_cross_encoder(4.0)
    assert sortie[1]["score_confiance"] == confiance_cross_encoder(-6.0)
    assert sortie[0]["score_confiance"] > 0.5 > sortie[1]["score_confiance"]


def test_boosts_ne_modifient_pas_la_confiance():
    docs = [dict(REPO_FASTAPI, score_rerank=1.0, score_confiance=0.6, mis_a_jour_le="2026-06-01"),
            dict(GUIDE, score_rerank=1.0, score_confiance=0.6, mis_a_jour_le="2026-06-01")]
    apres = booster_lexical(
        "route get fastapi", appliquer_fraicheur(docs, 0.2),
        {"fastapi": ["@app.get"]}, {"fastapi": ["fastapi/fastapi"]}, [],
    )
    assert all(d["score_confiance"] == 0.6 for d in apres)
    guide = next(d for d in apres if d.get("source_enrichissement"))
    depot = next(d for d in apres if not d.get("source_enrichissement"))
    assert guide["score_rerank"] <= depot["score_rerank"]


def test_diversification_ne_fait_pas_entrer_de_hors_sujet():
    docs = [
        {"texte": "fastapi route", "nom_complet": "fastapi/fastapi", "score_confiance": 0.9, "score_rerank": 3},
        {"texte": "fastapi get", "nom_complet": "fastapi/fastapi", "score_confiance": 0.85, "score_rerank": 2.5},
        {"texte": "django orm", "nom_complet": "django/django", "score_confiance": 0.2, "score_rerank": 1},
    ]
    _, faibles = separer_par_pertinence(docs)
    assert [d["texte"] for d in faibles] == ["django orm"]
    classes = classer_par_theme(docs, themes_requete=["fastapi"], top_k=2)
    assert all(d["texte"].startswith("fastapi") for d in classes)


def test_injection_prefere_depot_officiel_et_ignore_les_guides():
    chunks = [
        {"texte": "@app.get dans un blog", "nom_complet": "blog/tuto"},
        {"texte": "@app.get guide", "nom_complet": "enrichissement/fastapi", "source_enrichissement": True},
        {"texte": "@app.get('/') officiel", "nom_complet": "fastapi/fastapi",
         "url": "https://github.com/fastapi/fastapi"},
    ]
    out = injecter_hits_termes("route get fastapi", [], chunks, {"fastapi": ["@app.get"]},
                               max_inject=1, repos_preferes={"fastapi": ["fastapi/fastapi"]})
    assert len(out) == 1
    assert out[0]["nom_complet"] == "fastapi/fastapi"
    assert out[0]["injecte_par_termes"] is True
    assert out[0]["score_confiance"] == 0.0


def test_injection_prefere_original_a_traduction():
    texte = "Example Dockerfile for multi-stage builds FROM node AS build COPY --from=build /app ."
    chunks = [
        {"texte": texte, "nom_complet": "goldbergyoni/nodebestpractices", "chemin_fichier": "README.hebrew.md"},
        {"texte": texte, "nom_complet": "goldbergyoni/nodebestpractices", "chemin_fichier": "README.md"},
    ]
    termes = {"docker": ["Dockerfile"], "multi-stage": ["multi-stage", "COPY --from="]}
    out = injecter_hits_termes("dockerfile multi-stage", [], chunks, termes)
    assert [d["source_file"] for d in out] == ["README.md"]


def test_detection_traductions():
    from retrieval.dedup import est_traduction

    for chemin in ("README.hebrew.md", "README.zh-CN.md", "docs/de/docs/index.md", "README_ko.md"):
        assert est_traduction(chemin), chemin
    for chemin in ("README.md", "docs/en/docs/index.md", "CHANGELOG.md", "src/my_db.md"):
        assert not est_traduction(chemin), chemin


# --- Non-régression : 2 questions de référence ---------------------------------

def test_reference_fastapi_route_get():
    analyse = ClassificateurAssistant().analyser("Comment créer une route GET avec FastAPI ?")
    assert analyse.domaine == "fastapi"
    info = reecrire_requete("Comment créer une route GET avec FastAPI ?")
    assert "fastapi" in info.themes


def test_reference_dockerfile_multistage_reste_docker():
    question = "Comment écrire un Dockerfile multi-stage ?"
    assert ClassificateurAssistant().analyser(question).domaine == "docker"
    info = reecrire_requete(question)
    assert "docker" in info.themes
    assert "multi" in info.reecrite.lower() or "stage" in info.reecrite.lower()


def test_reference_dockerfile_python_ne_derive_pas_vers_python():
    info = reecrire_requete("Comment écrire un Dockerfile multi-stage pour une application Python ?")
    assert "docker" in info.themes
    assert ClassificateurAssistant().analyser(
        "Comment écrire un Dockerfile multi-stage pour une application Python ?").domaine == "docker"


# --- Stream + contrôle qualité a posteriori --------------------------------------

class _FauxRetrieval:
    def rechercher(self, question, **_):
        return [dict(REPO_FASTAPI, score_confiance=0.6, section_titre="Example")]

    def doit_sabstenir(self, documents):
        return False


class _FauxLLM:
    temperature = 0.3

    def stream(self, messages, usage_holder=None):
        for morceau in ("Utilisez `@app.get` ", "avec FastAPI :\n```python\n@app.get('/items/{id}')\n```"):
            yield morceau

    def invoke(self, messages):
        raise AssertionError("pas d'appel synchrone en mode stream")


def test_stream_technique_avec_controle_qualite_a_posteriori(tmp_path, monkeypatch):
    from core.journal_amelioration import JournalAmelioration
    from core.memoire_longue import MemoireLongue
    from core.orchestrateur import OrchestrateurAssistant

    monkeypatch.setenv("DESACTIVER_WEB_SEARCH", "true")
    orch = OrchestrateurAssistant(retrieval=_FauxRetrieval(), llm_client=_FauxLLM())
    orch.memoire_longue = MemoireLongue(chemin=tmp_path / "memoire.db")
    orch.journal = JournalAmelioration(chemin=tmp_path / "interactions.jsonl")

    res = orch.repondre("Comment créer une route GET avec FastAPI ?", stream=True)
    assert res.stream is not None
    assert res.rapport_qualite is None
    texte = "".join(res.stream)
    assert "@app.get" in texte
    assert res.reponse_seule == texte.strip()
    assert res.rapport_qualite is not None
    assert res.meta_journal["score_qualite"] == res.rapport_qualite.score
    assert "fastapi/fastapi" in res.citations


# --- BM25 creux ----------------------------------------------------------------

def test_bm25_creux_identique_a_rank_bm25():
    from rank_bm25 import BM25Okapi

    textes = ["fastapi route get app", "docker multi stage build", "fastapi pydantic model",
              "django orm queryset", "docker compose volumes docker", "route get get"]
    corpus = [tokeniser(t) for t in textes]
    ref, creux = BM25Okapi(corpus), BM25Creux.construire(corpus)
    for q in ("fastapi route get", "docker docker stage", "inconnu", "get"):
        np.testing.assert_allclose(creux.get_scores(tokeniser(q)), ref.get_scores(tokeniser(q)), atol=1e-9)


def test_bm25_cache_disque(tmp_path):
    import json

    chunks = [{"texte": t} for t in ("fastapi route get", "docker multi stage", "django orm")]
    fichier = tmp_path / "chunks.json"
    fichier.write_text(json.dumps(chunks), encoding="utf-8")
    cache = tmp_path / "cache"
    c1, idx1 = construire_index_bm25(str(fichier), dossier_cache=cache)
    assert any(cache.iterdir())
    c2, idx2 = construire_index_bm25(str(fichier), dossier_cache=cache)
    assert c1 == c2
    np.testing.assert_allclose(idx1.get_scores(["docker"]), idx2.get_scores(["docker"]))
