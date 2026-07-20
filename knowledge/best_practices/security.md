# Sécurité applicative — bases

## Principes
- Least privilege
- Valider toutes les entrées utilisateur
- Ne jamais faire confiance au client
- Secrets hors du code (env / vault)
- Dépendances à jour

## Auth & sessions
- Mots de passe hashés (argon2/bcrypt)
- JWT : courte durée, refresh maîtrisé, pas de secrets en localStorage si XSS possible
- CSRF pour cookies de session
- Rate limiting sur login

## Données
- Paramétrer les requêtes SQL (pas de concat)
- Échapper les sorties HTML (XSS)
- Chiffrer les données sensibles au repos si requis

## Erreurs fréquentes
- Secrets commités
- CORS `*` en production avec credentials
- Logs contenant tokens / mots de passe
- Admin sans audit
