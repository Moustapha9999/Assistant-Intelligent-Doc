"""
Module de génération de réponses enrichi v2
- LLM Groq (llama-3.3-70b-versatile)
- Connaissances générales + corpus RAG
- Web search DuckDuckGo (liens Wikipedia, YouTube, docs officielles)
- Raisonnement approfondi avec exemples de code
"""

import os
import re
import time
import requests
from typing import List, Dict, Optional
from dotenv import load_dotenv
from groq import Groq

load_dotenv()


# ════════════════════════════════════════════════════════════════
# PROMPT SYSTÈME ENRICHI
# ════════════════════════════════════════════════════════════════

PROMPT_SYSTEME = """Tu es un assistant technique expert de très haut niveau, équivalent à un senior developer avec 10+ ans d'expérience en développement logiciel, architecture système, data science et intelligence artificielle.

Tu combines :
1. Tes vastes connaissances générales en programmation et technologie
2. Les documents GitHub fournis dans le contexte
3. Des ressources web pour enrichir les réponses

RÈGLES FONDAMENTALES :
1. Réponds TOUJOURS en français naturel et clair.
2. Conserve les termes techniques en anglais (middleware, callback, endpoint, hook, promise, decorator, etc.).
3. Utilise les documents GitHub en PRIORITÉ quand ils sont pertinents, cite-les.
4. COMPLÈTE TOUJOURS avec tes connaissances générales — ne dis JAMAIS que tu ne peux pas répondre.
5. Fournis TOUJOURS des exemples de code complets, fonctionnels et bien commentés.
6. Explique le POURQUOI pas seulement le COMMENT.
7. Mentionne les alternatives et bonnes pratiques.
8. Inclus des liens vers des ressources externes utiles.

FORMAT DE RÉPONSE :

## [Titre clair]

[Introduction du concept en 2-3 phrases]

### Concepts clés
[Explication des notions importantes]

### Implémentation
[Code complet et commenté]

```python
# Exemple complet et fonctionnel
```

### Bonnes pratiques
[Tips et patterns recommandés]

### Alternatives
[Autres approches ou bibliothèques]

### Ressources
- 📖 [Documentation officielle](url)
- 📚 [Wikipedia](url)  
- 🎥 [Tutoriel vidéo](url)
- 💻 [Exemples GitHub](url)

📚 Sources GitHub du corpus :
[Citations]
"""

PROMPT_UTILISATEUR = """Contexte — Documents GitHub pertinents du corpus :

{contexte}

---

Ressources web disponibles :
{ressources_web}

---

Question : {question}

Consignes :
- Utilise les documents ET tes connaissances générales
- Fournis du code complet et fonctionnel
- Inclus les liens des ressources web
- Réponds en français, termes techniques en anglais
- Sois exhaustif comme un expert senior développeur
- Si les docs GitHub ne couvrent pas tout, complète avec tes connaissances
"""


# ════════════════════════════════════════════════════════════════
# WEB SEARCHER — DuckDuckGo gratuit
# ════════════════════════════════════════════════════════════════

class WebSearcher:
    """Recherche web via DuckDuckGo Instant Answer API"""

    def __init__(self):
        self.base_url = "https://api.duckduckgo.com/"
        self.headers  = {"User-Agent": "Mozilla/5.0 AssistDoc/1.0"}

    def rechercher(self, requete: str, nb_resultats: int = 5) -> List[Dict]:
        resultats = []
        try:
            params = {
                "q"           : requete,
                "format"      : "json",
                "no_html"     : 1,
                "skip_disambig": 1,
            }
            resp = requests.get(self.base_url, params=params,
                                headers=self.headers, timeout=5)
            data = resp.json()

            # Résultat principal Wikipedia
            if data.get("AbstractText") and data.get("AbstractURL"):
                resultats.append({
                    "titre"  : data.get("Heading", requete),
                    "url"    : data.get("AbstractURL", ""),
                    "extrait": data.get("AbstractText", "")[:300],
                    "source" : data.get("AbstractSource", "Wikipedia"),
                    "type"   : "definition",
                })

            # Résultats connexes
            for item in data.get("RelatedTopics", [])[:nb_resultats]:
                if isinstance(item, dict) and item.get("FirstURL"):
                    resultats.append({
                        "titre"  : item.get("Text", "")[:100],
                        "url"    : item.get("FirstURL", ""),
                        "extrait": item.get("Text", "")[:200],
                        "source" : "DuckDuckGo",
                        "type"   : "related",
                    })

        except Exception as e:
            print(f"   ⚠️  Web search: {e}")

        return resultats[:nb_resultats]

    def rechercher_multi(self, question: str) -> List[Dict]:
        """Recherche sur plusieurs angles : docs, wikipedia, tutoriels"""
        tous = []

        # Recherche principale
        tous.extend(self.rechercher(question))

        # Recherche documentation
        mots_cles = question.split()[:4]
        query_doc = " ".join(mots_cles) + " documentation tutorial"
        tous.extend(self.rechercher(query_doc, 3))

        # Déduplication par URL
        vus = set()
        uniques = []
        for r in tous:
            url = r.get("url", "")
            if url and url not in vus:
                vus.add(url)
                uniques.append(r)

        return uniques[:8]

    def formater(self, resultats: List[Dict]) -> str:
        if not resultats:
            return "Aucune ressource web disponible."
        lignes = []
        for r in resultats:
            if r.get("url") and r.get("titre"):
                titre = r["titre"][:80].strip()
                url   = r["url"]
                src   = r.get("source", "")
                lignes.append(f"- [{titre}]({url}) ({src})")
        return "\n".join(lignes) if lignes else "Aucune ressource web disponible."


# ════════════════════════════════════════════════════════════════
# GÉNÉRATEUR ENRICHI
# ════════════════════════════════════════════════════════════════

class GenerateurReponse:

    def __init__(self):
        self.api_key     = os.getenv("GROQ_API_KEY")
        self.modele      = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
        self.temperature = float(os.getenv("LLM_TEMPERATURE", 0.2))
        self.max_tokens  = int(os.getenv("MAX_TOKENS", 4000))

        if not self.api_key:
            raise ValueError("GROQ_API_KEY manquante")

        self.client   = Groq(api_key=self.api_key)
        self.searcher = WebSearcher()

        print(f"✅ Groq initialisé — {self.modele} | max_tokens={self.max_tokens}")

    def _construire_contexte(self, documents: List[Dict]) -> str:
        if not documents:
            return "Aucun document GitHub dans le corpus pour cette requête."
        blocs = []
        for i, doc in enumerate(documents, 1):
            score = doc.get("score_rerank", doc.get("score_dense", 0))
            blocs.append(
                f"[Doc {i}] score={score:.3f} | {doc.get('nom_complet','N/A')} "
                f"| {doc.get('section_titre','N/A')} | {doc.get('langage','N/A')}\n"
                f"URL: {doc.get('url','')}\n"
                f"{doc.get('texte','')[:1000]}"
            )
        return ("\n" + "─"*50 + "\n").join(blocs)

    def _construire_citations(self, documents: List[Dict], ressources: List[Dict]) -> str:
        lignes = ["📚 **Sources GitHub :**"]
        for i, doc in enumerate(documents, 1):
            repo    = doc.get("nom_complet", "N/A")
            section = doc.get("section_titre", "N/A")
            url     = doc.get("url", "")
            lien    = f"[{repo}]({url})" if url else repo
            lignes.append(f"[{i}] {lien} — *{section}*")

        if ressources:
            lignes.append("\n🌐 **Ressources web :**")
            for r in ressources[:6]:
                if r.get("url") and r.get("titre"):
                    lignes.append(f"- [{r['titre'][:60]}]({r['url']})")

        return "\n".join(lignes)

    def generer(
        self,
        question  : str,
        documents : List[Dict],
        historique: Optional[List[Dict]] = None,
    ) -> Dict:

        # 1. Web search
        print(f"   🌐 Recherche web...")
        ressources = self.searcher.rechercher_multi(question)
        ressources_str = self.searcher.formater(ressources)

        # 2. Contexte
        contexte = self._construire_contexte(documents)

        # 3. Prompt
        prompt = PROMPT_UTILISATEUR.format(
            contexte      = contexte,
            ressources_web= ressources_str,
            question      = question,
        )

        # 4. Messages
        messages = [{"role": "system", "content": PROMPT_SYSTEME}]
        if historique:
            messages.extend(historique[-6:])
        messages.append({"role": "user", "content": prompt})

        # 5. Appel Groq
        print(f"   🤖 Génération ({self.modele})...")
        try:
            completion = self.client.chat.completions.create(
                model      = self.modele,
                messages   = messages,
                temperature= self.temperature,
                max_tokens = self.max_tokens,
            )
            reponse_brute   = completion.choices[0].message.content
            tokens_utilises = completion.usage.total_tokens
            print(f"   ✅ {tokens_utilises} tokens")
        except Exception as e:
            print(f"   ❌ {e}")
            reponse_brute   = f"❌ Erreur : {e}"
            tokens_utilises = 0

        # 6. Assemblage
        citations = self._construire_citations(documents, ressources)
        if "📚" not in reponse_brute:
            reponse_complete = reponse_brute.strip() + "\n\n---\n\n" + citations
        else:
            reponse_complete = reponse_brute.strip()

        return {
            "reponse"        : reponse_complete,
            "reponse_seule"  : reponse_brute.strip(),
            "citations"      : citations,
            "documents"      : documents,
            "ressources_web" : ressources,
            "tokens_utilises": tokens_utilises,
        }

    def afficher_reponse(self, r: Dict) -> None:
        print("\n" + "═"*70)
        print(r["reponse"])
        print("═"*70)
        print(f"Tokens: {r['tokens_utilises']} | Docs: {len(r['documents'])} | Web: {len(r.get('ressources_web',[]))}")


# ════════════════════════════════════════════════════════════════
# TEST
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from retrieval.retrieval_hybride import RetrievalHybride

    moteur     = RetrievalHybride()
    generateur = GenerateurReponse()

    questions = [
        "Comment créer une API REST avec Flask en Python ?",
        "Comment implémenter l'authentification JWT avec Node.js ?",
        "Explique les hooks React useState et useEffect avec des exemples complets",
        "Comment utiliser SQLAlchemy pour créer des modèles et faire des requêtes ?",
        "Qu'est-ce que Docker et comment containeriser une application Python ?",
    ]

    for q in questions:
        print(f"\n{'═'*70}\n❓ {q}\n{'═'*70}")
        docs = moteur.rechercher(q, top_k_retrieval=20, top_k_final=5)
        res  = generateur.generer(q, docs)
        generateur.afficher_reponse(res)
        time.sleep(2)