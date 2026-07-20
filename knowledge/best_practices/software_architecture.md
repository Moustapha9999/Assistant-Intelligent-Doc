# Architecture logicielle — bonnes pratiques

## Principes
- Sépare les responsabilités (présentation, domaine, données, infrastructure).
- Préfère une architecture simple qui évolue plutôt qu’un over-engineering initial.
- Définis des frontières claires (modules, packages, services) et des contrats stables (API, DTO).
- La scalabilité commence par la clarté du modèle métier, pas par Kubernetes.

## Styles courants
| Style | Quand l’utiliser | Limite |
|-------|------------------|--------|
| Monolithe modulaire | MVP, équipe petite | Refactoring discipliné requis |
| Couches (API / Service / Repo) | Apps classiques CRUD | Risque de logique anémique |
| Hexagonale / ports-adapters | Domaine riche, tests | Courbe d’apprentissage |
| Microservices | Équipes multiples, scale indépendant | Complexité ops élevée |

## Checklist avant de choisir
1. Taille de l’équipe et maturité DevOps
2. Besoin réel de déploiement indépendant
3. Complexité du domaine métier
4. Contraintes de délais (MVP vs long terme)

## Erreurs fréquentes
- Microservices trop tôt
- Couplage fort base de données ↔ UI
- Absence de couches (tout dans les controllers)
- Pas de stratégie d’erreurs / observabilité
