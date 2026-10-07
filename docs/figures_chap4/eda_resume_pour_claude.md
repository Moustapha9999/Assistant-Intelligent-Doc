# EDA corpus — export pour le mémoire (chap. 4)

Généré le : 2026-09-01T12:21:03

## Synthèse

| Indicateur | Valeur |
|---|---:|
| Repos sélectionnés | 317 (235 forcés + 82 auto) |
| Chunks | 144,018 |
| Langages | 26 |
| Fichiers sources | 16,623 |
| Collecte GitHub (fichiers locaux) | 2026-03-28 → 2026-06-12 |
| Étoiles (sélection) min / médiane / max | 12 / 43,312 / 446,620 |

## Critères de sélection (rappel)

- `min_stars` : 500 (recherche auto)
- Langages ciblés : Python, JavaScript, TypeScript, Java, Go, Rust, C, C++, SQL
- Max 10 repos auto / langage, `pushed` < 24 mois
- README obligatoire, exclusion forks / archives
- Liste curatée `repos_forces` + complément auto

## Top 10 langages (chunks)

| Rang | Langage | Chunks | % |
|---:|---|---:|---:|
| 1 | Python | 35,797 | 24.86 % |
| 2 | Go | 24,285 | 16.86 % |
| 3 | TypeScript | 18,273 | 12.69 % |
| 4 | JavaScript | 12,626 | 8.77 % |
| 5 | Rust | 10,213 | 7.09 % |
| 6 | C++ | 9,772 | 6.79 % |
| 7 | Jupyter Notebook | 9,279 | 6.44 % |
| 8 | Java | 6,047 | 4.20 % |
| 9 | C | 5,092 | 3.54 % |
| 10 | Laravel | 3,058 | 2.12 % |

## Tailles

- Chunk : moyenne **987** caractères (~**247** tokens), médiane **526**
- Chunk : moyenne **104** mots, médiane **57**
- Fichier (somme des chunks) : moyenne **8555** car., médiane **2759**

## Fichiers générés

- `eda_chunks_par_langage.csv`
- `eda_chunks_par_type.csv`
- `eda_tailles_resume.csv`
- `figure_4_5_distribution_langages.png` (si générée)
