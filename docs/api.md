# API REST

L'API FastAPI est exposée par `src/api/main_api.py`. Les modèles de retrieval et de génération sont chargés paresseusement lors du premier `POST /ask`; cette première requête peut donc être plus lente.

```bash
uvicorn api.main_api:app --app-dir src --reload --port 8000
```

## Authentification

Si `API_KEYS` est défini dans `.env` (ex. `cle1:alice,cle2:bob`), toutes les routes protégées exigent le header :

```http
X-API-Key: cle1
```

Si `API_KEYS` est vide, l'accès est libre (pratique en local).

## `GET /health`

Retourne l'état du service sans charger les modèles.

```json
{"status": "ok", "models": "lazy"}
```

## `POST /ask`

Recherche les sources puis génère une réponse.

```json
{
  "question": "Comment créer une route FastAPI ?",
  "top_k": 5,
  "filtres": {"langage": "Python", "repo": "tiangolo/fastapi"},
  "utiliser_corpus": true
}
```

`top_k` est compris entre 1 et 20. Les filtres acceptent `langage`, `repo`, `stars_min` et `date_min`. La réponse contient `answer`, `documents`, `mode`, `tokens_utilises` et `abstention`.

## `POST /feedback`

Enregistre une évaluation d'une réponse (👍/👎 ou Likert) et un commentaire optionnel (signalement d'erreur).

```json
{
  "conversation_id": "uuid",
  "message_idx": 1,
  "note": -1,
  "commentaire": "[signalement] citation incorrecte"
}
```

La note est comprise entre -1 et 5.

## `POST /ingest/webhook`

Déclenche une synchronisation GitHub incrémentale en arrière-plan (cron, CI, webhook GitHub).

Header requis :

```http
X-Ingest-Secret: <INGEST_WEBHOOK_SECRET>
```

```json
{"since": "2026-01-01", "run": true}
```

### Cron (exemple)

```cron
# Tous les jours à 3h — sync incrémentale
0 3 * * * cd /chemin/Assistant-Intelligent-Doc && ./venv/bin/python scripts/sync_incremental_github.py --run
```

Ou via l'API :

```bash
curl -X POST http://localhost:8000/ingest/webhook \
  -H "X-Ingest-Secret: $INGEST_WEBHOOK_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"run": true}'
```

L'API configure CORS ouvert pour faciliter l'intégration d'un client séparé ; restreignez les origines avant un déploiement public.
