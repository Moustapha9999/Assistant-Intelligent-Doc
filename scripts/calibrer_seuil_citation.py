"""
Calibration du seuil de citation (_SEUIL_CITATION_MIN) sur le jeu de 52 questions.

Pour chaque document final (top-k, pipeline de production), on enregistre sa confiance
(cross-encoder) et sa pertinence stricte (provenance GitHub + ≥ 2 mots-clés attendus).
Le seuil est choisi sur une moitié des technologies et vérifié sur l'autre moitié
(validation croisée à 2 plis), pour ne pas sur-ajuster les 52 questions.

Usage :
    python scripts/calibrer_seuil_citation.py --sortie logs/calibration_seuil.json
    python scripts/calibrer_seuil_citation.py --depuis logs/calibration_seuil.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

SEUILS = [round(0.20 + 0.025 * i, 3) for i in range(13)]  # 0.20 → 0.50


def collecter(top_k: int) -> list[dict]:
    from core.orchestrateur import OrchestrateurAssistant
    from evaluation.jeux_questions import JEUX_QUESTIONS
    from retrieval.citations import determiner_provenance, enrichir_document
    from retrieval.retrieval_hybride import RetrievalHybride

    moteur = RetrievalHybride()
    lignes = []
    for item in JEUX_QUESTIONS:
        docs = [enrichir_document(d) for d in moteur.rechercher(item["question"], top_k_final=top_k)]
        attendus = [m.lower() for m in item["mots_cles"]]
        besoin = min(2, len(attendus))
        for rang, d in enumerate(docs, 1):
            texte = str(d.get("texte_brut") or d.get("texte") or "").lower()
            garde_045 = bool(OrchestrateurAssistant._filtrer_docs_fiables([d], question=item["question"], seuil=0.0))
            lignes.append({
                "id": item["id"],
                "techno": item["techno"],
                "rang": rang,
                "confiance": float(d.get("score_confiance") or 0),
                "provenance": determiner_provenance(d),
                "pertinent_strict": determiner_provenance(d) == "github"
                and sum(1 for m in attendus if m in texte) >= besoin,
                "passe_filtre_lexical": garde_045,
            })
    return lignes


def evaluer_seuil(lignes: list[dict], seuil: float) -> dict:
    gardes = [l for l in lignes if l["confiance"] >= seuil and l["passe_filtre_lexical"]]
    questions = {l["id"] for l in lignes}
    q_avec_doc = {l["id"] for l in gardes}
    q_avec_pertinent = {l["id"] for l in gardes if l["pertinent_strict"]}
    pertinents = sum(l["pertinent_strict"] for l in gardes)
    return {
        "seuil": seuil,
        "docs_gardes": len(gardes),
        "precision_docs_gardes": round(pertinents / len(gardes), 4) if gardes else None,
        "part_non_github_gardes": round(sum(l["provenance"] != "github" for l in gardes) / len(gardes), 4) if gardes else None,
        "questions_avec_doc": len(q_avec_doc),
        "questions_avec_doc_pertinent": len(q_avec_pertinent),
        "questions_sans_doc": len(questions) - len(q_avec_doc),
    }


def choisir(lignes: list[dict], plancher_precision: float) -> float:
    """Plus petit seuil dont la précision des docs gardés reste ≥ plancher (couverture max)."""
    candidats = [s for s in SEUILS if (evaluer_seuil(lignes, s)["precision_docs_gardes"] or 0) >= plancher_precision]
    return min(candidats) if candidats else max(SEUILS)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--sortie", default=str(ROOT / "logs" / "calibration_seuil.json"))
    p.add_argument("--depuis", default="", help="Réutilise une collecte existante (pas de recherche)")
    args = p.parse_args()

    if args.depuis:
        lignes = json.loads(Path(args.depuis).read_text(encoding="utf-8"))["lignes"]
    else:
        lignes = collecter(args.top_k)

    courbe = [evaluer_seuil(lignes, s) for s in SEUILS]
    reference = evaluer_seuil(lignes, 0.45)
    plancher = reference["precision_docs_gardes"] or 0.0

    technos = sorted({l["techno"] for l in lignes})
    plis = [set(technos[0::2]), set(technos[1::2])]
    validation = []
    for i, train in enumerate(plis):
        test = plis[1 - i]
        l_train = [l for l in lignes if l["techno"] in train]
        l_test = [l for l in lignes if l["techno"] in test]
        s = choisir(l_train, evaluer_seuil(l_train, 0.45)["precision_docs_gardes"] or 0.0)
        validation.append({
            "pli": i, "seuil_choisi": s,
            "test_seuil_choisi": evaluer_seuil(l_test, s),
            "test_seuil_045": evaluer_seuil(l_test, 0.45),
        })

    sortie = {
        "methode": "pertinence stricte = provenance GitHub + ≥2 mots-clés ; filtre lexical de l'orchestrateur conservé",
        "plancher_precision_045": plancher,
        "seuil_global_meme_precision": choisir(lignes, plancher),
        "courbe": courbe,
        "validation_croisee": validation,
        "lignes": lignes,
    }
    Path(args.sortie).write_text(json.dumps(sortie, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in sortie.items() if k != "lignes"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
