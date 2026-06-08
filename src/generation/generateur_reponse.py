"""
Module de génération de réponses en français via Groq (llama-3.3-70b-versatile)
avec citations systématiques des sources GitHub
"""

import os
from typing import List, Dict, Optional
from dotenv import load_dotenv
from groq import Groq

load_dotenv()


# ────────────────────────────────────────────────────────────────────
# PROMPT SYSTÈME
# ────────────────────────────────────────────────────────────────────

PROMPT_SYSTEME = """Tu es un assistant technique expert, spécialisé dans la documentation open-source GitHub.
Tu aides les développeurs francophones à comprendre et utiliser des bibliothèques et frameworks techniques.

RÈGLES STRICTES :
1. Réponds TOUJOURS en français naturel et clair.
2. Conserve les termes techniques en anglais (ex: "middleware", "callback", "endpoint", "commit", "pull request").
3. Base-toi UNIQUEMENT sur les documents fournis dans le contexte. Ne génère pas d'information hors contexte.
4. Cite TOUJOURS tes sources à la fin de ta réponse avec le format indiqué.
5. Si les documents ne contiennent pas la réponse, dis-le clairement en français.
6. Structure ta réponse avec des sections claires quand c'est pertinent.
7. Inclus des exemples de code si les documents en contiennent et qu'ils sont pertinents.

FORMAT DE RÉPONSE :
- Réponse principale en français
- Exemples de code si disponibles (conservés en anglais dans les blocs de code)
- Section "📚 Sources" avec les citations

FORMAT DES CITATIONS :
📚 Sources :
[1] {nom_repo} — {section} ({url})
[2] ...
"""

PROMPT_UTILISATEUR = """Voici les documents pertinents trouvés dans la documentation GitHub :

{contexte}

---

Question de l'utilisateur : {question}

Réponds en français en te basant uniquement sur les documents ci-dessus.
N'oublie pas de citer tes sources à la fin."""


class GenerateurReponse:
    """
    Génère des réponses en français à partir de documents contextuels
    en utilisant Groq (llama-3.3-70b-versatile).
    """

    def __init__(self):
        """Initialise le client Groq"""

        self.api_key     = os.getenv("GROQ_API_KEY")
        self.modele      = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
        self.temperature = float(os.getenv("LLM_TEMPERATURE", 0.1))
        self.max_tokens  = int(os.getenv("MAX_TOKENS", 2000))

        if not self.api_key:
            raise ValueError("❌ GROQ_API_KEY manquante dans le fichier .env")

        self.client = Groq(api_key=self.api_key)
        print(f"✅ Groq initialisé — modèle : {self.modele}")

    # ────────────────────────────────────────────────────────────────
    # CONSTRUCTION DU CONTEXTE
    # ────────────────────────────────────────────────────────────────

    def _construire_contexte(self, documents: List[Dict]) -> str:
        """
        Formate les documents récupérés en un contexte structuré
        pour le prompt LLM.
        """
        if not documents:
            return "Aucun document pertinent trouvé."

        blocs = []
        for i, doc in enumerate(documents, 1):
            bloc = (
                f"[Document {i}]\n"
                f"Repository : {doc.get('nom_complet', 'N/A')}\n"
                f"Section    : {doc.get('section_titre', 'N/A')}\n"
                f"Langage    : {doc.get('langage', 'N/A')}\n"
                f"URL        : {doc.get('url', 'N/A')}\n"
                f"Contenu    :\n{doc.get('texte', '')[:800]}\n"
            )
            blocs.append(bloc)

        return "\n" + ("─" * 50 + "\n").join(blocs)

    # ────────────────────────────────────────────────────────────────
    # CONSTRUCTION DES CITATIONS
    # ────────────────────────────────────────────────────────────────

    def _construire_citations(self, documents: List[Dict]) -> str:
        """
        Génère le bloc de citations structurées à partir des documents.
        """
        if not documents:
            return ""

        lignes = ["📚 **Sources :**"]
        for i, doc in enumerate(documents, 1):
            repo    = doc.get("nom_complet", "N/A")
            section = doc.get("section_titre", "N/A")
            url     = doc.get("url", "")
            lien    = f"[{repo}]({url})" if url else repo
            lignes.append(f"[{i}] {lien} — *{section}*")

        return "\n".join(lignes)

    # ────────────────────────────────────────────────────────────────
    # GÉNÉRATION DE LA RÉPONSE
    # ────────────────────────────────────────────────────────────────

    def generer(
        self,
        question  : str,
        documents : List[Dict],
        historique: Optional[List[Dict]] = None,
    ) -> Dict:
        """
        Génère une réponse en français avec citations.

        Args:
            question   : Question de l'utilisateur
            documents  : Documents récupérés par le retrieval hybride
            historique : Historique de conversation (optionnel)

        Returns:
            Dict avec clés :
              - reponse       : Texte complet de la réponse
              - reponse_seule : Réponse sans le bloc citations
              - citations     : Bloc citations formaté
              - documents     : Documents utilisés
              - tokens_utilises : Nombre de tokens consommés
        """

        # Construction du contexte
        contexte = self._construire_contexte(documents)

        # Construction du prompt utilisateur
        prompt = PROMPT_UTILISATEUR.format(
            contexte=contexte,
            question=question
        )

        # Construction des messages
        messages = [{"role": "system", "content": PROMPT_SYSTEME}]

        # Ajout de l'historique si fourni
        if historique:
            messages.extend(historique[-6:])  # 3 derniers échanges max

        messages.append({"role": "user", "content": prompt})

        # Appel à l'API Groq
        print(f"🤖 Génération via {self.modele}...")
        try:
            completion = self.client.chat.completions.create(
                model       = self.modele,
                messages    = messages,
                temperature = self.temperature,
                max_tokens  = self.max_tokens,
            )

            reponse_brute  = completion.choices[0].message.content
            tokens_utilises = completion.usage.total_tokens

            print(f"   ✅ Réponse générée ({tokens_utilises} tokens)")

        except Exception as e:
            print(f"   ❌ Erreur Groq : {e}")
            reponse_brute   = f"❌ Erreur lors de la génération : {str(e)}"
            tokens_utilises = 0

        # Construction du bloc citations séparé
        citations = self._construire_citations(documents)

        # Réponse finale : si le LLM n'a pas inclus les citations, on les ajoute
        if "📚" not in reponse_brute and citations:
            reponse_complete = reponse_brute.strip() + "\n\n" + citations
        else:
            reponse_complete = reponse_brute.strip()

        return {
            "reponse"         : reponse_complete,
            "reponse_seule"   : reponse_brute.strip(),
            "citations"       : citations,
            "documents"       : documents,
            "tokens_utilises" : tokens_utilises,
        }

    # ────────────────────────────────────────────────────────────────
    # AFFICHAGE TERMINAL
    # ────────────────────────────────────────────────────────────────

    def afficher_reponse(self, resultat: Dict) -> None:
        """Affiche la réponse de façon lisible dans le terminal"""
        print("\n" + "═" * 60)
        print("💬 RÉPONSE :")
        print("═" * 60)
        print(resultat["reponse"])
        print("═" * 60)
        print(f"📊 Tokens utilisés : {resultat['tokens_utilises']}")
        print(f"📄 Documents consultés : {len(resultat['documents'])}")
        print("═" * 60 + "\n")


# ────────────────────────────────────────────────────────────────────
# TEST RAPIDE
# ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from pathlib import Path

    # Ajouter src au path pour importer le retrieval
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    from retrieval.retrieval_hybride import RetrievalHybride

    # Initialisation
    moteur    = RetrievalHybride()
    generateur = GenerateurReponse()

    # Test
    questions = [
        "Comment créer une API REST avec Flask en Python ?",
        "Comment gérer les erreurs dans une application Node.js ?",
    ]

    for question in questions:
        print(f"\n{'═' * 60}")
        print(f"❓ Question : {question}")
        print("═" * 60)

        # Retrieval
        documents = moteur.rechercher(question, top_k_retrieval=20, top_k_final=5)

        # Génération
        resultat = generateur.generer(question, documents)
        generateur.afficher_reponse(resultat)