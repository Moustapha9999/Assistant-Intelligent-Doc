"""
Trace étape par étape du pipeline RAG (sans appel LLM).

Reproduit RetrievalHybride.rechercher() puis les décisions de l'orchestrateur
pour localiser l'étape où les documents disparaissent.

Usage :
    python scripts/tracer_pipeline.py
    python scripts/tracer_pipeline.py "Ma question" "Autre question"
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from core.orchestrateur import OrchestrateurAssistant, _SEUIL_CITATION_MIN  # noqa: E402
from retrieval.citations import enrichir_document  # noqa: E402
from retrieval.contexte import compresser_documents  # noqa: E402
from retrieval.dedup import dedupliquer_documents  # noqa: E402
from retrieval.fusion import classer_par_theme  # noqa: E402
from retrieval.query_rewriter import fusionner_requetes  # noqa: E402

QUESTIONS_REFERENCE = [
    "Comment créer une route GET avec FastAPI ?",
    "Comment écrire un Dockerfile multi-stage ?",
    "Comment écrire un Dockerfile multi-stage pour une application Python ?",
]


def _id(doc: dict) -> str:
    src = doc.get("source_file") or doc.get("chemin_fichier") or "?"
    return f"{doc.get('nom_complet', '?')}:{src}"


def _resume(docs: list, n: int = 8, cles=("score_dense", "score_bm25", "score_final", "score_rerank", "score_confiance")) -> list:
    out = []
    for d in docs[:n]:
        out.append({"id": _id(d), **{k: round(float(d.get(k) or 0), 4) for k in cles}})
    return out


def _raison_rejet(doc: dict, question: str, seuil: float) -> str | None:
    """Miroir de OrchestrateurAssistant._filtrer_docs_fiables, avec la raison."""
    import re

    tokens = {
        t
        for t in re.findall(r"[a-zàâçéèêëîïôùûü0-9_]{4,}", (question or "").lower())
        if t not in {
            "avec", "pour", "dans", "une", "des", "les", "comment",
            "quoi", "fait", "faire", "aide", "créer", "creer", "projet",
        }
    }
    score = float(doc.get("score_confiance") or 0)
    if score < seuil:
        return f"score_confiance {score:.3f} < seuil {seuil}"
    if tokens:
        hay = " ".join(
            str(doc.get(k) or "") for k in ("texte", "nom_complet", "section_titre", "source_file", "theme")
        ).lower()
        if not any(tok in hay for tok in tokens) and score < 0.70:
            return "aucun mot de la question dans le document et score < 0.70"
    return None


def tracer(orch: OrchestrateurAssistant, question: str, top_k: int = 5) -> dict:
    r = orch.retrieval
    trace: dict = {"question": question, "etapes": {}, "temps_ms": {}}

    def chrono(nom, fn):
        t0 = time.perf_counter()
        res = fn()
        trace["temps_ms"][nom] = round((time.perf_counter() - t0) * 1000, 1)
        return res

    analyse = chrono("classification", lambda: orch.classificateur.analyser(question=question, a_un_fichier=False))
    faire_rag, faire_web = orch._choisir_sources_initial(analyse, question)
    trace["etapes"]["0_decision_initiale"] = {
        "mode": analyse.mode, "domaine": analyse.domaine, "complexite": analyse.complexite,
        "faire_rag": faire_rag, "faire_web": faire_web,
    }

    info = chrono("rewrite", lambda: r._reecrire_requete(question))
    requete = fusionner_requetes(info.reecrite, info.variantes)
    requete_dense = question if r.requete_dense == "originale" else requete
    requete_ce = question if r.requete_rerank == "originale" else requete
    trace["etapes"]["1_rewrite"] = {
        "reecrite": info.reecrite, "requete_bm25": requete, "requete_dense": requete_dense,
        "requete_rerank": requete_ce, "themes": info.themes,
    }

    dense = chrono("dense", lambda: r._recherche_dense(requete_dense, top_k=20))
    trace["etapes"]["2_dense"] = {"nb": len(dense), "seuil_qdrant": r.score_threshold, "top": _resume(dense, cles=("score_dense",))}

    bm25 = chrono("bm25", lambda: r._recherche_bm25(requete, top_k=20))
    trace["etapes"]["3_bm25"] = {"nb": len(bm25), "top": _resume(bm25, cles=("score_bm25",))}

    fusion = chrono("rrf", lambda: r._fusionner_rrf(dense, bm25))
    communs = {_id(d) for d in dense} & {_id(d) for d in bm25}
    trace["etapes"]["4_rrf"] = {"nb_uniques": len(fusion), "communs_dense_bm25": len(communs)}

    fusion = dedupliquer_documents(fusion)
    avant_inj = {_id(d) for d in fusion}
    fusion = r._injecter_hits_termes(question, fusion)
    injectes = [d for d in fusion if _id(d) not in avant_inj]
    trace["etapes"]["5_injection_termes"] = {"nb_apres": len(fusion), "injectes": [_id(d) for d in injectes]}

    cands = chrono("rerank", lambda: r._reranker(requete_ce, fusion, top_k=max(top_k * 4, 20)))
    trace["etapes"]["6_rerank"] = {
        "nb": len(cands),
        "top": _resume(cands, cles=("score_dense", "score_bm25", "score_ce", "score_confiance")),
    }

    cands = r._booster_lexical(question, cands)
    trace["etapes"]["7_boost_lexical"] = {
        "top": [{**x, "boost": round(float(d.get("boost_lexical") or 0), 3)} for x, d in zip(_resume(cands), cands)]
    }
    cands = r._appliquer_fraicheur(cands)
    cands = classer_par_theme(cands, themes_requete=info.themes, top_k=max(top_k * 2, top_k), diversifier=True)
    finaux = compresser_documents(cands, max_docs=top_k, max_chars=900, requete=question, resumer=True, diversifier_themes=True)
    trace["etapes"]["8_theme_compression"] = {"nb": len(finaux), "top": _resume(finaux)}

    docs = [enrichir_document(d) for d in finaux]
    gardes, rejetes = [], []
    for d in docs:
        raison = _raison_rejet(d, question, _SEUIL_CITATION_MIN)
        (rejetes if raison else gardes).append((d, raison))
    trace["etapes"]["9_filtre_orchestrateur"] = {
        "seuil": _SEUIL_CITATION_MIN,
        "conserves": [_id(d) for d, _ in gardes],
        "rejetes": [{"id": _id(d), "raison": raison} for d, raison in rejetes],
    }

    documents = [d for d, _ in gardes]
    web_final = orch._ajuster_web_apres_rag(analyse, question, documents, faire_web)
    trace["etapes"]["10_contexte_final"] = {
        "docs_transmis_llm": [_id(d) for d in documents],
        "recherche_web": web_final,
        "web_remplace_corpus": web_final and not documents,
    }
    trace["etapes"]["11_citations"] = [
        {"id": _id(d), "url": d.get("url_blob") or d.get("url"), "etoiles": d.get("etoiles"),
         "provenance": d.get("provenance", "non renseignée")}
        for d in documents
    ]
    return trace


def main() -> None:
    questions = sys.argv[1:] or QUESTIONS_REFERENCE
    t0 = time.perf_counter()
    orch = OrchestrateurAssistant()
    print(f"\n[chargement] {time.perf_counter() - t0:.1f}s")
    traces = [tracer(orch, q) for q in questions]
    sortie = ROOT / "logs" / "trace_pipeline.json"
    sortie.parent.mkdir(exist_ok=True)
    sortie.write_text(json.dumps(traces, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(traces, ensure_ascii=False, indent=2))
    print(f"\nTrace écrite dans {sortie}")


if __name__ == "__main__":
    main()
