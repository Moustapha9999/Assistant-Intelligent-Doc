# Guide d'utilisation

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Copiez `.env.example` vers `.env` puis renseignez au minimum `GROQ_API_KEY`. Ajoutez `GITHUB_TOKEN` pour collecter GitHub et, si nécessaire, `QDRANT_HOST`, `QDRANT_PORT` et `EMBEDDING_MODEL`.

Démarrez les services :

```bash
docker compose -f docker/docker-compose.yml up --build
```

Ou lancez l'interface localement avec `streamlit run src/app/main.py`.

## Poser une question

Saisissez une question précise : « Comment valider un payload FastAPI avec Pydantic ? ». L'assistant récupère les documents, construit une réponse et affiche les sources. Les questions de projet peuvent demander un MVP, une architecture ou une roadmap.

Les filtres restreignent la recherche par langage, dépôt, étoiles minimales et date de mise à jour. Utilisez-les lorsque le corpus est vaste ou qu'une technologie est imposée.

## Import, feedback et export

L'interface accepte les fichiers autorisés dans la limite configurée par `UPLOAD_MAX_BYTES`. Après une réponse, attribuez une note et un commentaire : ils sont enregistrés dans SQLite avec la conversation. L'export de l'historique se fait depuis l'interface lorsqu'il est proposé.

## Ré-indexation

Après ajout ou modification du corpus, relancez le pipeline de découpage puis d'indexation Qdrant. Après tout changement de `EMBEDDING_MODEL`, une ré-indexation complète est obligatoire : les vecteurs existants ne sont pas comparables à ceux du nouveau modèle.
