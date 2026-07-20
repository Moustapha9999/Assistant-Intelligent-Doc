# Référence — Microservices (quand / comment)

## Objectif
Comprendre quand découper un système en services indépendants — et quand NE PAS le faire.

## Compétences
API design, messages async, observabilité, CI/CD, ownership d’équipe.

## Quand oui
- Équipes multiples avec bounded contexts clairs
- Scale / cycle de release très différents
- Domaines découplables (billing ≠ catalogue)

## Quand non
- MVP / petite équipe
- Domaine encore flou
- Pas d’expérience ops (tracing, deploy, incident)

## Étapes si tu y vas
1. Monolithe modulaire d’abord
2. Identifier bounded contexts
3. Extraire un service à fort besoin d’autonomie
4. Contrat API + versioning
5. Observabilité (logs, metrics, traces)

## Risques
Latence réseau, consistency, debugging distribué, coûts ops.

## Conseil mentor
Si tu poses la question “dois-je faire des microservices ?” pour un premier projet : la réponse est presque toujours **non** — construis un monolithe propre.
