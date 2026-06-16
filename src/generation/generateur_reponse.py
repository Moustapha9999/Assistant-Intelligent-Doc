"""
Module de génération de réponses — Version adaptative
- Mode TECHNIQUE : code + structure + sources
- Mode CONVERSATION : réponse naturelle, sans formatage forcé
ISI KOMUNIK · Master IAGE
"""

import os
import time
import requests
from typing import List, Dict, Optional
from dotenv import load_dotenv
from groq import Groq

load_dotenv()


# ════════════════════════════════════════════════════════════════
# PROMPT SYSTÈME — ADAPTATIF
# ════════════════════════════════════════════════════════════════

PROMPT_SYSTEME = """Tu es un assistant intelligent francophone, équivalent à un senior developer ET un interlocuteur intellectuel polyvalent.

Tu adaptes TOTALEMENT ta réponse à la NATURE de la demande :

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔧 SI LA DEMANDE EST TECHNIQUE (code, programmation, debug, architecture...)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Fournis du code complet, fonctionnel et commenté
- Structure avec des sections claires (## Concepts, ### Implémentation, etc.)
- Cite les documents GitHub pertinents
- Ajoute des ressources web si utiles
- Explique le pourquoi, pas seulement le comment

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💬 SI LA DEMANDE EST CONVERSATIONNELLE (discussion, débat, opinion, conseil,
   réflexion, question générale, salutation, rédaction de texte non-code...)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Réponds de manière NATURELLE et FLUIDE, comme une vraie conversation
- PAS de titres ## obligatoires, PAS de structure forcée
- PAS de blocs de code si ce n'est pas demandé
- PAS de section "Sources GitHub" si elles ne sont pas pertinentes
- Adopte un ton humain, engageant, semblable à un échange entre personnes
- Si on te demande d'écrire un texte (article, lettre, poème...), fais-le
  directement sans préambule technique

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RÈGLES GÉNÉRALES (toujours valables)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Réponds TOUJOURS en français (sauf si on te demande une autre langue)
2. Les termes techniques restent en anglais (middleware, callback, etc.)
3. Utilise les documents GitHub fournis SEULEMENT s'ils sont pertinents
   pour la question posée — sinon, ignore-les complètement
4. Utilise tes connaissances générales librement
5. Ne mentionne JAMAIS que tu es "limité aux documents" ou que tu
   "n'as pas accès" à quelque chose
6. Les ressources web ne sont ajoutées QUE si elles enrichissent
   réellement une réponse technique — jamais pour du small talk
7. Garde un ton chaleureux et naturel en toutes circonstances

EXEMPLES DE COMPORTEMENT ATTENDU :
- "Salut, comment ça va ?" → réponse courte et amicale, rien d'autre
- "Que penses-tu du télétravail ?" → discussion d'opinion, pas de code
- "Écris-moi un poème sur la mer" → le poème directement
- "Comment faire un JOIN en SQL ?" → réponse technique avec code SQL
- "Explique-moi la différence entre REST et GraphQL" → réponse technique
  structurée avec exemples
- "Aide-moi à rédiger un mail de motivation" → le texte du mail, sans code
"""

PROMPT_UTILISATEUR_TECHNIQUE = """Contexte — Documents GitHub pertinents du corpus :

{contexte}

---

Ressources web disponibles :
{ressources_web}

---

Question : {question}

Consignes :
- Utilise les documents ET tes connaissances générales
- Fournis du code complet et fonctionnel si pertinent
- Inclus les liens des ressources web si utiles
- Réponds en français, termes techniques en anglais
"""

PROMPT_UTILISATEUR_SIMPLE = """Question / Message de l'utilisateur : {question}

Réponds de manière naturelle et adaptée à la demande. Si des informations
techniques du corpus ci-dessous sont pertinentes, utilise-les ; sinon ignore-les.

{contexte}
"""


# ════════════════════════════════════════════════════════════════
# DÉTECTION DU TYPE DE DEMANDE
# ════════════════════════════════════════════════════════════════

MOTS_CLES_TECHNIQUES = {
    # Programmation générale
    'code', 'fonction', 'classe', 'variable', 'algorithme', 'algorithm',
    'script', 'programme', 'programmation', 'développer', 'implémenter',
    'implement', 'debug', 'bug', 'erreur', 'error', 'exception',
    # Langages
    'python', 'javascript', 'typescript', 'java', 'sql', 'react', 'vue',
    'angular', 'node', 'flask', 'django', 'fastapi', 'docker', 'kubernetes',
    'api', 'rest', 'graphql', 'json', 'yaml', 'html', 'css',
    # Concepts dev
    'base de données', 'database', 'orm', 'sqlalchemy', 'requête',
    'serveur', 'server', 'backend', 'frontend', 'framework', 'librairie',
    'library', 'package', 'module', 'import', 'export', 'syntaxe',
    'syntax', 'compiler', 'compilation', 'git', 'github', 'déploiement',
    'deploy', 'authentification', 'jwt', 'oauth', 'middleware', 'hook',
    'composant', 'component', 'endpoint', 'route', 'pipeline', 'docker',
    'conteneur', 'container', 'test', 'pytest', 'unittest',
}


MOTS_CLES_EXPLICATION = {
    'explique', 'explication', 'qu\'est-ce que', 'qu est ce que', 'c\'est quoi',
    'parle-moi', 'parle moi', 'présente', 'présentation', 'définition',
    'définis', 'comprendre', 'apprendre', 'différence entre', 'avantages',
    'inconvénients', 'comment fonctionne', 'principe', 'concept', 'théorie',
    'historique de', 'qu\'est ce', 'machine learning', 'deep learning',
    'intelligence artificielle', 'data science', 'algorithme de',
}


def est_demande_technique(question: str) -> bool:
    """Détecte si la question nécessite une réponse technique structurée (code)"""
    q = question.lower()

    if '```' in question or 'def ' in question or 'function ' in question:
        return True

    nb_mots_cles = sum(1 for mot in MOTS_CLES_TECHNIQUES if mot in q)
    return nb_mots_cles >= 1


def necessite_recherche_web(question: str) -> bool:
    """Détecte si la question mérite des liens/ressources web réels,
    même en mode conversationnel (sujets éducatifs, explications, etc.)"""
    q = question.lower()

    if est_demande_technique(question):
        return True

    return any(mot in q for mot in MOTS_CLES_EXPLICATION)


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

            if data.get("AbstractText") and data.get("AbstractURL"):
                resultats.append({
                    "titre"  : data.get("Heading", requete),
                    "url"    : data.get("AbstractURL", ""),
                    "extrait": data.get("AbstractText", "")[:300],
                    "source" : data.get("AbstractSource", "Wikipedia"),
                })

            for item in data.get("RelatedTopics", [])[:nb_resultats]:
                if isinstance(item, dict) and item.get("FirstURL"):
                    resultats.append({
                        "titre"  : item.get("Text", "")[:100],
                        "url"    : item.get("FirstURL", ""),
                        "extrait": item.get("Text", "")[:200],
                        "source" : "DuckDuckGo",
                    })
                elif isinstance(item, dict) and "Topics" in item:
                    for sous in item["Topics"][:3]:
                        if sous.get("FirstURL"):
                            resultats.append({
                                "titre"  : sous.get("Text", "")[:100],
                                "url"    : sous.get("FirstURL", ""),
                                "extrait": sous.get("Text", "")[:200],
                                "source" : "DuckDuckGo",
                            })
        except Exception as e:
            print(f"   ⚠️  Web search: {e}")

        return resultats[:nb_resultats]

    def rechercher_html(self, requete: str, nb_resultats: int = 5) -> List[Dict]:
        """Fallback : scrape la page HTML de DuckDuckGo pour de vrais résultats organiques"""
        resultats = []
        try:
            resp = requests.get(
                "https://html.duckduckgo.com/html/",
                params={"q": requete},
                headers=self.headers,
                timeout=6,
            )
            import re
            # Extraction simple des liens résultats
            liens   = re.findall(r'class="result__a"[^>]*href="([^"]+)"', resp.text)
            titres  = re.findall(r'class="result__a"[^>]*>([^<]+)<', resp.text)

            for url, titre in zip(liens[:nb_resultats], titres[:nb_resultats]):
                # DuckDuckGo encode parfois les URLs via uddg=
                if "uddg=" in url:
                    import urllib.parse
                    try:
                        url = urllib.parse.unquote(url.split("uddg=")[1].split("&")[0])
                    except Exception:
                        pass
                if url.startswith("http"):
                    resultats.append({
                        "titre" : titre.strip(),
                        "url"   : url,
                        "extrait": "",
                        "source": "Web",
                    })
        except Exception as e:
            print(f"   ⚠️  Web search HTML: {e}")

        return resultats

    def rechercher_multi(self, question: str) -> List[Dict]:
        tous = []
        tous.extend(self.rechercher(question))

        # Wikipedia direct
        tous.extend(self.rechercher(f"{question} wikipedia", 2))

        # Résultats organiques réels (HTML)
        tous.extend(self.rechercher_html(question, 5))

        mots_cles = question.split()[:5]
        query_doc = " ".join(mots_cles) + " documentation officielle"
        tous.extend(self.rechercher_html(query_doc, 3))

        vus = set()
        uniques = []
        for r in tous:
            url = r.get("url", "")
            if url and url not in vus and "duckduckgo.com" not in url:
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
                lignes.append(f"- [{titre}]({r['url']}) ({r.get('source','')})")
        return "\n".join(lignes) if lignes else "Aucune ressource web disponible."


# ════════════════════════════════════════════════════════════════
# GÉNÉRATEUR ADAPTATIF
# ════════════════════════════════════════════════════════════════

class GenerateurReponse:

    def __init__(self):
        self.api_key     = os.getenv("GROQ_API_KEY")
        self.modele      = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
        self.temperature = float(os.getenv("LLM_TEMPERATURE", 0.3))
        self.max_tokens  = int(os.getenv("MAX_TOKENS", 4000))

        if not self.api_key:
            raise ValueError("GROQ_API_KEY manquante")

        self.client   = Groq(api_key=self.api_key)
        self.searcher = WebSearcher()

        print(f"✅ Groq initialisé — {self.modele} | max_tokens={self.max_tokens}")

    def _construire_contexte(self, documents: List[Dict]) -> str:
        if not documents:
            return ""
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

        # ── Détection du type de demande ──
        technique  = est_demande_technique(question)
        besoin_web = necessite_recherche_web(question)

        ressources = []
        citations  = ""

        if technique:
            # Mode technique : web search + contexte + citations
            print(f"   🔧 Mode technique détecté")
            print(f"   🌐 Recherche web...")
            ressources      = self.searcher.rechercher_multi(question)
            ressources_str  = self.searcher.formater(ressources)
            contexte        = self._construire_contexte(documents)

            prompt = PROMPT_UTILISATEUR_TECHNIQUE.format(
                contexte      = contexte if contexte else "Aucun document pertinent.",
                ressources_web= ressources_str,
                question      = question,
            )
            citations = self._construire_citations(documents, ressources)

        elif besoin_web:
            # Mode conversationnel ENRICHI : sujet éducatif → vrais liens, pas de code forcé
            print(f"   📘 Mode explication détecté")
            print(f"   🌐 Recherche web...")
            ressources     = self.searcher.rechercher_multi(question)
            ressources_str = self.searcher.formater(ressources)

            contexte = ""
            if documents and documents[0].get("score_rerank", 0) > 0.3:
                contexte = "Documents potentiellement utiles :\n" + self._construire_contexte(documents[:2])

            prompt = (
                f"Question : {question}\n\n"
                f"Réponds de manière naturelle, claire et bien rédigée, "
                f"sans forcer de structure technique ni de code si non nécessaire.\n\n"
                f"Ressources web trouvées (à citer en fin de réponse sous forme de liens "
                f"markdown réels) :\n{ressources_str}\n\n"
                f"{contexte}"
            )
            if ressources:
                citations = "🌐 **Pour aller plus loin :**\n" + "\n".join(
                    f"- [{r['titre'][:70]}]({r['url']})"
                    for r in ressources[:6] if r.get("url") and r.get("titre")
                )

        else:
            # Mode conversationnel : pas de web search, contexte minimal
            print(f"   💬 Mode conversationnel détecté")
            contexte = ""
            if documents:
                # On ne donne le contexte que s'il semble vraiment pertinent
                top_score = documents[0].get("score_rerank", 0)
                if top_score > 0.3:
                    contexte = "Documents potentiellement utiles :\n" + self._construire_contexte(documents[:2])

            prompt = PROMPT_UTILISATEUR_SIMPLE.format(
                question = question,
                contexte = contexte,
            )

        # ── Messages ──
        messages = [{"role": "system", "content": PROMPT_SYSTEME}]
        if historique:
            messages.extend(historique[-6:])
        messages.append({"role": "user", "content": prompt})

        # ── Appel Groq ──
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

        # ── Assemblage final ──
        if citations and "🌐" not in reponse_brute and "📚" not in reponse_brute:
            reponse_complete = reponse_brute.strip() + "\n\n---\n\n" + citations
        else:
            reponse_complete = reponse_brute.strip()

        mode_final = "technique" if technique else ("explication" if besoin_web else "conversation")

        return {
            "reponse"        : reponse_complete,
            "reponse_seule"  : reponse_brute.strip(),
            "citations"      : citations,
            "documents"      : documents if technique else [],
            "ressources_web" : ressources,
            "tokens_utilises": tokens_utilises,
            "mode"           : mode_final,
        }

    def afficher_reponse(self, r: Dict) -> None:
        print("\n" + "═"*70)
        print(f"[Mode: {r['mode']}]")
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
        "Salut, comment ça va ?",
        "Que penses-tu du télétravail pour les développeurs ?",
        "Comment créer une API REST avec Flask ?",
        "Écris-moi un petit poème sur le code.",
        "Aide-moi à rédiger un email pour demander un délai sur mon mémoire",
    ]

    for q in questions:
        print(f"\n{'═'*70}\n❓ {q}\n{'═'*70}")
        docs = moteur.rechercher(q, top_k_retrieval=20, top_k_final=5)
        res  = generateur.generer(q, docs)
        generateur.afficher_reponse(res)
        time.sleep(2)