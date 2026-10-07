"""
Figure 4.5 — Distribution des chunks par langage (barres horizontales).
Source : docs/figures_chap4/eda_chunks_par_langage.csv
Sortie : docs/figures_chap4/figure_4_5_distribution_langages.png
"""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib as mpl

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "docs" / "figures_chap4" / "eda_chunks_par_langage.csv"
OUT = ROOT / "docs" / "figures_chap4" / "figure_4_5_distribution_langages.png"

TOP_N = 10
COULEUR = "#2E5FA3"


def _charger_top_langages(chemin: Path, n: int) -> tuple[list[str], list[int]]:
    if not chemin.exists():
        raise FileNotFoundError(
            f"{chemin} introuvable — lancez d'abord : python scripts/export_eda_memoire.py"
        )
    langages: list[str] = []
    chunks: list[int] = []
    with chemin.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            langages.append(row["langage"].strip())
            chunks.append(int(row["nb_chunks"]))
            if len(langages) >= n:
                break
    return langages, chunks


def _fmt_nombre(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def generer(chemin_csv: Path = CSV, chemin_sortie: Path = OUT) -> Path:
    langages, chunks = _charger_top_langages(chemin_csv, TOP_N)

    mpl.rcParams["font.family"] = "DejaVu Sans"
    fig, ax = plt.subplots(figsize=(12, 7))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    y_labels = langages[::-1]
    valeurs = chunks[::-1]
    bars = ax.barh(y_labels, valeurs, color=COULEUR, height=0.6)

    for bar, val in zip(bars, valeurs):
        ax.text(
            bar.get_width() + 300,
            bar.get_y() + bar.get_height() / 2,
            _fmt_nombre(val),
            va="center",
            ha="left",
            fontsize=10,
        )

    ax.set_xlabel("Nombre de chunks", fontsize=11)
    ax.set_xlim(0, 42_000)
    ax.set_title(
        "Distribution des chunks par langage de programmation",
        fontsize=13,
        fontweight="bold",
        pad=15,
    )
    ax.text(
        0.5,
        -0.08,
        "Corpus AssistDoc — 144 701 chunks, 26 langages, juillet 2026",
        ha="center",
        transform=ax.transAxes,
        fontsize=9,
        color="gray",
    )
    ax.xaxis.grid(True, linestyle="--", alpha=0.3)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="y", labelsize=11)

    chemin_sortie.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(chemin_sortie, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return chemin_sortie


if __name__ == "__main__":
    out = generer()
    print(f"Figure générée : {out}")
