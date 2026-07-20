from __future__ import annotations

from pathlib import Path


def _e(texte: str, nom: str, titre: str, langage: str, url: str) -> dict:
    return {
        "texte": texte.strip(),
        "nom_complet": f"enrichissement/{nom}",
        "section_titre": titre,
        "langage": langage,
        "source_file": f"enrichissement/{nom}.md",
        "url": url,
    }


ENRICHISSEMENTS = [
    _e(
        nom="flask-rest-fr",
        titre="API REST Flask avec @app.route et jsonify",
        langage="Python",
        url="https://flask.palletsprojects.com/",
        texte="""# Créer une API REST avec Flask en Python
Flask est un micro-framework Python. On définit des routes avec `@app.route()` et on renvoie du JSON via `jsonify()`.

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
Résumé : `@app.route` associe une URL à une fonction ; `jsonify()` convertit un dictionnaire en JSON.""",
    ),
    _e(
        nom="fastapi-en",
        titre="FastAPI minimal GET/POST API",
        langage="Python",
        url="https://fastapi.tiangolo.com/",
        texte="""# Creating an API with FastAPI
FastAPI is a modern Python framework. Define routes with `@app.get` / `@app.post` and validate payloads with Pydantic models.

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
Run with: `uvicorn main:app --reload`.""",
    ),
    _e(
        nom="react-hooks-fr",
        titre="Hooks React useState et useEffect",
        langage="JavaScript",
        url="https://react.dev/reference/react/hooks",
        texte="""# Utiliser les hooks dans React
Les hooks React permettent d'utiliser l'état et les effets dans des composants fonctionnels, sans classes.
- `useState` : état local
- `useEffect` : effets de bord
- `useMemo` / `useCallback` : mémoïsation

```jsx
import { useState, useEffect } from "react";
function Compteur() {
  const [count, setCount] = useState(0);
  useEffect(() => { document.title = `Count: ${count}`; }, [count]);
  return <button onClick={() => setCount(count + 1)}>{count}</button>;
}
```
Règle : n'appelez les hooks qu'au niveau supérieur du composant.""",
    ),
    _e(
        nom="jwt-auth-fr",
        titre="Authentification JWT application web",
        langage="Python",
        url="https://jwt.io/",
        texte="""# Gérer l'authentification JWT dans une application web
JWT (JSON Web Token) authentifie sans session serveur. À la connexion, le serveur signe un token avec une clé secrète. Le client l'envoie dans `Authorization: Bearer ...` ; le serveur vérifie la signature.

```python
import jwt
token = jwt.encode({"sub": "user-1"}, "secret", algorithm="HS256")
payload = jwt.decode(token, "secret", algorithms=["HS256"])
```
Flux : login → JWT signé → Bearer sur routes protégées → verify ou 401.""",
    ),
    _e(
        nom="python-files-fr",
        titre="Lire et écrire un fichier avec with open",
        langage="Python",
        url="https://docs.python.org/fr/3/tutorial/inputoutput.html",
        texte="""# Ouvrir et lire un fichier avec with open en Python
Utilisez `with open(chemin, mode) as f`. Le gestionnaire ferme automatiquement le fichier.

```python
with open("data.txt", "r", encoding="utf-8") as f:
    contenu = f.read()
with open("sortie.txt", "w", encoding="utf-8") as f:
    f.write("bonjour\\n")
```
Modes : `'r'` lecture, `'w'` écriture, `'a'` ajout.""",
    ),
    _e(
        nom="projet-todo-fastapi-fr",
        titre="Guide projet : app gestion de tâches FastAPI",
        langage="Python",
        url="https://fastapi.tiangolo.com/tutorial/",
        texte="""# Projet complet : application de gestion de tâches avec FastAPI

## Objectif
API REST CRUD pour des tâches (todo) : créer, lister, modifier, supprimer.

## Stack
- Python 3.10+
- FastAPI + Pydantic
- Stockage mémoire (liste) ou SQLite plus tard
- Uvicorn

## Démarrage (étape 1) — NE PAS utiliser `fastapi new`
```bash
mkdir gestion-taches && cd gestion-taches
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/Mac: source .venv/bin/activate
pip install fastapi uvicorn
```

Créer `main.py` :
```python
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List

app = FastAPI(title="Gestion de tâches")
taches = []
compteur = 1

class TacheCreate(BaseModel):
    titre: str
    fait: bool = False

class Tache(TacheCreate):
    id: int

@app.get("/")
def accueil():
    return {"message": "API gestion de tâches"}

@app.get("/taches", response_model=List[Tache])
def lister():
    return taches

@app.post("/taches", response_model=Tache, status_code=201)
def creer(data: TacheCreate):
    global compteur
    t = Tache(id=compteur, **data.model_dump())
    compteur += 1
    taches.append(t)
    return t
```

Lancer : `uvicorn main:app --reload` puis ouvrir http://localhost:8000/docs

## Feuille de route
1. Initialiser projet + main.py
2. Modèles Pydantic
3. Routes CRUD (GET/POST/PUT/DELETE)
4. Validation et codes HTTP
5. Tests manuels via /docs
6. (optionnel) SQLite + SQLAlchemy""",
    ),
    _e(
        nom="projet-api-jwt-fr",
        titre="Guide projet : API sécurisée avec JWT",
        langage="Python",
        url="https://fastapi.tiangolo.com/tutorial/security/",
        texte="""# Projet : API FastAPI sécurisée avec JWT

## Étapes
1. Installer : `pip install fastapi uvicorn python-jose[cryptography] passlib[bcrypt]`
2. Modèle User + hash du mot de passe (passlib)
3. Route `/login` qui renvoie un JWT
4. Dépendance `get_current_user` qui lit le Bearer token
5. Protéger les routes avec `Depends(get_current_user)`

```python
from datetime import datetime, timedelta
from jose import jwt
SECRET = "change-me"
ALGO = "HS256"

def creer_token(sub: str) -> str:
    exp = datetime.utcnow() + timedelta(hours=2)
    return jwt.encode({"sub": sub, "exp": exp}, SECRET, algorithm=ALGO)
```
Ne jamais committer la clé secrète. Utiliser HTTPS en production.""",
    ),
    _e(
        nom="projet-react-todo-fr",
        titre="Guide projet : Todo React avec hooks",
        langage="JavaScript",
        url="https://react.dev/learn",
        texte="""# Projet : application Todo en React (hooks)

## Stack
Vite + React + useState/useEffect

## Étape 1
```bash
npm create vite@latest todo-app -- --template react
cd todo-app && npm install && npm run dev
```

## Structure
- `App.jsx` : liste des tâches + formulaire
- état : `const [todos, setTodos] = useState([])`
- ajouter : `setTodos([...todos, { id: Date.now(), text, done: false }])`
- basculer done / supprimer avec `map` / `filter`

Persistance simple : `localStorage` dans un `useEffect`.""",
    ),
    _e(
        nom="algo-complexite-fr",
        titre="Complexité algorithmique Big O",
        langage="Informatique",
        url="https://en.wikipedia.org/wiki/Big_O_notation",
        texte="""# Complexité algorithmique (Big O)

La notation Big O décrit comment le temps (ou la mémoire) croît avec la taille n des données.

| Complexité | Exemple | Commentaire |
|---|---|---|
| O(1) | accès tableau[i] | constant |
| O(log n) | recherche dichotomique | très bon |
| O(n) | parcours de liste | linéaire |
| O(n log n) | tri fusion / timsort | tris efficaces |
| O(n²) | double boucle | lent sur grands n |

Choisir la bonne structure de données (hash map, heap, arbre) change souvent la complexité.""",
    ),
    _e(
        nom="structures-donnees-fr",
        titre="Structures de données essentielles",
        langage="Informatique",
        url="https://en.wikipedia.org/wiki/Data_structure",
        texte="""# Structures de données essentielles

- **Tableau / liste** : accès index O(1), insertion milieu O(n)
- **Pile (stack)** : LIFO — undo, parsing
- **File (queue)** : FIFO — file d'attente, BFS
- **Hash map / dict** : clé → valeur, accès moyen O(1)
- **Ensemble (set)** : unicité, tests d'appartenance
- **Arbre / BST** : recherche ordonnée
- **Graphe** : réseaux, chemins (DFS/BFS, Dijkstra)

En Python : `list`, `dict`, `set`, `collections.deque`.""",
    ),
    _e(
        nom="oop-python-fr",
        titre="Programmation orientée objet Python",
        langage="Python",
        url="https://docs.python.org/3/tutorial/classes.html",
        texte="""# Programmation orientée objet (POO) en Python

```python
class Animal:
    def __init__(self, nom: str):
        self.nom = nom
    def parler(self):
        raise NotImplementedError

class Chien(Animal):
    def parler(self):
        return f"{self.nom} aboie"
```

Concepts : encapsulation, héritage, polymorphisme.
`@property`, méthodes de classe `@classmethod`, méthodes statiques `@staticmethod`.
Préférer la composition à un héritage trop profond.""",
    ),
    _e(
        nom="http-rest-fr",
        titre="HTTP et architecture REST",
        langage="Informatique",
        url="https://developer.mozilla.org/fr/docs/Web/HTTP",
        texte="""# HTTP et API REST

## Méthodes
- GET : lire (idempotent)
- POST : créer
- PUT/PATCH : remplacer / modifier
- DELETE : supprimer

## Codes
- 200 OK, 201 Created, 204 No Content
- 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found
- 500 Internal Server Error

## REST
Ressources nommées par URL (`/users/42`), représentation JSON, sans état (stateless).
Headers utiles : `Content-Type`, `Authorization`, `Accept`.""",
    ),
    _e(
        nom="sql-bases-fr",
        titre="Bases SQL SELECT JOIN INDEX",
        langage="SQL",
        url="https://www.postgresql.org/docs/",
        texte="""# Bases de SQL

```sql
SELECT id, nom FROM users WHERE actif = TRUE ORDER BY nom LIMIT 20;

SELECT u.nom, o.total
FROM users u
JOIN orders o ON o.user_id = u.id
WHERE o.total > 100;

CREATE INDEX idx_orders_user ON orders(user_id);
```

- PRIMARY KEY / FOREIGN KEY pour l'intégrité
- JOIN pour relier les tables
- INDEX pour accélérer les filtres/jointures
- Transactions : BEGIN / COMMIT / ROLLBACK

ORM populaires : SQLAlchemy (Python), Prisma (JS), Hibernate (Java).""",
    ),
    _e(
        nom="git-bases-fr",
        titre="Git : commit branch merge pull request",
        langage="Informatique",
        url="https://git-scm.com/doc",
        texte="""# Git — commandes essentielles

```bash
git init
git clone <url>
git status
git add .
git commit -m "message clair"
git branch feature-x
git checkout feature-x
git merge feature-x
git pull
git push origin main
```

Workflow : branches courtes + Pull Request + revue de code.
`.gitignore` pour exclure `.env`, `node_modules`, `__pycache__`.""",
    ),
    _e(
        nom="linux-bash-fr",
        titre="Linux et Bash essentiels",
        langage="Shell",
        url="https://tldp.org/LDP/abs/html/",
        texte="""# Linux / Bash — essentiels

```bash
pwd ; ls -la ; cd /chemin
cp a.txt b.txt ; mv a.txt dir/ ; rm fichier
mkdir -p projet/src
cat fichier ; less fichier ; head -n 20 fichier
grep -R "TODO" .
chmod +x script.sh
ps aux | grep python
curl -I https://example.com
```

Redirections : `>` écrase, `>>` ajoute, `|` pipe.
Variables : `export PATH="$PATH:/opt/bin"`.""",
    ),
    _e(
        nom="docker-bases-fr",
        titre="Docker : image container Dockerfile",
        langage="DevOps",
        url="https://docs.docker.com/get-started/",
        texte="""# Docker — bases

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t mon-api .
docker run -p 8000:8000 mon-api
docker ps
docker logs <id>
docker compose up -d
```

Image = recette ; container = instance en cours.
Volumes pour persister les données ; réseaux pour lier les services.""",
    ),
    _e(
        nom="reseaux-bases-fr",
        titre="Réseaux informatiques TCP IP DNS",
        langage="Informatique",
        url="https://developer.mozilla.org/fr/docs/Learn/Common_questions/Web_mechanics/How_does_the_Internet_work",
        texte="""# Réseaux informatiques — bases

- **IP** : adresse d'une machine (IPv4 / IPv6)
- **Port** : service (80 HTTP, 443 HTTPS, 22 SSH, 5432 Postgres)
- **TCP** : fiable, ordonné (HTTP, SSH)
- **UDP** : rapide, non garanti (DNS, streaming)
- **DNS** : nom → adresse IP
- **HTTP/HTTPS** : application web ; TLS chiffre HTTPS

Modèle simplifié : Client → DNS → TCP → TLS → HTTP → Serveur.""",
    ),
    _e(
        nom="securite-web-fr",
        titre="Sécurité web OWASP bases",
        langage="Sécurité",
        url="https://owasp.org/www-project-top-ten/",
        texte="""# Sécurité web — bases OWASP

Risques fréquents :
1. Injection SQL → requêtes paramétrées / ORM
2. XSS → échapper le HTML, CSP
3. CSRF → tokens anti-CSRF
4. Auth faible → mots de passe hashés (bcrypt), MFA
5. Secrets dans le code → variables d'environnement
6. Droits excessifs → principe du moindre privilège

Toujours valider les entrées côté serveur. HTTPS partout.""",
    ),
    _e(
        nom="tests-pytest-fr",
        titre="Tests unitaires avec pytest",
        langage="Python",
        url="https://docs.pytest.org/",
        texte="""# Tests avec pytest

```python
def addition(a, b):
    return a + b

def test_addition():
    assert addition(2, 3) == 5
```

```bash
pip install pytest
pytest -q
```

Bonnes pratiques : tests isolés, noms clairs, fixtures (`@pytest.fixture`), mocks pour les I/O.
Pyramide : beaucoup d'unitaires, quelques intégration, peu d'E2E.""",
    ),
    _e(
        nom="ci-cd-github-fr",
        titre="CI/CD avec GitHub Actions",
        langage="DevOps",
        url="https://docs.github.com/actions",
        texte="""# CI/CD avec GitHub Actions

Fichier `.github/workflows/ci.yml` :
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt
      - run: pytest -q
```

CI = tests automatiques à chaque push.
CD = déploiement automatique si les tests passent.""",
    ),
    _e(
        nom="js-es6-fr",
        titre="JavaScript ES6+ essentiels",
        langage="JavaScript",
        url="https://developer.mozilla.org/fr/docs/Web/JavaScript",
        texte="""# JavaScript moderne (ES6+)

```js
const somme = (a, b) => a + b;
const user = { nom: "Ada", age: 36 };
const { nom } = user;
const liste = [...[1, 2], 3];
const attente = async () => {
  const res = await fetch("/api/items");
  return res.json();
};
```

`let`/`const`, modules `import/export`, Promises/async-await, template strings.
Éviter `var`. Preférer `const` par défaut.""",
    ),
    _e(
        nom="nodejs-express-fr",
        titre="API Node.js avec Express",
        langage="JavaScript",
        url="https://expressjs.com/",
        texte="""# Créer une API avec Express.js

```bash
npm init -y
npm install express
```

```js
const express = require("express");
const app = express();
app.use(express.json());

app.get("/items", (req, res) => res.json([{ id: 1, name: "A" }]));
app.post("/items", (req, res) => res.status(201).json(req.body));

app.listen(3000, () => console.log("http://localhost:3000"));
```

Middleware = fonction `(req, res, next)`.""",
    ),
    _e(
        nom="html-css-fr",
        titre="HTML CSS bases frontend",
        langage="HTML",
        url="https://developer.mozilla.org/fr/docs/Learn",
        texte="""# HTML & CSS — bases frontend

```html
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8" />
  <title>Page</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <header><h1>Titre</h1></header>
  <main><p class="intro">Contenu</p></main>
</body>
</html>
```

```css
:root { --accent: #2563eb; }
body { font-family: system-ui; margin: 0; }
.intro { color: var(--accent); }
```

Sémantique HTML, flexbox/grid, responsive mobile-first.""",
    ),
    _e(
        nom="db-postgres-fr",
        titre="PostgreSQL introduction",
        langage="SQL",
        url="https://www.postgresql.org/docs/current/tutorial.html",
        texte="""# PostgreSQL — introduction

```sql
CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  email TEXT UNIQUE NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO users (email) VALUES ('ada@example.com');
SELECT * FROM users WHERE email LIKE '%@example.com';
```

Types utiles : `TEXT`, `INTEGER`, `BOOLEAN`, `JSONB`, `TIMESTAMPTZ`.
Outils : `psql`, pgAdmin, Docker image `postgres:16`.""",
    ),
    _e(
        nom="mongodb-fr",
        titre="MongoDB bases NoSQL",
        langage="NoSQL",
        url="https://www.mongodb.com/docs/manual/",
        texte="""# MongoDB — bases NoSQL

Document JSON (BSON) dans des collections.

```js
db.users.insertOne({ name: "Ada", tags: ["math", "cs"] })
db.users.find({ name: "Ada" })
db.users.updateOne({ name: "Ada" }, { $set: { active: true } })
```

Flexible pour schémas évolutifs. ODM : Mongoose (Node), Beanie (Python).""",
    ),
    _e(
        nom="os-processus-fr",
        titre="Systèmes d'exploitation processus threads",
        langage="Informatique",
        url="https://en.wikipedia.org/wiki/Operating_system",
        texte="""# Systèmes d'exploitation — processus et mémoire

- **Processus** : programme en exécution (espace mémoire isolé)
- **Thread** : fil d'exécution dans un processus (mémoire partagée)
- **Ordonnanceur** : décide quel thread tourne sur le CPU
- **Mémoire virtuelle** : isolation + swap
- **Fichiers / permissions** : rwx utilisateur/groupe/autres

Concurrency : verrous, deadlocks, race conditions.
En Python : `threading`, `multiprocessing`, `asyncio`.""",
    ),
    _e(
        nom="design-patterns-fr",
        titre="Design patterns utiles",
        langage="Informatique",
        url="https://refactoring.guru/design-patterns",
        texte="""# Design patterns utiles

- **Singleton** : une seule instance — à utiliser avec parcimonie
- **Factory** : créer des objets sans exposer la classe concrète
- **Strategy** : interchangeabilité d'algorithmes
- **Observer** : pub/sub (événements UI)
- **Repository** : accès données derrière une interface
- **Dependency Injection** : dépendances injectées (testable)

Un pattern n'est utile que s'il réduit la complexité réelle.""",
    ),
    _e(
        nom="ml-intro-fr",
        titre="Introduction machine learning",
        langage="Data Science",
        url="https://scikit-learn.org/stable/tutorial/basic/tutorial.html",
        texte="""# Machine Learning — introduction

Types :
- **Supervisé** : classification / régression
- **Non supervisé** : clustering, réduction de dimension
- **Renforcement** : agent + récompense

Pipeline : données → nettoyage → features → train/test → modèle → métriques.
Bibliothèques : scikit-learn, PyTorch, TensorFlow.
Attention au surapprentissage (overfitting).""",
    ),
    _e(
        nom="typescript-fr",
        titre="TypeScript bases types interfaces",
        langage="TypeScript",
        url="https://www.typescriptlang.org/docs/",
        texte="""# TypeScript — bases

```ts
interface User { id: number; name: string; active?: boolean }
function greet(u: User): string {
  return `Hello ${u.name}`;
}
const ids: number[] = [1, 2, 3];
type Id = string | number;
```

Typage statique pour JavaScript. `strict: true` recommandé dans `tsconfig.json`.""",
    ),
    _e(
        nom="graphql-fr",
        titre="GraphQL introduction",
        langage="API",
        url="https://graphql.org/learn/",
        texte="""# GraphQL — introduction

Le client demande exactement les champs dont il a besoin :

```graphql
query {
  user(id: "1") {
    name
    posts { title }
  }
}
```

Concepts : schema, types, queries, mutations, resolvers.
Utile quand web/mobile ont des besoins de données différents.""",
    ),
    _e(
        nom="websockets-fr",
        titre="WebSockets temps réel",
        langage="Informatique",
        url="https://developer.mozilla.org/fr/docs/Web/API/WebSockets_API",
        texte="""# WebSockets — communication temps réel

Connexion bidirectionnelle persistante (chat, notifications, collab).

```js
const ws = new WebSocket("wss://exemple.com/ws");
ws.onmessage = (e) => console.log(e.data);
ws.send(JSON.stringify({ type: "ping" }));
```

Côté Python : FastAPI WebSocket, Django Channels, Socket.IO.""",
    ),
    _e(
        nom="clean-archi-fr",
        titre="Architecture logicielle clean hexagonale",
        langage="Informatique",
        url="https://en.wikipedia.org/wiki/Hexagonal_architecture_(software)",
        texte="""# Architecture logicielle (clean / hexagonale)

Séparer :
1. **Domaine** : règles métier pures
2. **Application** : use cases / services
3. **Infrastructure** : DB, HTTP, fichiers

Dépendances pointent vers le domaine.
Avantages : tests faciles, changement de DB/UI sans casser le métier.
Pour un petit projet : rester simple.""",
    ),
    _e(
        nom="regex-fr",
        titre="Expressions régulières bases",
        langage="Informatique",
        url="https://developer.mozilla.org/fr/docs/Web/JavaScript/Guide/Regular_expressions",
        texte="""# Expressions régulières (regex) — bases

```python
import re
re.findall(r"\\b\\w+@\\w+\\.\\w+\\b", texte)
re.sub(r"\\s+", " ", texte).strip()
re.match(r"^\\d{4}-\\d{2}-\\d{2}$", "2026-07-13")
```

Métacaractères : `.` `*` `+` `?` `[]` `()` `\\d` `\\w` `\\s` `^` `$`
Tester sur regex101.com.""",
    ),
    _e(
        nom="async-python-fr",
        titre="Asyncio et programmation asynchrone Python",
        langage="Python",
        url="https://docs.python.org/3/library/asyncio.html",
        texte="""# Programmation asynchrone en Python (asyncio)

```python
import asyncio
import httpx

async def fetch(url: str) -> int:
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        return r.status_code

async def main():
    codes = await asyncio.gather(
        fetch("https://example.com"),
        fetch("https://httpbin.org/get"),
    )
    print(codes)

asyncio.run(main())
```

Utile pour I/O concurrentes. FastAPI est nativement async.""",
    ),
    _e(
        nom="env-secrets-fr",
        titre="Variables d'environnement et secrets",
        langage="Informatique",
        url="https://12factor.net/config",
        texte="""# Configuration et secrets (.env)

```bash
# .env (NE PAS committer)
GROQ_API_KEY=...
DATABASE_URL=postgresql://user:pass@localhost:5432/app
```

```python
from dotenv import load_dotenv
import os
load_dotenv()
api_key = os.getenv("GROQ_API_KEY")
```

Principes 12-factor : config hors code. Ajouter `.env` au `.gitignore`.""",
    ),
    _e(
        nom="api-design-fr",
        titre="Bonnes pratiques conception API",
        langage="API",
        url="https://swagger.io/resources/articles/best-practices-in-api-design/",
        texte="""# Bonnes pratiques de conception d'API

- Noms de ressources au pluriel : `/users`, `/orders`
- Verbes HTTP corrects (pas `/getUser`)
- Pagination : `?page=1&limit=20`
- Versioning : `/v1/...`
- Erreurs JSON homogènes : `{ "detail": "..." }`
- Documentation OpenAPI (/docs avec FastAPI)
- Idempotence pour PUT/DELETE
- Rate limiting et authentification""",
    ),
    _e(
        nom="debugging-fr",
        titre="Débogage méthodique",
        langage="Informatique",
        url="https://en.wikipedia.org/wiki/Debugging",
        texte="""# Débogage méthodique

1. Reproduire le bug de façon fiable
2. Lire le message d'erreur / stack trace en entier
3. Isoler : quel changement casse ?
4. Logger les entrées/sorties aux frontières
5. Utiliser le debugger (pdb, breakpoints)
6. Écrire un test qui échoue puis corriger
7. Vérifier les hypothèses

Erreur fréquente : corriger le symptôme sans comprendre la cause.""",
    ),
    _e(
        nom="json-xml-fr",
        titre="Formats de données JSON YAML XML",
        langage="Informatique",
        url="https://www.json.org/json-fr.html",
        texte="""# Formats de données : JSON, YAML, XML

**JSON** (APIs web) :
```json
{ "id": 1, "tags": ["a", "b"], "ok": true }
```

**YAML** (config) :
```yaml
server:
  port: 8000
  debug: false
```

Python : `json.loads` / `json.dumps`. Valider avec Pydantic / JSON Schema.""",
    ),
    _e(
        nom="orm-sqlalchemy-fr",
        titre="SQLAlchemy ORM introduction",
        langage="Python",
        url="https://docs.sqlalchemy.org/",
        texte="""# SQLAlchemy — introduction ORM

```python
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, Session

Base = declarative_base()
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True)

engine = create_engine("sqlite:///app.db")
Base.metadata.create_all(engine)

with Session(engine) as s:
    s.add(User(email="ada@example.com"))
    s.commit()
```

ORM = objets Python ↔ tables SQL. Attention N+1.""",
    ),
    _e(
        nom="frontend-state-fr",
        titre="Gestion d'état frontend",
        langage="JavaScript",
        url="https://react.dev/learn/managing-state",
        texte="""# Gestion d'état frontend

- **Local** : `useState` / `useReducer`
- **Partagé proche** : props ou Context
- **Global app** : Redux, Zustand, Pinia
- **Serveur** : React Query / SWR

Règle : remonter l'état au plus bas ancêtre commun.
Ne pas globaliser trop tôt.""",
    ),
    _e(
        nom="cli-python-fr",
        titre="Créer une CLI Python argparse",
        langage="Python",
        url="https://docs.python.org/3/library/argparse.html",
        texte="""# Créer une CLI en Python

```python
import argparse

parser = argparse.ArgumentParser(description="Mon outil")
parser.add_argument("fichier", help="chemin du fichier")
parser.add_argument("-v", "--verbose", action="store_true")
args = parser.parse_args()
print(args.fichier)
```

Alternatives : `typer`, `click`.""",
    ),
    _e(
        nom="django-bases-fr",
        titre="Django bases MTV vues modèles",
        langage="Python",
        url="https://docs.djangoproject.com/",
        texte="""# Django — bases

```bash
pip install django
django-admin startproject monprojet
cd monprojet
python manage.py startapp blog
python manage.py migrate
python manage.py runserver
```

Architecture MTV : Model (ORM), Template (HTML), View (logique).
Admin intégré, auth users, migrations SQL automatiques.
Idéal pour apps web complètes avec admin.""",
    ),
    _e(
        nom="kubernetes-intro-fr",
        titre="Kubernetes introduction pods services",
        langage="DevOps",
        url="https://kubernetes.io/docs/concepts/overview/",
        texte="""# Kubernetes — introduction

Orchestre des containers à grande échelle.

Concepts :
- **Pod** : plus petite unité (1+ containers)
- **Deployment** : réplicas + rolling update
- **Service** : IP stable / load balancing
- **Ingress** : entrée HTTP

```bash
kubectl get pods
kubectl apply -f deployment.yaml
kubectl logs <pod>
```

Utile en production multi-services ; Docker Compose suffit souvent en local.""",
    ),
    _e(
        nom="cloud-bases-fr",
        titre="Cloud computing IaaS PaaS SaaS",
        langage="Informatique",
        url="https://en.wikipedia.org/wiki/Cloud_computing",
        texte="""# Cloud computing — bases

- **IaaS** : machines virtuelles (AWS EC2, Azure VM)
- **PaaS** : plateforme app (Heroku, Railway, Render)
- **SaaS** : logiciel prêt (Gmail, Notion)

Avantages : scalabilité, paiement à l'usage, moins de hardware.
Concepts : régions, AZ, object storage (S3), CDN, serverless (Lambda/Functions).""",
    ),
    _e(
        nom="agile-scrum-fr",
        titre="Méthodes Agile et Scrum",
        langage="Informatique",
        url="https://www.scrum.org/resources/what-scrum-module",
        texte="""# Agile / Scrum — bases

Principes Agile : livrer souvent, collaboration, s'adapter au changement.

Scrum :
- **Sprint** : itération 1–4 semaines
- **Backlog** : liste priorisée de besoins
- **Daily** : synchro courte
- **Review / Rétro** : démo + amélioration

Rôles : Product Owner, Scrum Master, Dev Team.
User story : « En tant que … je veux … afin de … ».""",
    ),
    _e(
        nom="compilateurs-fr",
        titre="Compilation interprétation bytecode",
        langage="Informatique",
        url="https://en.wikipedia.org/wiki/Compiler",
        texte="""# Compilation vs interprétation

- **Compilé** (C, Go, Rust) : source → binaire machine
- **Interprété** (Python, JS historique) : exécuté ligne à ligne
- **Bytecode + VM** (Java JVM, Python CPython, C#) : compilé en bytecode puis exécuté

Étapes compilateur : lexing → parsing → analyse sémantique → IR → optimisation → codegen.
Python compile en `.pyc` puis interprète le bytecode.""",
    ),
    _e(
        nom="bdd-normalisation-fr",
        titre="Normalisation bases de données",
        langage="SQL",
        url="https://en.wikipedia.org/wiki/Database_normalization",
        texte="""# Normalisation des bases de données

But : réduire la redondance et les anomalies de mise à jour.

- **1NF** : valeurs atomiques, pas de listes dans une cellule
- **2NF** : 1NF + attributs dépendent de toute la clé
- **3NF** : 2NF + pas de dépendance transitive

Dénormalisation volontaire parfois pour la perf (caches, reporting).
Toujours définir clés primaires/étrangères et contraintes.""",
    ),
    _e(
        nom="cache-redis-fr",
        titre="Cache Redis introduction",
        langage="DevOps",
        url="https://redis.io/docs/latest/",
        texte="""# Cache avec Redis

Redis = store clé-valeur en mémoire (très rapide).

Usages : cache de réponses API, sessions, files, rate limiting, pub/sub.

```bash
SET user:1 '{"name":"Ada"}' EX 3600
GET user:1
```

Pattern cache-aside : lire Redis → miss → lire DB → écrire Redis.
Attention : invalidation du cache (TTL, purge à l'update).""",
    ),
    _e(
        nom="oauth-fr",
        titre="OAuth2 et OpenID Connect",
        langage="Sécurité",
        url="https://oauth.net/2/",
        texte="""# OAuth 2.0 / OpenID Connect

OAuth2 délègue l'autorisation (ex. « Se connecter avec Google »).
OpenID Connect ajoute l'identité (qui est l'utilisateur).

Flux Authorization Code (apps web) :
1. Redirection vers le provider
2. Consentement utilisateur
3. Code → échange contre access_token (+ id_token)
4. Appelle l'API avec Bearer token

Ne jamais utiliser le flux Implicit pour les nouvelles apps.
Librairies : Authlib, next-auth, spring-security-oauth.""",
    ),
    _e(
        nom="observabilite-fr",
        titre="Logs métriques tracing observabilité",
        langage="DevOps",
        url="https://opentelemetry.io/docs/concepts/observability-primer/",
        texte="""# Observabilité : logs, métriques, traces

- **Logs** : événements textuels (erreur, audit)
- **Métriques** : compteurs/jauges (CPU, latence p95, error rate)
- **Traces** : parcours d'une requête entre services

Stack courante : OpenTelemetry + Prometheus + Grafana + Loki/ELK.
Corréler avec un `request_id` / `trace_id`.
Alerter sur SLO (ex. disponibilité 99.9%).""",
    ),
    _e(
        nom="projet-erp-universitaire-fr",
        titre="Guide projet ERP universitaire Laravel Angular MVP",
        langage="PHP",
        url="https://laravel.com/docs",
        texte="""# Guide projet : ERP universitaire (cahier des charges → MVP)

## Principe
Un ERP université à 30+ modules ne se livre PAS en une fois.
Découper en MVP puis phases.

## MVP V1 (prioritaire)
1. Multi-tenant (université) + Paramètres
2. Utilisateurs + RBAC + Auth (JWT/Sanctum + MFA optionnel)
3. Académique de base : Facultés, Départements, Programmes, UE, ECTS
4. Étudiants (fiche) + Inscriptions
5. Emploi du temps simple (salles + conflits basiques)
6. Notes + Relevés
7. Paiements inscription (manuel + stub en ligne)
8. Dashboard Recteur / Enseignant / Étudiant (KPIs de base)

## Hors MVP (phases 2+)
Bibliothèque, RH complet, Comptabilité ERP, CRM, Transport, Résidences,
Cafétéria, Santé, Alumni, Mobile natif, IA (chatbot, plagiat), BI avancée,
reconnaissance faciale, GraphQL.

## Stack recommandée
- Backend : Laravel 11/12 (API REST) + PHP 8.3
- Frontend : Angular + Angular Material (ou Next.js si équipe JS)
- DB : PostgreSQL
- Cache : Redis
- Files : S3/MinIO
- Auth : Sanctum/JWT + RBAC policies
- Docker + GitHub Actions

## Étape 1 — bootstrap
```bash
composer create-project laravel/laravel erp-universite
cd erp-universite
# Windows: pas de source ; utiliser php artisan serve
php artisan install:api
php artisan make:model University -m
php artisan make:model Campus -m
```
Multi-tenant : table `universities` + `university_id` sur les modèles métier.
RBAC : spatie/laravel-permission (roles: super_admin, rector, dean, teacher, student).

## Entités cœur
University, Campus, Faculty, Department, User, Role, Student, Teacher,
Program, CourseUnit, Enrollment, Grade, Invoice, Classroom, TimetableSlot.""",
    ),
]


def _charger_knowledge() -> list[dict]:
    """Charge les guides markdown du dossier knowledge/ pour le RAG."""
    root = Path(__file__).resolve().parent.parent / "knowledge"
    if not root.is_dir():
        return []

    items: list[dict] = []
    for path in sorted(root.rglob("*.md")):
        texte = path.read_text(encoding="utf-8").strip()
        if len(texte) < 80:
            continue
        rel = path.relative_to(root).as_posix()
        nom = rel.replace("/", "-").removesuffix(".md")
        # Première ligne # titre si présente
        premiere = next((ln.strip() for ln in texte.splitlines() if ln.strip()), nom)
        titre = premiere.lstrip("# ").strip()[:120]
        categorie = path.parent.name  # best_practices | mentorat | perfect_answers
        langage = {
            "best_practices": "Methodology",
            "mentorat": "Mentoring",
            "perfect_answers": "Reference",
        }.get(categorie, "Knowledge")
        items.append(
            _e(
                texte=texte,
                nom=f"knowledge-{nom}",
                titre=titre,
                langage=langage,
                url=f"knowledge://{rel}",
            )
        )
    return items


ENRICHISSEMENTS = ENRICHISSEMENTS + _charger_knowledge()
