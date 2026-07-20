# Référence — Dockeriser une app Python

## Explication
Docker packagé l’app + runtime pour un run reproductible.

## Architecture
- Image app (API)
- Service DB (Postgres) via compose
- Réseau interne, volumes pour la persistance

## Exemple Dockerfile (multi-stage simple)
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## docker-compose (idée)
services: `api`, `db` ; variables `DATABASE_URL` ; volume `pgdata`.

## Pourquoi
Évite “ça marche chez moi”. Aligne dev et prod.

## Erreurs fréquentes
- Copier `.venv` dans l’image
- Tourner en root sans besoin
- Secrets dans l’image
- Oublier `.dockerignore`

## Bonnes pratiques
Images slim, healthchecks, non-root user, tags versionnés.
