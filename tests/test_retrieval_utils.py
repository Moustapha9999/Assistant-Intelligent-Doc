import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.classificateur import ClassificateurAssistant
from core.orchestrateur import OrchestrateurAssistant
from core.schemas import AnalyseQuestion
from retrieval.contexte import compresser_documents, detecter_theme_doc, resumer_chunk
from retrieval.fusion import classer_par_theme
from retrieval.query_rewriter import enrichir_requete, reecrire_requete
from retrieval.retrieval_hybride import RetrievalHybride, _normaliser_confiance


def test_normaliser_confiance_reste_bornee():
    assert 0.0 <= _normaliser_confiance(-100, 0) <= 1.0
    assert 0.0 <= _normaliser_confiance(100, 1) <= 1.0


def test_passe_filtres_sans_charger_les_modeles():
    doc = {
        "langage": "Python", "nom_complet": "tiangolo/fastapi",
        "etoiles": 100, "mis_a_jour_le": "2026-01-01",
    }
    assert RetrievalHybride._passe_filtres(None, doc, {"langage": "Python", "repo": "fastapi", "stars_min": 50})
    assert not RetrievalHybride._passe_filtres(None, doc, {"langage": "Java"})


def test_query_rewriter_enrichit_fastapi():
    info = reecrire_requete("Comment créer une API REST avec FastAPI s'il te plaît ?")
    assert info.intention == "howto"
    assert "fastapi" in info.themes or "fastapi" in info.reecrite.lower()
    assert "FastAPI" in enrichir_requete("Comment créer une API FastAPI ?") or "fastapi" in enrichir_requete(
        "Comment créer une API FastAPI ?"
    ).lower()
    assert len(info.reecrite) >= 10


def test_query_rewriter_detecte_debug():
    info = reecrire_requete("J'ai une erreur JWT traceback NoneType")
    assert info.intention == "debug"
    assert "error" in info.reecrite.lower() or "exception" in info.reecrite.lower()


def test_resumer_chunk_garde_phrases_pertinentes():
    texte = (
        "Introduction générale au web sans intérêt. "
        "FastAPI utilise Pydantic pour valider les requêtes HTTP. "
        "La cuisine française est célèbre dans le monde. "
        "Les dépendances Depends injectent la session de base de données."
    )
    resume = resumer_chunk(texte, requete="FastAPI Pydantic Depends", max_chars=220, max_phrases=2)
    assert "FastAPI" in resume or "Pydantic" in resume or "Depends" in resume
    assert len(resume) <= 240


def test_compresser_documents_ajoute_theme_et_resume():
    docs = [
        {
            "texte": "A" * 1200,
            "nom_complet": "tiangolo/fastapi",
            "section_titre": "Dependencies",
            "score_confiance": 0.8,
        },
        {
            "texte": "Docker compose up builds containers and networks for local stack.",
            "nom_complet": "docker/docs",
            "section_titre": "Compose",
            "score_confiance": 0.7,
        },
    ]
    out = compresser_documents(docs, max_docs=2, max_chars=200, requete="FastAPI Depends", resumer=True)
    assert len(out) == 2
    assert out[0].get("theme")
    assert out[0].get("resume_auto") is True
    assert len(out[0]["texte"]) <= 220


def test_classer_par_theme_diversifie():
    docs = [
        {"texte": "fastapi endpoint pydantic", "nom_complet": "tiangolo/fastapi", "score_rerank": 0.9},
        {"texte": "fastapi depends injection", "nom_complet": "tiangolo/fastapi", "score_rerank": 0.85},
        {"texte": "docker compose volumes", "nom_complet": "docker/docs", "score_rerank": 0.8},
        {"texte": "react useState hook", "nom_complet": "facebook/react", "score_rerank": 0.75},
    ]
    classes = classer_par_theme(docs, themes_requete=["fastapi"], top_k=3, diversifier=True)
    themes = {d["theme"] for d in classes}
    assert "fastapi" in themes
    assert len(classes) == 3


def test_detecter_theme_doc():
    assert detecter_theme_doc({"texte": "use JWT bearer token", "nom_complet": "jpadilla/pyjwt"}) == "jwt"


def test_orchestrateur_choisit_rag_sans_web_technique_simple():
    analyse = AnalyseQuestion(
        mode="technique",
        domaine="fastapi",
        complexite="simple",
        besoin_rag=True,
        besoin_web=True,
    )
    rag, web = OrchestrateurAssistant._choisir_sources_initial(None, analyse, "Comment créer un endpoint FastAPI ?")
    assert rag is True
    assert web is False


def test_orchestrateur_force_web_si_actualite():
    analyse = AnalyseQuestion(
        mode="technique",
        domaine="fastapi",
        complexite="simple",
        besoin_rag=True,
        besoin_web=False,
    )
    rag, web = OrchestrateurAssistant._choisir_sources_initial(
        None, analyse, "Quelle est la dernière version FastAPI 2026 ?"
    )
    assert rag is True
    assert web is True


def test_classificateur_strategie_sources_technique_simple():
    analyse = ClassificateurAssistant().analyser("Comment créer un endpoint FastAPI avec Pydantic ?")
    assert analyse.mode == "technique"
    assert analyse.besoin_rag is True
    assert analyse.strategie_sources in {"rag", "hybride"}


def test_orchestrateur_projet_metier_sans_rag_ni_web():
    analyse = AnalyseQuestion(
        mode="projet",
        domaine="general",
        complexite="complexe",
        besoin_rag=False,
        besoin_web=False,
    )
    rag, web = OrchestrateurAssistant._choisir_sources_initial(
        None, analyse, "Créer une plateforme de gestion pour une quincaillerie"
    )
    assert rag is False
    assert web is False


def test_filtrer_docs_fiables_rejette_hors_sujet():
    docs = [
        {
            "nom_complet": "vercel/next.js",
            "texte": "write a guide skill for agents",
            "section_titre": "SKILL.md",
            "score_confiance": 0.41,
        },
        {
            "nom_complet": "tiangolo/fastapi",
            "texte": "créer une route FastAPI avec pydantic",
            "section_titre": "First steps",
            "score_confiance": 0.72,
        },
    ]
    fiables = OrchestrateurAssistant._filtrer_docs_fiables(
        docs, question="Comment créer une route FastAPI ?"
    )
    assert len(fiables) == 1
    assert fiables[0]["nom_complet"] == "tiangolo/fastapi"
