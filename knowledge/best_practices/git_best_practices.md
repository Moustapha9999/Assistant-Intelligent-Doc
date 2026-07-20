# Git — bonnes pratiques

## Commits
- Petits, atomiques, message clair (quoi + pourquoi).
- Présent de l’indicatif : `fix auth refresh on expired token`.
- Pas de secrets dans l’historique.

## Branches
- `main` toujours déployable.
- Feature branches courtes ; PR/MR avec description.
- Rebase ou merge selon la convention d’équipe — sois cohérent.

## Revue
- Relis ton diff avant de pousser.
- Une PR = un sujet.
- Tests / CI verts avant merge.

## Erreurs fréquentes
- `git commit -m "fix"` sans contexte
- Committer `node_modules` / `.env`
- Force-push sur `main`
- Branches zombies non fusionnées
