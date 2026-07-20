# Estimer la difficulté

## Grille simple
| Taille | Signification | Exemple |
|--------|---------------|---------|
| S | < 1 jour, connu | Endpoint CRUD |
| M | 2–4 jours, quelques inconnues | Auth JWT + refresh |
| L | 1–2 semaines | Multi-tenant basique |
| XL | Spike requis | Sync offline, billing réel |

## Facteurs qui augmentent la difficulté
- Inconnues techniques
- Intégrations tierces
- Données legacy
- Contraintes sécurité / conformité
- Manque de specs

## Conseil
Si tu ne peux pas expliquer le plan en 5 bullet points, tu n’as pas assez découpé.
