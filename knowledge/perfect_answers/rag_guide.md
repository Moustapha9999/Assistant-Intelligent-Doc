# Référence — Construire un RAG de qualité

## Objectif
Réponses ancrées sur un corpus, avec citations et faible hallucination.

## Architecture typique
Ingestion → chunking → embeddings → vector DB → retrieval hybride → rerank → LLM → réponse.

## Étapes
1. Qualité corpus (langue, pertinence, dédoublonnage)
2. Chunking sémantique (titres, taille raisonnable)
3. Hybrid search (dense + BM25)
4. Filtres (langage, source)
5. Prompt qui force l’usage prudent du contexte
6. Évaluation (faithfulness, relevancy)

## Erreurs fréquentes
- Corpus bruyant (mauvaise langue, READMEs hors sujet)
- Top-k trop large sans rerank
- Prompt qui ignore le contexte ou invente
- Pas d’éval → “ça a l’air bien”

## Bonnes pratiques
Guides d’enrichissement ciblés, perfect answers, mode conversation sans sources inutiles.
