# Référence — API FastAPI complète (niveau mentor)

## Explication
FastAPI combine typage Python, validation Pydantic et OpenAPI automatique. Idéal pour des APIs REST modernes.

## Architecture
- Routes minces
- Schemas Pydantic (Create/Read)
- Service métier
- Repository / session DB

## Code minimal correct
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Gestion Taches")

class TacheCreate(BaseModel):
    titre: str
    fait: bool = False

class Tache(TacheCreate):
    id: int

_db: dict[int, Tache] = {}
_seq = 1

@app.post("/taches", response_model=Tache, status_code=201)
def creer(payload: TacheCreate) -> Tache:
    global _seq
    t = Tache(id=_seq, **payload.model_dump())
    _db[_seq] = t
    _seq += 1
    return t

@app.get("/taches/{tache_id}", response_model=Tache)
def lire(tache_id: int) -> Tache:
    if tache_id not in _db:
        raise HTTPException(404, "Tache introuvable")
    return _db[tache_id]
```

## Pourquoi ce code
Domaines explicites (`Tache`), pas un `Item` générique. Status 201, 404 clair, validation automatique.

## Alternatives
Flask (plus manuel), Django REST (batteries included, plus lourd).

## Erreurs fréquentes
`fastapi new`, modèles hors sujet, logique métier dans la route, secrets en dur.

## Bonnes pratiques
Venv, uvicorn reload en dev, settings via env, tests sur create/get.
