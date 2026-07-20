# Principes SOLID (pratiques)

## S — Single Responsibility
Un module change pour une seule raison. Sépare validation, persistance, et présentation.

## O — Open/Closed
Ouvert à l’extension, fermé à la modification. Préfère stratégies/plugins plutôt que `if/elif` infinis.

## L — Liskov Substitution
Un sous-type doit pouvoir remplacer son parent sans casser le contrat. Pas de surprises (exceptions, comportements affaiblis).

## I — Interface Segregation
Plusieurs interfaces ciblées > une interface fourre-tout. Le client ne dépend que de ce qu’il utilise.

## D — Dependency Inversion
Le domaine dépend d’abstractions, pas de détails (DB, HTTP). Injecte les dépendances.

## Application concrète
- Controllers minces, services métier testables
- Repositories derrière une interface
- Config et I/O isolés des règles métier

## Erreur fréquente
Appliquer SOLID partout dès le jour 1 → complexité inutile. Commence simple, extrais quand la douleur apparaît.
