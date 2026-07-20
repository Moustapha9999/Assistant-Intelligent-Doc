"""Interface en ligne de commande de l'assistant."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.orchestrateur import OrchestrateurAssistant


def main() -> None:
    parser = argparse.ArgumentParser(description="Assistant Intelligent Doc")
    sous_commandes = parser.add_subparsers(dest="commande", required=True)
    for nom, aide in (("ask", "Génère une réponse RAG"), ("search", "Affiche les documents trouvés")):
        cmd = sous_commandes.add_parser(nom, help=aide)
        cmd.add_argument("question")
        cmd.add_argument("--top-k", type=int, default=5)

    args = parser.parse_args()
    orchestrateur = OrchestrateurAssistant()
    resultat = orchestrateur.repondre(args.question, top_k=args.top_k)
    if args.commande == "search":
        for i, doc in enumerate(resultat.documents, 1):
            score = doc.get("score_confiance", doc.get("score_rerank", doc.get("score_dense", 0)))
            print(f"[{i}] score={score:.3f} · {doc.get('nom_complet', 'source inconnue')}")
            print(f"    {doc.get('section_titre', '')}: {doc.get('texte', '')[:240]}")
        return

    print(resultat.reponse)


if __name__ == "__main__":
    main()
