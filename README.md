# Assistant Intelligent Doc — RAG Documentation Assistant

[![CI](https://github.com/Moustapha9999/Assistant-Intelligent-Doc/actions/workflows/ci.yml/badge.svg)](https://github.com/Moustapha9999/Assistant-Intelligent-Doc/actions/workflows/ci.yml)

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
- Feedback 👍/👎, export Markdown / PDF
- Filtres avancés (langage, repo, stars, date) + abstention si confiance faible
- Citations avec **score de confiance**
- Upload fichier **+ corpus** combinés
- Embeddings **multilingues** FR/EN
- API FastAPI (`src/api/main_api.py`) + CLI (`src/cli.py`)
- Auth : invité, email, **Google** / **GitHub** OAuth + quotas + page **Admin**
- Vision (analyse d'images via Groq) + **génération d'images** (Pollinations / OpenAI)
- Favoris / collections, panel admin corpus, webhook d'ingestion
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
| Vision / images | Groq Vision + Pollinations (ou OpenAI Images) |
| Évaluation | **RAGAS** + Precision@k / MRR |
| Interface | **Streamlit** + API FastAPI + CLI |
| CI | GitHub Actions (`pytest` + lint critique) |

---

## Structure du projet

```
Assistant-Intelligent-Doc/
├── .github/workflows/ci.yml     # CI GitHub Actions
├── .streamlit/config.toml       # Thème Streamlit
├── .env.example                 # Variables d'environnement (modèle)
├── requirements.txt
├── assets/                      # Logo AssistDoc
├── configs/
│   ├── repos_github.yaml        # Critères de sélection + repos forcés
│   └── qdrant_config.yaml       # Config collection Qdrant
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml       # Service Qdrant
├── docs/                        # Architecture, API, guide, rapports
├── knowledge/                   # Mentorat / best practices / réponses types
├── notebooks/                   # Explorations & évaluations
├── scripts/                     # Indexation, sync GitHub, CI locale
├── tests/                       # Tests unitaires (CI)
└── src/
    ├── config.py                # Configuration centrale
    ├── cli.py                   # Interface en ligne de commande
    ├── api/                     # FastAPI (+ webhook ingest)
    ├── app/                     # Streamlit (chat, auth, admin, exports)
    ├── core/                    # Orchestrateur, modes, mémoires
    ├── data_collection/         # Sélection + scrape GitHub
    ├── data_preprocessing/      # Nettoyage + chunks
    ├── indexing/                # Embeddings + Qdrant
    ├── retrieval/               # Dense, BM25, fusion, citations
    ├── generation/              # LLM Groq + génération d'images
    ├── prompts/                 # Prompts système / modes / domaines
    ├── web/                     # Recherche web
    ├── securite/                # Clés API / contrôle d'accès
    └── evaluation/              # RAGAS + métriques retrieval
```

Données locales (non versionnées) : `data/`, `qdrant_storage/`, `logs/`, `resultats/`, `models_cache/`.

---

## Installation

```bash
git clone https://github.com/Moustapha9999/Assistant-Intelligent-Doc.git
cd Assistant-Intelligent-Doc
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # puis renseigner GROQ_API_KEY, etc.
```

Variables utiles dans `.env` :

```ini
GITHUB_TOKEN=ghp_xxx              # pour la collecte
GROQ_API_KEY=gsk_xxx             # pour la génération
LLM_MODEL=llama-3.3-70b-versatile
LLM_TEMPERATURE=0.1
QDRANT_URL=http://localhost:6333
# IMAGE_GEN_PROVIDER=auto        # pollinations | openai | off
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
python src/data_collection/selecter_repo.py
python src/data_collection/scraper_github.py
python src/data_preprocessing/nettoyeur.py
python src/data_preprocessing/decoupeur.py
```

### 3. Indexer le corpus dans Qdrant

```bash
python scripts/indexer_corpus.py
```

### 4. Lancer l'interface

```bash
streamlit run src/app/main.py
```

### 5. CI locale (même checks que GitHub)

```bash
# Windows
pwsh scripts/run_ci.ps1
# Linux / macOS
bash scripts/run_ci.sh
```

### 6. Évaluer le système (optionnel)

```bash
python src/evaluation/evaluateur_ragas.py
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
