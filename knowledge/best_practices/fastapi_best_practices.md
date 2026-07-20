# FastAPI — bonnes pratiques

## Structure recommandée
```
app/
  main.py          # create_app, include_router
  api/routes/      # endpoints par domaine
  schemas/         # Pydantic request/response
  models/          # ORM / domaine
  services/        # logique métier
  repositories/    # accès données
  core/config.py   # settings
```

## API design
- Modèles Pydantic séparés Create / Update / Read.
- Codes HTTP corrects (201 create, 404 not found, 422 validation).
- Dépendances (`Depends`) pour auth, DB session, settings.
- Pas de logique métier lourde dans les route handlers.

## Démarrage correct
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate
pip install fastapi uvicorn
uvicorn app.main:app --reload
```
Interdit : `fastapi new` (n’existe pas).

## Sécurité
- Validation stricte des entrées
- Secrets via variables d’environnement
- CORS explicite
- Auth JWT/OAuth2 avec expiration et refresh maîtrisés

## Erreurs fréquentes
- Modèle générique `Item(name, price)` hors sujet
- Session DB globale non scoped
- Retourner des objets ORM bruts sans schema
