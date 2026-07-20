# Découper un gros projet

## Technique des tranches verticales
Chaque étape livre une fonctionnalité utilisable de bout en bout (UI → API → DB), pas une couche entière isolée.

## Exemple e-commerce
1. Catalogue lecture seule
2. Panier local
3. Compte utilisateur
4. Commande + paiement stub
5. Admin produits
… plutôt que “toute la DB puis tout le front”.

## Heuristiques
- Si une tâche > 2–3 jours → découper
- Chaque slice a un critère d’acceptation clair
- Les dépendances dures (auth, schéma) viennent tôt mais minimales

## Anti-patterns
- Big bang
- “D’abord toute l’infra”
- Features parallèles sans intégration
