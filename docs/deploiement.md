# Déploiement — Streamlit Community Cloud + Qdrant Cloud

Architecture cible :

```
Streamlit Community Cloud (app, src/app/main.py)
 ├── Qdrant Cloud ............ recherche dense (collection github_docs, 144 701 points)
 ├── Release GitHub ......... corpus_assistdoc.zip (tous_chunks.json + cache BM25), téléchargé au 1er démarrage
 ├── Hugging Face ........... modèles d'embeddings et de reranking, téléchargés au 1er démarrage
 ├── Groq ................... génération (openai/gpt-oss-120b)
 └── Tavily ................. recherche web
```

Pourquoi ce découpage : `tous_chunks.json` (≈ 195 Mo) dépasse la limite de 100 Mo par fichier de
GitHub, et Streamlit Cloud ne peut pas faire tourner Qdrant. Le code n'a pas besoin d'être modifié
entre local et cloud : tout passe par des variables d'environnement.

---

## Étape 0 — Comptes à créer

| Service | Usage | Offre gratuite |
|---|---|---|
| [Qdrant Cloud](https://cloud.qdrant.io) | base vectorielle | 1 cluster, 1 Go RAM, 4 Go disque |
| [Streamlit Community Cloud](https://share.streamlit.io) | hébergement de l'app | connexion avec le compte GitHub |
| [Tavily](https://app.tavily.com) | recherche web | 1 000 requêtes / mois |
| [Groq](https://console.groq.com) | LLM (clé existante) | 8 000 tokens / min, 1 000 requêtes / jour |

---

## Étape 1 — Qdrant Cloud

1. Sur cloud.qdrant.io : **Create cluster** → *Free* → choisir une région proche (ex. `eu-central`).
2. Ouvrir le cluster → **API Keys** → créer une clé. La copier immédiatement (elle n'est plus réaffichée).
3. Noter l'URL du cluster : `https://<id>.<region>.cloud.qdrant.io:6333`.
4. Ajouter dans le `.env` local (jamais committé) :

   ```ini
   QDRANT_CLOUD_URL=https://<id>.<region>.cloud.qdrant.io:6333
   QDRANT_CLOUD_API_KEY=<clé>
   ```

5. Qdrant local démarré (`docker compose -f docker/docker-compose.yml up -d qdrant`), vérifier :

   ```bash
   python scripts/migrer_vers_qdrant_cloud.py --dry-run
   ```

   Attendu : `[source] localhost:6333/github_docs — 144701 points` puis `Qdrant Cloud joignable`.

6. Copier la collection :

   ```bash
   python scripts/migrer_vers_qdrant_cloud.py
   ```

   - La base locale est seulement lue (aucune écriture, aucune suppression).
   - Copie par lots de 256 avec reprise : en cas de coupure, relancer la même commande.
   - L'indexation HNSW est suspendue pendant le chargement puis réactivée ; les payloads sont
     stockés sur disque (`on_disk_payload`) pour tenir dans 1 Go de RAM.
   - Fin attendue : `source=144701 cible=144701` et 5 recherches de contrôle `OK`.
   - `--recreer` supprime et recrée la collection **cible** (Qdrant Cloud) uniquement.

> Les clusters gratuits inactifs sont suspendus puis supprimés après une période sans usage
> (voir la page de facturation Qdrant). En cas de suppression, relancer simplement l'étape 1.

---

## Étape 2 — Archive du corpus (release GitHub)

1. Générer l'archive (reconstruit le cache BM25 si besoin) :

   ```bash
   python scripts/preparer_corpus_deploiement.py
   ```

   Sortie : `deploy/corpus_assistdoc.zip` (≈ 88 Mo) et la ligne `CORPUS_SHA256 = …` à conserver.
   `deploy/` est ignoré par git.

2. Publier l'archive comme asset de release :

   - **En ligne de commande** (après `gh auth login`) :

     ```bash
     gh release create corpus-v1 deploy/corpus_assistdoc.zip \
       --title "Corpus AssistDoc v1" \
       --notes "tous_chunks.json (144 018 chunks) + cache BM25. SHA-256 : <empreinte>"
     ```

   - **Ou dans le navigateur** : dépôt GitHub → *Releases* → *Draft a new release* → tag
     `corpus-v1` → glisser `corpus_assistdoc.zip` → *Publish release*.

3. URL de téléchargement (dépôt public, sans authentification) :

   ```
   https://github.com/Moustapha9999/Assistant-Intelligent-Doc/releases/download/corpus-v1/corpus_assistdoc.zip
   ```

Si le corpus change : régénérer l'archive, publier `corpus-v2`, mettre à jour `CORPUS_URL` et
`CORPUS_SHA256`, puis redémarrer l'app (*Reboot*) pour vider le disque éphémère.

---

## Étape 3 — Pousser le code

```bash
git status                       # vérifier : ni .env, ni secrets.toml, ni deploy/, ni data/
git add -A
git commit -m "Préparation du déploiement cloud"
git push origin master
```

Contrôle des secrets avant le push :

```bash
git ls-files | grep -Ei "\.env$|secrets\.toml$|\.p8$"   # doit être vide
```

La CI GitHub Actions (lint + pytest avec `requirements-dev.txt`) doit être verte.

---

## Étape 4 — Streamlit Community Cloud

1. share.streamlit.io → **Create app** → *Deploy a public app from GitHub*.
2. Paramètres :
   - Repository : `Moustapha9999/Assistant-Intelligent-Doc`
   - Branch : `master`
   - Main file path : `src/app/main.py`
   - App URL : `assistant-intelligent-doc` → `https://assistant-intelligent-doc.streamlit.app`
3. **Advanced settings** :
   - Python version : **3.12**
   - Secrets : coller le contenu de [`.streamlit/secrets.toml.example`](../.streamlit/secrets.toml.example)
     complété (clé Groq, URL + clé Qdrant Cloud, `CORPUS_URL`, `CORPUS_SHA256`, clé Tavily,
     identifiants admin). Les clés de premier niveau deviennent des variables d'environnement.
4. **Deploy**. Streamlit installe `requirements.txt` (torch CPU via l'index PyTorch).

### Premier démarrage (≈ 3–6 min)

1. Installation des dépendances.
2. Première question : téléchargement des modèles Hugging Face (≈ 560 Mo) et de l'archive du
   corpus (88 Mo, empreinte vérifiée), chargement du BM25 depuis le cache (≈ 7 s).
3. Les démarrages suivants réutilisent le disque tant que le conteneur n'est pas recyclé.

### OAuth (optionnel)

URL de redirection en production : `https://assistant-intelligent-doc.streamlit.app/`
- secrets : `GITHUB_OAUTH_REDIRECT_URI`, `GOOGLE_OAUTH_REDIRECT_URI`, `STREAMLIT_PUBLIC_URL` ;
- Google Cloud Console → client OAuth → *URI de redirection autorisés* : **ajouter** cette URL
  (garder `http://localhost:8501/` pour le local) ;
- GitHub → OAuth App → *Authorization callback URL* : une seule URL par application ; créer une
  seconde OAuth App « prod » pour ne pas casser la connexion locale.

---

## Étape 5 — Vérifications après déploiement

| Test | Attendu |
|---|---|
| Logs (*Manage app*) | `Corpus installé`, ni `Chunks introuvables` ni erreur Qdrant |
| « Comment créer une route GET avec FastAPI ? » | citation `fastapi/fastapi` (📚 Sources GitHub) |
| « Comment écrire un Dockerfile multi-stage ? » | citation du corpus Docker, pas seulement du web |
| Question d'actualité | bloc 🌐 Ressources web alimenté par Tavily |
| Connexion admin | identifiants des secrets |

---

## Limites connues de l'hébergement gratuit

- **Historique et comptes (SQLite)** : le disque de Streamlit Cloud est éphémère ; les
  conversations, comptes et quotas sont perdus à chaque redémarrage ou redéploiement.
  L'administrateur est recréé automatiquement depuis les secrets.
- **Mémoire** : ≈ 2,7 Go maximum ; l'app en consomme ≈ 1,8 Go (modèles + BM25 + chunks).
- **Groq gratuit** : 8 000 tokens/min — une à deux réponses longues par minute. Garder des quotas
  bas (déjà fait dans le modèle de secrets).
- **Mise en veille** : l'app s'endort sans trafic ; le réveil recharge les modèles (≈ 1 min).
- **Non disponibles sur Streamlit Cloud** : l'API FastAPI (`src/api`) et *Sign in with Apple*
  (callback servi par l'API). Ils restent utilisables en local / Docker.

---

## Docker local (inchangé)

`docker/docker-compose.yml` continue d'utiliser Qdrant local (`http://qdrant:6333`) et le corpus
monté depuis `data/`. Pour tester l'image contre Qdrant Cloud, définir `QDRANT_URL` et
`QDRANT_API_KEY` dans `.env` et retirer la ligne `QDRANT_URL` imposée dans le compose.

## Dépannage

| Symptôme | Cause probable | Action |
|---|---|---|
| `CORPUS_SHA256 ne correspond pas` | archive remplacée ou empreinte mal copiée | relancer `preparer_corpus_deploiement.py`, recopier l'empreinte |
| `Unauthorized` / 403 Qdrant | clé absente ou erronée | vérifier `QDRANT_API_KEY` dans les secrets |
| Timeout Qdrant | cluster suspendu (inactivité) | le réactiver dans la console Qdrant ; `QDRANT_TIMEOUT=60` |
| App redémarre seule (*Oh no*) | mémoire dépassée | redémarrer ; éviter les fichiers envoyés volumineux |
| `Rate limit` Groq | 8 000 tokens/min atteints | patienter une minute ; baisser `MAX_TOKENS` |
| Web vide | `TAVILY_API_KEY` absente | DuckDuckGo est bloqué depuis les serveurs cloud : ajouter la clé |
