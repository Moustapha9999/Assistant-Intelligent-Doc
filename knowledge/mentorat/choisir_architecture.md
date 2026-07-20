# Comment choisir une architecture

## Questions à poser
1. Combien de personnes vont maintenir ça ?
2. Quel volume / latence réellement attendu ?
3. Faut-il déployer des parties indépendamment ?
4. Le domaine est-il simple (CRUD) ou riche (règles complexes) ?
5. Quel délai pour un premier livrable ?

## Recommandations pragmatiques
- **Débutant / MVP** → monolithe modulaire + API claire
- **Domaine riche** → couches + services métier testables
- **Équipes multiples + scale** → envisager services, pas avant

## Décision
Documente le choix (ADR court) : contexte, options, décision, conséquences.
Revisite si les hypothèses changent.
