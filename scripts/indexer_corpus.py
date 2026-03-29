"""
Script principal pour indexer tout le corpus dans Qdrant
"""

import sys
from pathlib import Path

# Ajouter le dossier src au path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from indexing.generateur_embeddings import GenerateurEmbeddings
from indexing.gestionnaire_qdrant import GestionnaireQdrant


def main():
    """Pipeline complet d'indexation"""
    
    print("=" * 60)
    print(" A- PIPELINE D'INDEXATION COMPLÈTE")
    print("=" * 60)
    
    # ÉTAPE 1 : Générer les embeddings
    print("\n ÉTAPE 1/2 : Génération des embeddings")
    print("-" * 60)
    
    generateur = GenerateurEmbeddings()
    embeddings, chunks = generateur.generer_pour_chunks()
    
    # ÉTAPE 2 : Indexer dans Qdrant
    print("\n ÉTAPE 2/2 : Indexation dans Qdrant")
    print("-" * 60)
    
    gestionnaire = GestionnaireQdrant()
    gestionnaire.indexer_chunks()
    
    # Test final
    print("\n B- TEST FINAL")
    print("-" * 60)
    
    gestionnaire.tester_recherche(
        requete="How to create a REST API with Python?",
        top_k=5
    )
    
    print("\n" + "=" * 60)
    print(" INDEXATION TERMINÉE AVEC SUCCÈS !")
    print("=" * 60)
    
    print("\n C- Résumé:")
    print(f"   - {len(chunks)} chunks indexés")
    print(f"   - Dimension embeddings: {embeddings.shape[1]}")
    print(f"   - Collection Qdrant: {gestionnaire.collection_name}")
    print(f"   - Host Qdrant: {gestionnaire.host}:{gestionnaire.port}")


if __name__ == "__main__":
    main()