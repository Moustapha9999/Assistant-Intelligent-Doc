"""
Figure 4.10 / Figure 10 — Performance système vs objectifs RAGAS.
Sortie : docs/figures_chap4/figure_4_10_performance_objectifs.png
"""
from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "figures_chap4" / "figure_4_10_performance_objectifs.png"

METRIQUES = ["Faithfulness", "Answer\nRelevancy", "Context\nPrecision", "Context\nRecall"]
CIBLES = [0.90, 0.80, 0.80, 0.75]
RESULTATS = [0.95, 0.72, 1.00, 1.00]

COULEUR_CIBLE = "#A0A0A0"
COULEUR_RESULTAT = "#2E5FA3"


def generer(chemin_sortie: Path = OUT) -> Path:
    mpl.rcParams["font.family"] = "DejaVu Sans"
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    x = np.arange(len(METRIQUES))
    width = 0.35

    bars_cible = ax.bar(
        x - width / 2, CIBLES, width, label="Cible", color=COULEUR_CIBLE
    )
    bars_resultat = ax.bar(
        x + width / 2, RESULTATS, width, label="Résultat", color=COULEUR_RESULTAT
    )

    for bar in bars_cible:
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.01,
            f"{bar.get_height():.2f}",
            ha="center",
            va="bottom",
            fontsize=10,
        )
    for bar in bars_resultat:
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.01,
            f"{bar.get_height():.2f}",
            ha="center",
            va="bottom",
            fontsize=10,
        )

    ax.set_ylim(0, 1.15)
    ax.set_ylabel("Score", fontsize=11)
    ax.set_xticks(x)
    ax.set_xticklabels(METRIQUES, fontsize=11)
    ax.set_title(
        "Performance système vs objectifs fixés",
        fontsize=13,
        fontweight="bold",
        pad=15,
    )
    ax.text(
        0.5,
        -0.12,
        "Évaluation RAGAS — Corpus AssistDoc, juillet 2026",
        ha="center",
        transform=ax.transAxes,
        fontsize=9,
        color="gray",
    )
    ax.legend(fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.axhline(y=1.0, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)

    chemin_sortie.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(chemin_sortie, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return chemin_sortie


if __name__ == "__main__":
    out = generer()
    print(f"Figure générée : {out}")
