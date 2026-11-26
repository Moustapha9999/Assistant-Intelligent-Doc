# AssistDoc

Assistant conversationnel RAG pour la documentation technique (ISI KOMUNIK · Master IAGE).

## Démarrage local

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
streamlit run src/app/main.py
```

Copiez `.env.example` vers `.env` et `.streamlit/secrets.toml.example` vers `.streamlit/secrets.toml` selon votre environnement.

## Déploiement

- **Streamlit Community Cloud** : point d’entrée `src/app/main.py`, dépendances `requirements.txt`.
- **Docker** : voir `docker/docker-compose.yml`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests/test_ui.py tests/test_edit_prompt.py tests/test_edit_prompt_apptest.py -q
```
