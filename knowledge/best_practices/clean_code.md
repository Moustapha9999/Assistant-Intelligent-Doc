# Clean Code — bonnes pratiques

## Nommage
- Noms intentionnels : `calculerTotalTTC` plutôt que `calc`.
- Fonctions = verbes ; classes/modules = noms.
- Évite les abréviations obscures et les booléens négatifs (`isNotReady`).

## Fonctions
- Une responsabilité claire, idéalement courte.
- Peu d’arguments (idéalement ≤ 3) ; sinon objet de paramètres.
- Pas d’effets de bord cachés.

## Structure
- Code qui se lit comme une prose technique.
- Early return pour réduire l’imbrication.
- Dupliquer légèrement vaut mieux qu’une abstraction prématurée.

## Commentaires
- Expliquent le *pourquoi*, pas le *quoi* déjà clair dans le code.
- Code douteux → refactor, pas un long commentaire.

## Erreurs fréquentes
- God class / god function
- Noms génériques (`data`, `info`, `manager`)
- Magic numbers sans constantes
- Catch vide ou `except Exception` trop large
