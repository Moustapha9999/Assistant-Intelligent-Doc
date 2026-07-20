# Guidelines de code review

## Objectif
Améliorer le code et partager la connaissance — pas humilier l’auteur.

## Ce qu’il faut vérifier
- Correctness : le code fait-il ce qui est demandé ?
- Lisibilité et nommage
- Cas limites et gestion d’erreurs
- Sécurité (injections, secrets, auth)
- Tests pertinents
- Perf évidente (N+1, boucles inutiles)

## Comment commenter
- Pose des questions plutôt que des ordres quand c’est discutable
- Distingue *bloqueur* / *suggestion* / *nit*
- Propose une alternative concrète

## Pour l’auteur
- Explique le contexte dans la PR
- Réponds aux commentaires ou corrige
- Garde les PR petites
