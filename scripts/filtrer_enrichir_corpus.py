"""
Filtre le corpus (retire DE/ES/PT et docs hors sujet) et enrichit
avec des chunks FR/EN ciblés Flask REST + fichiers Python.

Usage :
    python scripts/filtrer_enrichir_corpus.py

Effets :
  - Sauvegarde data/processed/chunks/tous_chunks.backup.json
  - Écrit data/processed/chunks/tous_chunks.json (filtré + enrichi)
  - Ensuite : python scripts/indexer_corpus.py
"""

from __future__ import annotations

import json
import re
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHUNKS_PATH = ROOT / "data" / "processed" / "chunks" / "tous_chunks.json"
BACKUP_PATH = ROOT / "data" / "processed" / "chunks" / "tous_chunks.backup.json"

# Marqueurs de langues non désirées (docs naturelles)
MARKERS = {
    "de": re.compile(
        r"\b(und|der|die|das|mit|für|nicht|auch|oder|werden|hierbei|"
        r"erstellen|verwenden|verzeichnis|anwendung|schlüssel|sicherheit)\b",
        re.I,
    ),
    "es": re.compile(
        r"\b(también|aplicación|mediante|configuración|siguiente|"
        r"archivo|puede|nuestro|ejemplo)\b",
        re.I,
    ),
    "pt": re.compile(
        r"\b(também|aplicação|através|configuração|arquivo|"
        r"pode|nosso|exemplo|utilize)\b",
        re.I,
    ),
    "it": re.compile(
        r"\b(anche|applicazione|mediante|configurazione|file|"
        r"può|nostro|esempio|utilizzare)\b",
        re.I,
    ),
    "fr": re.compile(
        r"\b(les|des|une|pour|avec|dans|cette|aussi|fonction|"
        r"utiliser|fichier|exemple)\b",
        re.I,
    ),
    "en": re.compile(
        r"\b(the|and|with|for|this|that|from|function|using|"
        r"return|example|file|create)\b",
        re.I,
    ),
}

DOC_TYPES = {"markdown", "notebook_markdown", "documentation"}


def detecter_langue_doc(texte: str) -> str:
    extrait = texte[:1200]
    scores = {lang: len(rx.findall(extrait)) for lang, rx in MARKERS.items()}
    meilleure = max(scores, key=scores.get)
    if scores[meilleure] < 3:
        return "unknown"
    return meilleure


def est_code(chunk: dict) -> bool:
    t = (chunk.get("type_chunk") or "").lower()
    return "code" in t or chunk.get("type_doc") == "code"


def doit_exclure(chunk: dict) -> bool:
    """Exclut les docs naturelles hors EN/FR (garde le code)."""
    if est_code(chunk):
        return False
    texte = chunk.get("texte") or ""
    lang = detecter_langue_doc(texte)
    if lang in {"de", "es", "pt", "it"}:
        return True
    # Traductions FastAPI / CLI clairement non EN-FR
    if lang not in {"en", "fr", "unknown"}:
        return True
    return False


def chunk_enrichi(
    texte: str,
    titre: str,
    repo: str,
    chemin: str,
    langage: str = "Python",
) -> dict:
    return {
        "texte": texte.strip(),
        "section_titre": titre,
        "type_chunk": "markdown",
        "nom_complet": repo,
        "langage": langage,
        "etoiles": 0,
        "url": f"https://github.com/{repo}" if "/" in repo else "",
        "type_doc": "documentation",
        "chemin_fichier": chemin,
        "source_enrichissement": True,
    }


ENRICHISSEMENTS = [
    chunk_enrichi(
        titre="Flask REST API with @app.route and jsonify",
        repo="enrichissement/flask-rest-en",
        chemin="enrichissement/flask_rest_en.md",
        texte="""
# Creating a REST API with Flask in Python

Flask is a lightweight Python microframework. To build a REST API, define
HTTP routes with the `@app.route` decorator and return JSON with `jsonify()`.

```python
from flask import Flask, jsonify, request

app = Flask(__name__)

books = [
    {"id": 1, "title": "Clean Code"},
    {"id": 2, "title": "Fluent Python"},
]

@app.route("/books", methods=["GET"])
def list_books():
    return jsonify(books)

@app.route("/books/<int:book_id>", methods=["GET"])
def get_book(book_id):
    for book in books:
        if book["id"] == book_id:
            return jsonify(book)
    return jsonify({"error": "Not found"}), 404

@app.route("/books", methods=["POST"])
def create_book():
    data = request.get_json()
    new_book = {"id": len(books) + 1, "title": data["title"]}
    books.append(new_book)
    return jsonify(new_book), 201

if __name__ == "__main__":
    app.run(debug=True)
```

Key ideas: `@app.route` maps URLs to functions; HTTP methods select the action;
`jsonify()` serializes Python objects to JSON responses.
""",
    ),
    chunk_enrichi(
        titre="API REST Flask avec @app.route et jsonify",
        repo="enrichissement/flask-rest-fr",
        chemin="enrichissement/flask_rest_fr.md",
        texte="""
# Créer une API REST avec Flask en Python

Flask est un micro-framework Python. Pour créer une API REST, on définit des
routes avec le décorateur `@app.route()` et on renvoie du JSON via `jsonify()`.

```python
from flask import Flask, jsonify, request

app = Flask(__name__)

@app.route("/api/hello", methods=["GET"])
def hello():
    return jsonify({"message": "Bonjour"})

@app.route("/api/items", methods=["POST"])
def creer_item():
    payload = request.get_json()
    return jsonify({"cree": True, "item": payload}), 201
```

Résumé : `@app.route` associe une URL à une fonction ; `jsonify()` convertit
un dictionnaire Python en réponse JSON ; les méthodes HTTP (`GET`, `POST`,
`PUT`, `DELETE`) décrivent l'action sur la ressource.
""",
    ),
    chunk_enrichi(
        titre="Python with open — read and write files",
        repo="enrichissement/python-files-en",
        chemin="enrichissement/python_files_en.md",
        texte="""
# Reading and writing files in Python with `with open`

Prefer the context manager `with open(...)` so the file is always closed.

```python
# Read text
with open("data.txt", "r", encoding="utf-8") as f:
    content = f.read()

# Read line by line
with open("data.txt", "r", encoding="utf-8") as f:
    for line in f:
        print(line.strip())

# Write (overwrite)
with open("out.txt", "w", encoding="utf-8") as f:
    f.write("hello\\n")

# Append
with open("out.txt", "a", encoding="utf-8") as f:
    f.write("world\\n")
```

Modes: `'r'` read, `'w'` write, `'a'` append, `'rb'`/`'wb'` binary.
The `with` block guarantees `f.close()` even if an exception occurs.
""",
    ),
    chunk_enrichi(
        titre="Lire et écrire un fichier avec with open en Python",
        repo="enrichissement/python-files-fr",
        chemin="enrichissement/python_files_fr.md",
        texte="""
# Ouvrir et lire un fichier avec `with open` en Python

Utilisez `with open(chemin, mode)` pour ouvrir un fichier. Le gestionnaire
de contexte ferme automatiquement le fichier.

```python
# Lecture
with open("data.txt", "r", encoding="utf-8") as f:
    contenu = f.read()

# Écriture
with open("sortie.txt", "w", encoding="utf-8") as f:
    f.write("bonjour\\n")

# Ajout en fin de fichier
with open("sortie.txt", "a", encoding="utf-8") as f:
    f.write("suite\\n")
```

Modes courants : `'r'` lecture, `'w'` écriture (écrase), `'a'` ajout.
Le bloc `with` appelle `close()` même en cas d'erreur.
""",
    ),
    chunk_enrichi(
        titre="FastAPI minimal GET/POST API",
        repo="enrichissement/fastapi-en",
        chemin="enrichissement/fastapi_en.md",
        texte="""
# Creating an API with FastAPI

FastAPI is a modern Python framework. Define routes with `@app.get` / `@app.post`
and validate payloads with Pydantic models.

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str
    price: float

@app.get("/items/{item_id}")
def read_item(item_id: int):
    return {"item_id": item_id}

@app.post("/items")
def create_item(item: Item):
    return item
```

Run with: `uvicorn main:app --reload`.
""",
    ),
]


def main():
    if not CHUNKS_PATH.exists():
        raise SystemExit(f"Fichier introuvable : {CHUNKS_PATH}")

    print("=" * 60)
    print("FILTRAGE + ENRICHISSEMENT DU CORPUS")
    print("=" * 60)

    with open(CHUNKS_PATH, encoding="utf-8") as f:
        chunks = json.load(f)
    print(f"Chunks d'origine : {len(chunks)}")

    # Backup une seule fois
    if not BACKUP_PATH.exists():
        shutil.copy2(CHUNKS_PATH, BACKUP_PATH)
        print(f"Backup créé : {BACKUP_PATH.name}")
    else:
        print(f"Backup déjà présent : {BACKUP_PATH.name}")

    exclus = []
    conserves = []
    stats_lang = Counter()
    for c in chunks:
        if doit_exclure(c):
            lang = detecter_langue_doc(c.get("texte") or "")
            stats_lang[lang] += 1
            exclus.append(c)
        else:
            conserves.append(c)

    print(f"Exclus (docs non EN/FR) : {len(exclus)} → {dict(stats_lang)}")
    print(f"Conservés               : {len(conserves)}")

    # Enrichissement
    avant = len(conserves)
    conserves.extend(ENRICHISSEMENTS)
    print(f"Enrichissements ajoutés : {len(ENRICHISSEMENTS)} (total {len(conserves)}, +{len(conserves)-avant})")

    # Stats ciblées
    for terme in ["jsonify", "@app.route", "with open(", "FastAPI"]:
        n = sum(1 for c in conserves if terme in (c.get("texte") or ""))
        print(f"  couverture '{terme}': {n} chunks")

    with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
        json.dump(conserves, f, ensure_ascii=False)

    print(f"\n✅ Écrit : {CHUNKS_PATH}")
    print("👉 Étape suivante : python scripts/indexer_corpus.py")


if __name__ == "__main__":
    main()
