# Design patterns utiles (pragmatiques)

## Création
- **Factory** : centraliser la création d’objets complexes.
- **Builder** : objets avec beaucoup de paramètres optionnels.
- **Singleton** : à utiliser avec parcimonie (config, clients HTTP) ; difficile à tester.

## Structure
- **Adapter** : intégrer une API tierce sans polluer le domaine.
- **Facade** : simplifier un sous-système pour les appelants.
- **Decorator** : étendre un comportement sans modifier la classe de base.

## Comportement
- **Strategy** : remplacer des `if` de règles métier interchangeables.
- **Observer / Event** : découpler les réactions (emails, logs, metrics).
- **Command** : encapsuler une action (undo, files d’attente).

## Règle d’or
Un pattern n’est pas un objectif. Il résout une douleur réelle (duplication, couplage, variabilité). Sinon, code simple.
