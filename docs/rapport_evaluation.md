# Rapport d'évaluation du retrieval

Généré le : 2026-07-16T15:11:53.651325+00:00
Questions : 52 · k = 5
Pipeline : `rewrite+theme+compression+hybride`

| Ablation | Precision@k | MRR | Δ Prec. vs baseline | Δ MRR vs baseline |
|---|---:|---:|---:|---:|
| dense_sans_rerank | 46.15% | 0.3917 | +0.0769 | +0.0770 |
| dense_avec_rerank | 46.15% | 0.4375 | +0.0769 | +0.0625 |
| bm25_sans_rerank | 88.46% | 0.6641 | +0.1538 | +0.1455 |
| bm25_avec_rerank | 90.38% | 0.7721 | +0.1538 | +0.1615 |
| hybride_sans_rerank | 88.46% | 0.6240 | +0.1538 | +0.1137 |
| hybride_avec_rerank | 90.38% | 0.7689 | +0.1153 | +0.1471 |

## Méthode
Un hit est compté lorsqu'au moins un mot-clé attendu apparaît dans le texte, le dépôt ou le thème d'un document retourné. Le MRR utilise le rang du premier hit ; cette mesure évalue donc le retrieval et non la qualité de génération.

## Baseline
Comparaison avec le rapport du 2026-07-16 (avant rewrite intelligent / classement thématique / compression contextuelle renforcée).

## Lecture rapide
- `hybride_avec_rerank` reste la configuration de référence pour la prod.
- Un Δ positif indique un gain ; un Δ négatif un recul à investiguer.
