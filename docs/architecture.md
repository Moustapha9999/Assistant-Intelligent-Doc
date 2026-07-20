# Architecture

L'application est un assistant RAG francophone orienté documentation technique et accompagnement de projets.

```text
Utilisateur
    │
    ▼
Streamlit ────────────────► SQLite (conversations et feedback)
    │
    ▼
RetrievalHybride
    ├─ Dense : embeddings multilingues ─► Qdrant
    ├─ Sparse : index BM25 local
    ├─ Fusion : Reciprocal Rank Fusion (RRF)
    └─ Classement : cross-encoder
    │
    ▼
Contexte sélectionné ───► Groq / Llama ───► Réponse sourcée
    │
    └────────────────────► RAGAS (évaluation hors ligne)
```

## Données et indexation

Les dépôts GitHub, les guides internes et le corpus enrichi sont collectés puis nettoyés et découpés en chunks. Chaque chunk conserve ses métadonnées : dépôt, langage, URL, fichier, étoiles et date de mise à jour. L'index Qdrant et l'index BM25 exploitent ce même corpus.

Le modèle `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` produit les embeddings de 384 dimensions, adaptés aux requêtes françaises et aux sources anglaises. Le cross-encoder `ms-marco-MiniLM-L-6-v2` réordonne les candidats après la fusion dense/sparse.

## Génération et évaluation

Les documents les plus pertinents sont fournis à Llama via Groq avec des instructions de mentorat et de citation. L'historique et les évaluations utilisateur sont persistés dans SQLite. RAGAS et le jeu de questions de retrieval permettent de mesurer séparément l'ancrage des réponses et la qualité de récupération.

Changer le modèle d'embeddings impose de reconstruire les vecteurs et la collection Qdrant : les dimensions et l'espace vectoriel doivent rester cohérents.
