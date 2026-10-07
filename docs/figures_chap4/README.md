# Dossier mémoire — Chapitres 4 & 5 (AssistDoc)

Document de synthèse factuelle extrait du dépôt le **2026-07-26**.  
À coller / joindre à Claude pour rédiger les chapitres 4 et 5.

---

## 1. Chiffres corpus à citer

| Indicateur | Valeur | Source |
|---|---:|---|
| Repos sélectionnés | **317** (235 forcés + 82 auto) | `data/raw/repos_selectionnes.yaml` |
| Points Qdrant (`github_docs`) | **144 701** | Qdrant live, status green |
| Chunks fichier local | **144 018** | `data/processed/chunks/tous_chunks.json` |
| Langages distincts | **26** | chunks |
| Fichiers sources | **16 623** | chunks |
| Repos uniques dans les chunks | **415** | sélection + enrichissement |

> Pour le mémoire : privilégier **317 repos** + **144 701 chunks** (Qdrant = corpus indexé).  
> L’écart 144 018 / 144 701 vient de l’enrichissement / indexation.

---

## 2. Section 4.2 — Collecte de données

### Critères de sélection (`configs/repos_github.yaml`)

- **Étoiles minimum :** 500 (`min_stars`) — pour la recherche automatique
- **Popularité :** tri GitHub par `stars` décroissant
- **Langages ciblés :** Python, JavaScript, TypeScript, Java, Go, Rust, C, C++, SQL
- **Max :** 10 repos auto par langage
- **Fraîcheur :** `pushed` dans les **24 derniers mois**
- **Qualité :** README obligatoire, **pas de forks**, **pas d’archives**
- **Topics exclus :** `awesome`, `awesome-list`, `documentation-only`
- **Liste d’exclusion :** `repos_exclus` (ex. linux, bitcoin, ffmpeg…)
- **Pas de mots-clés thématiques** dans la requête GitHub (seulement `language:` + `stars:` + `pushed:`)

### Méthode mixte

1. **Repos forcés** (liste curatée par domaine : algo, web, ML, LLM, DevOps, docs…) → **235**
2. **Repos auto** (complément par critères API) → **82**
3. **Total = 317**

Étoiles observées sur la sélection : min **12** (certains repos forcés sous le seuil 500), médiane **43 312**, max **446 620**.

### Période de collecte GitHub

| Étape | Date |
|---|---|
| Premier fichier scrapé | **2026-03-28** |
| Sélection figée (`repos_selectionnes.yaml`) | **2026-06-11** |
| Fin / recap scraping | **2026-06-12** |
| Chunks finalisés | **2026-07-12** |

Recap scraping (`_recap_scraping.yaml`) : 317 repos OK, 0 KO, 14 223 docs (readme + code/doc).

**Formulation mémoire :** collecte principale **mars–juin 2026**, clôture corpus le **12/06/2026**.

---

## 3. Section 4.4 — Analyse exploratoire

### Top 10 langages (chunks locaux)

| Rang | Langage | Chunks | % |
|---:|---|---:|---:|
| 1 | Python | 35 797 | 24,86 % |
| 2 | Go | 24 285 | 16,86 % |
| 3 | TypeScript | 18 273 | 12,69 % |
| 4 | JavaScript | 12 626 | 8,77 % |
| 5 | Rust | 10 213 | 7,09 % |
| 6 | C++ | 9 772 | 6,79 % |
| 7 | Jupyter Notebook | 9 279 | 6,44 % |
| 8 | Java | 6 047 | 4,20 % |
| 9 | C | 5 092 | 3,54 % |
| 10 | Laravel | 3 058 | 2,12 % |

Les 26 langages complets : `eda_chunks_par_langage.csv`.

### Types de chunks

| Type | Nb | % approx. |
|---|---:|---|
| markdown | 82 253 | 57 % |
| code | 49 892 | 35 % |
| notebook_markdown | 5 524 | 4 % |
| notebook_code | 4 800 | 3 % |
| notebook_output | 1 549 | 1 % |

### Tailles

| Métrique | Valeur |
|---|---:|
| Chunk — caractères (moyenne) | **988** |
| Chunk — caractères (médiane) | **526** |
| Chunk — tokens approx. (car./4) | **~247** |
| Chunk — mots (moyenne / médiane) | **105 / 57** |
| P25 / P75 caractères | 263 / 1 165 |
| Fichier (somme chunks) — moy. / médiane | **8 555 / 2 759** car. |

### Paramètres de découpage (`src/data_preprocessing/decoupeur.py`)

- Texte : ~450 mots cible, overlap, min 40 / max 600 mots
- Code : ~80 lignes

Fichiers CSV : `eda_chunks_par_type.csv`, `eda_tailles_resume.csv`.

### 4.4.2 Visualisations — texte mémoire (prêt à coller)

> **Figure 5 :** Distribution des chunks par langage de programmation  
> Fichier : `figure_4_5_distribution_langages.png`

```
4.4.2. Visualisations

Deux figures accompagnent l'analyse exploratoire du corpus.

La Figure 5 présente la distribution des chunks par langage de programmation
sous forme de diagramme en barres horizontales. L'axe des ordonnées recense
les dix langages les plus représentés ; l'axe des abscisses indique le nombre
de chunks indexés. La figure confirme visuellement la prépondérance de Python
(35 797 chunks, 24,9 %) et de Go (24 285 chunks, 16,9 %), ainsi qu'une
diversité notable des langages compilés (Rust, C++, C, Java) et des notebooks
Jupyter. Cette répartition a guidé le choix des questions du jeu de test RAGAS,
afin de couvrir plusieurs écosystèmes plutôt qu'un corpus Python-only.

L'analyse exploratoire confirme la cohérence du corpus. On peut dès lors
aborder la modélisation du pipeline RAG proprement dit.
```

**Attention terminologie :** parler de **chunks** (unités indexées), pas de
« projets GitHub » — un même dépôt peut produire plusieurs chunks.

---

## 4. Section 4.5 — Modélisation RAG

### 4.5.1 Choix des modèles

**Réponse courte : choix direct** (contraintes gratuit / open-source / multilingue FR–EN / rapidité).  
Pas de campagne comparative sauvegardée (`notebooks/tests_embeddings.ipynb` vide).

| Rôle | Modèle |
|---|---|
| Embeddings | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384 dim) |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| LLM | Groq `llama-3.3-70b-versatile` |
| Base vectorielle | Qdrant (Docker), collection `github_docs`, distance COSINE |

### 4.5.3 Hyperparamètres retrieval

**Réponse courte :** choix **raisonnés** + **ablations d’architecture**  
(dense / BM25 / hybride × avec/sans rerank).  
**Pas** de grille systématique sur `top_k`, seuils et poids RRF.

Valeurs actuelles (`configs/qdrant_config.yaml` + code) :

| Paramètre | Valeur |
|---|---|
| `top_k_final` (sources) | **5** (slider UI 3–10) |
| `top_k_retrieval` | **20** |
| `score_threshold` (dense) | **0,25** (corrigé le 26/07/2026 ; était 0,35 → 0 hit dense) |
| `abstention_threshold` | **0,12** |
| RRF `poids_dense` / `poids_bm25` | **0,6 / 0,4** |
| `freshness_weight` | **0,08** |

Ablations retrieval (rapport `docs/rapport_evaluation.md`, 2026-07-16, k=5, 52 questions) :  
hybride + rerank = config de référence (Precision@k ~90 %, MRR ~0,77).

### Pipeline RAG (rappel architecture)

```
GitHub → nettoyage → chunks → embeddings → Qdrant
Requêtes : Dense + BM25 → Fusion RRF → Cross-encoder → Fraîcheur/filtres
→ Groq Llama → réponse FR + citations + confiance
```

---

## 5. Section 4.6 — Évaluation et tests

### RAGAS (déjà disponible)

| Métrique | Score |
|---|---:|
| Faithfulness | 0,95 |
| Answer Relevancy | 0,72 |
| Context Precision | 1,0 |
| Context Recall | 1,0 |
| Score global | **0,9174** |

### Tests utilisateurs (10 participants)

**Non menés.**  
Seul un **protocole** existe : `docs/questionnaire_isi.md`.  
Aucun tableau de résultats.  
→ **Retirer** des listes de figures / tableaux, ou déplacer en **perspectives**.

Feedback 👍/👎 interne SQLite ≠ enquête ISI structurée.

---

## 6. Section 4.7 — Déploiement

- **Fait :** Docker pour **Qdrant uniquement** (`docker/docker-compose.yml`)
- **Perspective :** conteneurisation complète de l’app Streamlit / API, etc.

---

## 7. Figures / captures

| Fichier | Usage mémoire |
|---|---|
| `figure_4_2_accueil.png` | Fig. 4.2 — écran d’accueil AssistDoc (**capture live**, sept. 2026) |
| `figure_4_3_reponse_sources.png` | Fig. 4.3 / Fig. 8 — requête Flask + sources GitHub citées (**capture live**, sept. 2026) |
| `figure_4_5_distribution_langages.png` | Fig. 4.5 — distribution chunks par langage (matplotlib) |
| `figure_4_10_performance_objectifs.png` | Fig. 10 — performance RAGAS vs cibles (barres groupées) |
| `figure_4_2_accueil.html` / `figure_4_3_*.html` | Maquettes HTML (secours si pas de capture live) |
| `eda_resume_pour_claude.md` | Synthèse EDA courte |
| `eda_*.csv` | Tableaux bruts (source des figures quantitatives) |

**Fig. 4.2 :** capture manuelle de l’écran d’accueil Streamlit.  
**Fig. 4.3 (Fig. 8 mémoire) :** capture live — requête « Créer une API REST avec Flask », réponse structurée, sources GitHub (`flask-rest-fr` / `flask-rest-en`) avec scores de confiance.  
**Fig. 4.5 :** générée depuis `eda_chunks_par_langage.csv` (top 10, Laravel seul au rang 10).

### Régénérer les exports

```bash
python scripts/export_eda_memoire.py
python scripts/generer_figure_distribution_langages.py
python scripts/generer_figure_performance_objectifs.py
python scripts/generer_figures_ui.py   # maquettes 4.2 / 4.3 si besoin
```

---

## 8. Bloc prêt à coller à Claude

```
Corpus AssistDoc :
- 317 repos (235 forcés + 82 auto)
- Critères : min 500⭐ (auto), README, non-fork, non-archivé, pushed < 24 mois,
  9 langages + liste curatée ; pas de mots-clés thématiques dans la requête GitHub
- Collecte GitHub : 28/03/2026 → 12/06/2026
- Index Qdrant : 144 701 points, 26 langages
- EDA chunks locaux : 144 018 ; top : Python 24,9 %, Go 16,9 %, TS 12,7 %, JS 8,8 %, Rust 7,1 %
- Taille chunk moy. ~988 car. (~247 tokens), médiane 526
- Modèles = CHOIX DIRECT (gratuit / multilingue / Groq)
  embeddings MiniLM-L12-v2 multilingue, reranker ms-marco-MiniLM-L-6-v2,
  LLM llama-3.3-70b-versatile
- Hyperparams RAG = RAISONNÉS + ablations architecture (pas sweep top_k/seuils/RRF)
  top_k=5, retrieval=20, score_threshold=0.25, RRF 0.6/0.4, abstention=0.12
- RAGAS : Faithfulness 0.95, Relevancy 0.72, Precision 1.0, Recall 1.0, global 0.9174
- Enquête 10 utilisateurs : NON MENÉE → retirer / perspectives
- Déploiement : Docker Qdrant seul ; reste en perspective
- Figures : figure_4_2_accueil.png + figure_4_3_reponse_sources.png (ce dossier)
```

---

## 9. Fichiers du dépôt utiles

| Chemin | Contenu |
|---|---|
| `configs/repos_github.yaml` | Critères + repos forcés |
| `configs/qdrant_config.yaml` | Seuils / collection |
| `src/data_collection/selecter_repo.py` | Pipeline sélection |
| `src/data_preprocessing/decoupeur.py` | Chunking |
| `src/retrieval/fusion.py` | RRF 0.6 / 0.4 |
| `docs/rapport_evaluation.md` | Ablations Precision@k / MRR |
| `docs/questionnaire_isi.md` | Protocole users (non exécuté) |
| `docs/architecture.md` | Vue d’ensemble |
| `resultats/metrics/ragas_final_*.json` | Historique RAGAS |
