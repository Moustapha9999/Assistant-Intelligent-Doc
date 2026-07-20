# Assistant Intelligent Doc — RAG Documentation Assistant

Système intelligent d'assistance à la recherche documentaire technique pour développeurs **francophones**.

Interrogez en français la documentation open-source de centaines de projets GitHub de qualité, et obtenez des réponses claires **avec citations des sources**.

---

## Description

Ce projet implémente un système **RAG** (Retrieval Augmented Generation) complet :
collecte de documentation GitHub → nettoyage → découpage → embeddings → indexation vectorielle → recherche hybride → génération de réponses en français → évaluation.

L'objectif est de fournir une alternative **gratuite et open-source** aux assistants documentaires commerciaux, en s'appuyant exclusivement sur des modèles et services accessibles (Sentence-Transformers, Qdrant, Groq).

### Fonctionnalités récentes

- Historique de chat **persistant** (SQLite)
- **Streaming** des réponses
- Feedback 👍/👎, export Markdown
- Filtres avancés (langage, repo, stars, date) + abstention si confiance faible
- Citations avec **score de confiance**
- Upload fichier **+ corpus** combinés
- Embeddings **multilingues** FR/EN
- API FastAPI (`src/api/main_api.py`) + CLI (`src/cli.py`)
- Auth Streamlit (`STREAMLIT_PASSWORD` / `STREAMLIT_USERS`) + clés API (`API_KEYS`)
- Export Markdown / PDF + signalement d’erreur
- Webhook d’ingestion (`POST /ingest/webhook`) + script cron
- Favoris / collections de docs, vision images (Groq), panel admin corpus
- Comptes invité / email / GitHub + quotas + page **Admin** (users, usage, corpus, audit)
- Éval retrieval : Precision@k / MRR + ablations (`src/evaluation/3_evaluer_retrieval.py`)

## Objectifs

- Réduire le temps de recherche documentaire de ~70 %
- Fournir des réponses **en français** avec citations systématiques des sources
- Rester gratuit et open-source de bout en bout

---

## Architecture

```
GitHub (API)
   │  collecte (README + /docs)
   ▼
Nettoyage  ──►  Découpage (chunks ~500 mots, overlap 100)
   │
   ▼
Embeddings (Sentence-Transformers paraphrase-multilingual-MiniLM-L12-v2, dim 384)
   │
   ▼
Qdrant (collection "github_docs", distance COSINE, filtres payload)
   │
   ▼
Recherche hybride :  Dense (Qdrant + seuil)  +  Sparse (BM25)  ──► Fusion RRF ──► Reranking ──► Fraîcheur
   │
   ▼
Génération streaming (Groq · llama-3.3-70b-versatile) ──► Réponse FR + citations + confiance
   │
   ▼
Évaluation RAGAS + Precision@k / MRR (ablations)
   │
   ▼
Interface Streamlit (+ API FastAPI / CLI) · historique SQLite
```

### Stack technique

| Étape | Technologie |
|-------|-------------|
| Collecte | `PyGithub`, GitHub API |
| Prétraitement | nettoyeur regex (badges, HTML, liens) + découpeur en chunks |
| Embeddings | `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensions) |
| Base vectorielle | **Qdrant** (Docker) + index payload |
| Recherche | Hybride — Dense + BM25, RRF, reranking, fraîcheur, filtres |
| Génération | **Groq** — `llama-3.3-70b-versatile` (streaming) |
| Évaluation | **RAGAS** + Precision@k / MRR |
| Interface | **Streamlit** + API FastAPI + CLI |

---

## Structure du projet

```
Assistant-Intelligent-Doc/
├── configs/
│   ├── repos_github.yaml        # Critères de sélection + repos forcés
│   └── qdrant_config.yaml       # Config collection Qdrant
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml       # Service Qdrant
├── src/
│   ├── config.py                # Configuration centrale (chemins, modèle, SSL)
│   ├── data_collection/
│   │   ├── selecter_repo.py     # Sélection des repos (forcés + auto par critères)
│   │   └── scraper_github.py    # Collecte README + fichiers /docs
│   ├── data_preprocessing/
│   │   ├── nettoyeur.py         # Nettoyage des README
│   │   └── decoupeur.py         # Découpage en chunks
│   ├── indexing/
│   │   ├── generateur_embeddings.py  # Génération des embeddings
│   │   └── gestionnaire_qdrant.py    # Indexation / requêtes Qdrant
│   ├── retrieval/
│   │   └── retrieval_hybride.py # Dense + BM25 + RRF + reranking
│   ├── generation/
│   │   └── generateur_reponse.py# Réponses FR via Groq avec citations
│   ├── evaluation/
│   │   └── evaluateur_ragas.py  # Évaluation RAGAS
│   └── app/
│       └── main.py              # Interface Streamlit
├── scripts/
│   └── indexer_corpus.py        # Pipeline complet d'indexation
├── notebooks/                   # exploration, tests embeddings, évaluation
├── data/                        # raw / processed / embeddings (gitignoré)
├── docs/                        # architecture, api, guide d'utilisation
├── tests/
└── requirements.txt
```

---

## Le pipeline en détail

### 1. Sélection des repositories — `selecter_repo.py`

Sélectionne les projets GitHub à partir de [configs/repos_github.yaml](configs/repos_github.yaml) :

- **repos forcés** (liste explicite) + **recherche automatique** par critères
- Critères : ≥ 250 stars, ≤ 24 mois d'ancienneté, README obligatoire, exclusion des forks et archives
- Langages ciblés : Python, JavaScript, Java, C, C++, Go, PHP/Laravel
- Filtrage par topics préférés (api, web, framework, ml, cli, testing, security…)

### 2. Collecte — `scraper_github.py`

Récupère le README et les fichiers `.md` du dossier `/docs` de chaque repo via l'API GitHub.

### 3. Nettoyage — `nettoyeur.py`

Supprime les badges (shields.io, travis-ci…), le HTML résiduel et les éléments non pertinents.

### 4. Découpage — `decoupeur.py`

Découpe les documents en **chunks d'environ 500 mots** avec un **overlap de 100 mots** pour préserver le contexte.

### 5. Embeddings — `generateur_embeddings.py`

Encode chaque chunk avec `all-MiniLM-L6-v2` → vecteurs de **384 dimensions**, sauvegardés en `.npz`.

### 6. Indexation — `gestionnaire_qdrant.py` + `scripts/indexer_corpus.py`

Crée la collection `github_docs` (distance COSINE) et indexe tous les chunks dans Qdrant.

### 7. Recherche hybride — `retrieval_hybride.py`

- **Dense** : recherche vectorielle Qdrant
- **Sparse** : BM25 (`rank-bm25`)
- **Fusion** : Reciprocal Rank Fusion (RRF)
- **Reranking** : cross-encoder `ms-marco-MiniLM-L-6-v2`
- Paramètres par défaut : `top_k_retrieval=20`, `top_k_final=5`

### 8. Génération — `generateur_reponse.py`

Génère une réponse **en français** via Groq (`llama-3.3-70b-versatile`, `temperature=0.1`), strictement basée sur le contexte récupéré, avec **citation systématique des sources GitHub**.

### 9. Évaluation — `evaluateur_ragas.py`

Mesure la qualité du système avec RAGAS : **Faithfulness, Answer Relevancy, Context Recall, Context Precision**.

### 10. Interface — `app/main.py`

Application Streamlit (thème sombre, IBM Plex) pour poser des questions et visualiser réponses + sources.

---

## Installation

```bash
# 1. Cloner le repo
git clone https://github.com/Moustapha9999/Assistant-Intelligent-Doc.git
cd Assistant-Intelligent-Doc

# 2. Créer l'environnement virtuel
python -m venv venv
# Windows
venv\Scripts\activate
# Mac/Linux
# source venv/bin/activate

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Configurer les variables d'environnement
cp .env.example .env
# puis éditer .env
```

### Variables d'environnement (`.env`)

```ini
GITHUB_TOKEN=ghp_xxx              # pour la collecte
GROQ_API_KEY=gsk_xxx             # pour la génération
LLM_MODEL=llama-3.3-70b-versatile
LLM_TEMPERATURE=0.1
QDRANT_URL=http://localhost:6333
# DISABLE_SSL_VERIFY=1           # dépannage réseau uniquement (proxy d'entreprise)
```

---

## Utilisation

### 1. Lancer Qdrant (Docker)

```bash
cd docker
docker-compose up -d
# API REST : http://localhost:6333 — gRPC : 6334
```

### 2. Construire le corpus (une seule fois)

```bash
# Sélection des repos
python src/data_collection/selecter_repo.py
# Collecte de la documentation
python src/data_collection/scraper_github.py
# Nettoyage
python src/data_preprocessing/nettoyeur.py
# Découpage en chunks
python src/data_preprocessing/decoupeur.py
```

### 3. Indexer le corpus dans Qdrant

```bash
# Génère les embeddings puis indexe tout dans Qdrant
python scripts/indexer_corpus.py
```

### 4. Lancer l'interface

```bash
streamlit run src/app/main.py
```

### 5. Évaluer le système (optionnel)

```bash
python src/evaluation/evaluateur_ragas.py
# ou via le notebook : notebooks/evaluation.ipynb
```

---

## Configuration

Toute la configuration est centralisée dans [src/config.py](src/config.py) :

- chemins **ancrés sur la racine du projet** (indépendants du répertoire courant)
- cache des modèles **unifié** (`models_cache/`)
- contournement SSL **désactivé par défaut**, activable via `DISABLE_SSL_VERIFY=1` (dépannage uniquement)

La collection Qdrant est paramétrée dans [configs/qdrant_config.yaml](configs/qdrant_config.yaml)
et les critères de corpus dans [configs/repos_github.yaml](configs/repos_github.yaml).

---

## Performance visée

| Métrique | Cible |
|----------|-------|
| Precision@5 | > 80 % |
| Faithfulness | > 90 % |
| Latence | < 5 s |

---

## Documentation complémentaire

- [docs/architecture.md](docs/architecture.md)
- [docs/api.md](docs/api.md)
- [docs/guide_utilisation.md](docs/guide_utilisation.md)

---

## Auteur

**Moustapha Youssouf Sall** — Master 2 IAGE — ISI KOMUNIK
