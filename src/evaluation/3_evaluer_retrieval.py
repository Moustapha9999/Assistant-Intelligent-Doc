"""Évalue les ablations du moteur de récupération hybride."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SRC_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = SRC_DIR.parent
sys.path.insert(0, str(SRC_DIR))

from evaluation.jeux_questions import JEUX_QUESTIONS
from retrieval.retrieval_hybride import RetrievalHybride


ABLATIONS = [
    ("dense_sans_rerank", "dense", False),
    ("dense_avec_rerank", "dense", True),
    ("bm25_sans_rerank", "bm25", False),
    ("bm25_avec_rerank", "bm25", True),
    ("hybride_sans_rerank", "hybride", False),
    ("hybride_avec_rerank", "hybride", True),
]

BASELINE_REF = {
    "dense_sans_rerank": {"precision_at_k": 0.3846, "mrr": 0.3147},
    "dense_avec_rerank": {"precision_at_k": 0.3846, "mrr": 0.3750},
    "bm25_sans_rerank": {"precision_at_k": 0.7308, "mrr": 0.5186},
    "bm25_avec_rerank": {"precision_at_k": 0.7500, "mrr": 0.6106},
    "hybride_sans_rerank": {"precision_at_k": 0.7308, "mrr": 0.5103},
    "hybride_avec_rerank": {"precision_at_k": 0.7885, "mrr": 0.6218},
}


def rang_pertinent(documents: list[dict[str, Any]], mots_cles: list[str]) -> int | None:
    """Retourne le premier rang contenant un mot-clé attendu."""
    attendus = [mot.lower() for mot in mots_cles]
    for rang, doc in enumerate(documents, start=1):
        texte = f"{doc.get('texte', '')} {doc.get('nom_complet', '')} {doc.get('theme', '')}".lower()
        if any(mot in texte for mot in attendus):
            return rang
    return None


def evaluer(top_k: int, limit: int) -> dict[str, Any]:
    questions = JEUX_QUESTIONS[:limit] if limit else JEUX_QUESTIONS
    moteur = RetrievalHybride()
    resultats: dict[str, Any] = {
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "top_k": top_k,
        "nombre_questions": len(questions),
        "pipeline": "rewrite+theme+compression+hybride",
        "ablations": {},
    }
    for nom, mode, avec_rerank in ABLATIONS:
        print(f"\n=== Ablation {nom} ===")
        details, hits, mrr_total = [], 0, 0.0
        for i, item in enumerate(questions, 1):
            docs = moteur.rechercher(
                item["question"],
                top_k_retrieval=max(20, top_k * 4),
                top_k_final=top_k,
                mode=mode,
                avec_rerank=avec_rerank,
            )
            rang = rang_pertinent(docs, item["mots_cles"])
            hits += rang is not None
            mrr_total += 1 / rang if rang else 0
            details.append({
                "id": item["id"],
                "techno": item["techno"],
                "rang": rang,
                "hit": rang is not None,
                "themes": [d.get("theme") for d in docs if d.get("theme")],
            })
            if i % 10 == 0 or i == len(questions):
                print(f"   {i}/{len(questions)} | hits={hits} | MRR_partiel={mrr_total / i:.4f}")
        total = len(questions) or 1
        resultats["ablations"][nom] = {
            "mode": mode,
            "avec_rerank": avec_rerank,
            "precision_at_k": round(hits / total, 4),
            "mrr": round(mrr_total / total, 4),
            "details": details,
        }
    return resultats


def _delta(actuel: float, base: float) -> str:
    d = actuel - base
    signe = "+" if d >= 0 else ""
    return f"{signe}{d:.4f}"


def rapport_markdown(resultats: dict[str, Any], baseline: dict[str, Any] | None = None) -> str:
    base = baseline or BASELINE_REF
    lignes = [
        "# Rapport d'évaluation du retrieval",
        "",
        f"Généré le : {resultats['date_utc']}",
        f"Questions : {resultats['nombre_questions']} · k = {resultats['top_k']}",
        f"Pipeline : `{resultats.get('pipeline', 'n/a')}`",
        "",
        "| Ablation | Precision@k | MRR | Δ Prec. vs baseline | Δ MRR vs baseline |",
        "|---|---:|---:|---:|---:|",
    ]
    for nom, mesures in resultats["ablations"].items():
        b = base.get(nom, {})
        bp = float(b.get("precision_at_k", 0))
        bm = float(b.get("mrr", 0))
        lignes.append(
            f"| {nom} | {mesures['precision_at_k']:.2%} | {mesures['mrr']:.4f} | "
            f"{_delta(mesures['precision_at_k'], bp)} | {_delta(mesures['mrr'], bm)} |"
        )
    lignes += [
        "",
        "## Méthode",
        "Un hit est compté lorsqu'au moins un mot-clé attendu apparaît dans le texte, "
        "le dépôt ou le thème d'un document retourné. "
        "Le MRR utilise le rang du premier hit ; cette mesure évalue donc le retrieval "
        "et non la qualité de génération.",
        "",
        "## Baseline",
        "Comparaison avec le rapport du 2026-07-16 (avant rewrite intelligent / "
        "classement thématique / compression contextuelle renforcée).",
        "",
        "## Lecture rapide",
        "- `hybride_avec_rerank` reste la configuration de référence pour la prod.",
        "- Un Δ positif indique un gain ; un Δ négatif un recul à investiguer.",
    ]
    return "\n".join(lignes) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--limit", type=int, default=0, help="0 évalue toutes les questions")
    args = parser.parse_args()
    resultats = evaluer(args.top_k, args.limit)
    docs = ROOT_DIR / "docs"
    docs.mkdir(exist_ok=True)

    # Conserve l'ancien rapport comme baseline si présent
    prev_path = docs / "rapport_evaluation.json"
    baseline = None
    if prev_path.exists():
        try:
            prev = json.loads(prev_path.read_text(encoding="utf-8"))
            baseline = {
                nom: {
                    "precision_at_k": vals.get("precision_at_k", 0),
                    "mrr": vals.get("mrr", 0),
                }
                for nom, vals in (prev.get("ablations") or {}).items()
            }
            (docs / "rapport_evaluation_baseline.json").write_text(
                json.dumps(prev, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            baseline = None

    (docs / "rapport_evaluation.json").write_text(
        json.dumps(resultats, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (docs / "rapport_evaluation.md").write_text(
        rapport_markdown(resultats, baseline=baseline),
        encoding="utf-8",
    )
    print(f"Rapports écrits dans {docs}")
    for nom, m in resultats["ablations"].items():
        print(f"  {nom}: P@k={m['precision_at_k']:.2%} MRR={m['mrr']:.4f}")


if __name__ == "__main__":
    main()
