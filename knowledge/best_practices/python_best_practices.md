# Python — bonnes pratiques

## Style & projet
- Suis PEP 8 ; formate avec `ruff` ou `black`.
- Environnement virtuel obligatoire (`.venv`).
- `requirements.txt` ou `pyproject.toml` versionné.
- Type hints sur les API publiques (`mypy` / `pyright` si possible).

## Code idiomatique
- Comprehensions lisibles ; sinon boucle claire.
- Context managers (`with`) pour fichiers, locks, sessions.
- Dataclasses / Pydantic pour structures de données.
- Préfère les exceptions explicites aux codes d’erreur silencieux.

## Packaging & imports
- Imports absolus dans les apps ; structure `src/` ou package clair.
- Évite `from module import *`.

## Tests
- `pytest` ; tests unitaires sur le domaine ; tests d’intégration sur l’API.
- Fixtures ciblées, pas de dépendances réseau non mockées.

## Erreurs fréquentes
- Mutable default args (`def f(x=[])`)
- Chemin Windows/Linux non gérés (`pathlib`)
- Tout mettre dans `main.py`
- Ignorer le logging (print partout en prod)
