# Référence — Authentification JWT

## Explication
JWT transporte des claims signés (sub, exp). Le serveur vérifie la signature sans session serveur classique.

## Architecture
- `POST /auth/login` → access (+ refresh optionnel)
- Middleware/Depends qui valide Bearer token
- Rôles/claims pour l’autorisation

## Flux recommandé
1. Vérifier email/mot de passe (hash)
2. Émettre access token court (5–15 min)
3. Refresh token long, stocké avec prudence
4. Protéger les routes sensibles

## Pourquoi JWT
Scalable, adapté aux APIs stateless. Mais révocation plus complexe que sessions.

## Alternatives
Sessions serveur + cookie HttpOnly, OAuth2/OIDC (Auth0, Keycloak).

## Erreurs fréquentes
- Token sans expiration
- Secret faible / commit du secret
- Stocker JWT sensible exposé au XSS sans mitigation
- Confondre authentication et authorization

## Bonnes pratiques
HTTPS, `exp`/`iat`, rotation refresh, rate-limit login, tests d’accès refusé.
