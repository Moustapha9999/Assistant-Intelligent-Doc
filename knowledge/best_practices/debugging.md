# Débogage efficace

## Méthode
1. Reproduire le bug de façon fiable
2. Isoler (réduire le périmètre)
3. Former une hypothèse
4. Vérifier avec logs / debugger / tests
5. Corriger la cause, pas le symptôme
6. Ajouter un test de non-régression

## Outils
- Debugger (breakpoints) > print aléatoires
- Logs structurés avec niveaux
- Bisect git si régression
- Minimal reproducible example

## Erreurs fréquentes
- Modifier 10 choses à la fois
- “Ça marche sur ma machine” sans reproduire
- Ignorer les stack traces
- Corriger sans comprendre
