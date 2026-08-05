"""
Exporte les statistiques EDA du corpus pour le mémoire (chap. 4).
Sorties dans docs/figures_chap4/
"""
from __future__ import annotations

import csv
import json
import statistics as st
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHUNKS = ROOT / "data" / "processed" / "chunks" / "tous_chunks.json"
REPOS = ROOT / "data" / "raw" / "repos_selectionnes.yaml"
RAW_READMES = ROOT / "data" / "raw" / "readmes"
OUT = ROOT / "docs" / "figures_chap4"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"Chargement {CHUNKS} ...")
    chunks = json.loads(CHUNKS.read_text(encoding="utf-8"))
    repos = yaml.safe_load(REPOS.read_text(encoding="utf-8")) if REPOS.exists() else []

    langs = Counter((c.get("langage") or "Inconnu") for c in chunks)
    types = Counter((c.get("type_chunk") or "inconnu") for c in chunks)
    repos_chunks = {c.get("nom_complet") for c in chunks if c.get("nom_complet")}

    lens = [len(c.get("texte") or "") for c in chunks]
    words = [len((c.get("texte") or "").split()) for c in chunks]

    fs: dict[tuple, int] = defaultdict(int)
    for c in chunks:
        key = (c.get("nom_complet"), c.get("chemin_fichier"))
        fs[key] += len(c.get("texte") or "")
    file_lens = list(fs.values())

    # --- CSV langages ---
    path_lang = OUT / "eda_chunks_par_langage.csv"
    with path_lang.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["rang", "langage", "nb_chunks", "pourcentage"])
        total = len(chunks)
        for i, (lang, n) in enumerate(langs.most_common(), 1):
            w.writerow([i, lang, n, f"{100 * n / total:.2f}"])

    # --- CSV types ---
    path_types = OUT / "eda_chunks_par_type.csv"
    with path_types.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["type_chunk", "nb_chunks", "pourcentage"])
        for t, n in types.most_common():
            w.writerow([t, n, f"{100 * n / total:.2f}"])

    # --- CSV tailles ---
    path_sizes = OUT / "eda_tailles_resume.csv"
    with path_sizes.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["metrique", "valeur"])
        rows = [
            ("nb_chunks", len(chunks)),
            ("nb_langages", len(langs)),
            ("nb_repos_selectionnes", len(repos)),
            ("nb_repos_dans_chunks", len(repos_chunks)),
            ("nb_fichiers", len(file_lens)),
            ("chars_moyenne", round(st.mean(lens), 1)),
            ("chars_mediane", round(st.median(lens), 1)),
            ("chars_p25", round(st.quantiles(lens, n=4)[0], 1)),
            ("chars_p75", round(st.quantiles(lens, n=4)[2], 1)),
            ("tokens_approx_moyenne_chars_div4", round(st.mean(lens) / 4, 1)),
            ("mots_moyenne", round(st.mean(words), 1)),
            ("mots_mediane", round(st.median(words), 1)),
            ("fichier_chars_moyenne", round(st.mean(file_lens), 1)),
            ("fichier_chars_mediane", round(st.median(file_lens), 1)),
        ]
        for k, v in rows:
            w.writerow([k, v])

    # --- Période scrape ---
    scrape_debut = scrape_fin = None
    if RAW_READMES.exists():
        mtimes = [
            p.stat().st_mtime
            for p in RAW_READMES.iterdir()
            if p.is_file() and p.name != "_recap_scraping.yaml"
        ]
        if mtimes:
            scrape_debut = datetime.fromtimestamp(min(mtimes)).strftime("%Y-%m-%d")
            scrape_fin = datetime.fromtimestamp(max(mtimes)).strftime("%Y-%m-%d")

    sources = Counter((r.get("source") or "?") for r in repos)
    stars = [int(r.get("etoiles") or 0) for r in repos] or [0]

    top10 = langs.most_common(10)
    md = f"""# EDA corpus — export pour le mémoire (chap. 4)

Généré le : {datetime.now().isoformat(timespec="seconds")}

## Synthèse

| Indicateur | Valeur |
|---|---:|
| Repos sélectionnés | {len(repos)} ({sources.get('force', 0)} forcés + {sources.get('auto', 0)} auto) |
| Chunks | {len(chunks):,} |
| Langages | {len(langs)} |
| Fichiers sources | {len(file_lens):,} |
| Collecte GitHub (fichiers locaux) | {scrape_debut} → {scrape_fin} |
| Étoiles (sélection) min / médiane / max | {min(stars):,} / {sorted(stars)[len(stars)//2]:,} / {max(stars):,} |

## Critères de sélection (rappel)

- `min_stars` : 500 (recherche auto)
- Langages ciblés : Python, JavaScript, TypeScript, Java, Go, Rust, C, C++, SQL
- Max 10 repos auto / langage, `pushed` < 24 mois
- README obligatoire, exclusion forks / archives
- Liste curatée `repos_forces` + complément auto

## Top 10 langages (chunks)

| Rang | Langage | Chunks | % |
|---:|---|---:|---:|
"""
    for i, (lang, n) in enumerate(top10, 1):
        md += f"| {i} | {lang} | {n:,} | {100 * n / total:.2f} % |\n"

    md += f"""
## Tailles

- Chunk : moyenne **{st.mean(lens):.0f}** caractères (~**{st.mean(lens)/4:.0f}** tokens), médiane **{st.median(lens):.0f}**
- Chunk : moyenne **{st.mean(words):.0f}** mots, médiane **{st.median(words):.0f}**
- Fichier (somme des chunks) : moyenne **{st.mean(file_lens):.0f}** car., médiane **{st.median(file_lens):.0f}**

## Fichiers générés

- `{path_lang.name}`
- `{path_types.name}`
- `{path_sizes.name}`
- `figure_4_2_accueil.png` / `figure_4_3_reponse_sources.png` (si générées)
"""
    path_md = OUT / "eda_resume_pour_claude.md"
    path_md.write_text(md, encoding="utf-8")
    print(f"OK -> {OUT}")
    print(f"  - {path_lang.name}")
    print(f"  - {path_types.name}")
    print(f"  - {path_sizes.name}")
    print(f"  - {path_md.name}")


if __name__ == "__main__":
    main()
