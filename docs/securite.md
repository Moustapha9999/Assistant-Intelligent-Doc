# Sécurité d'AssistDoc — audit, renforcement et module d'administration

Document de référence (octobre 2026). Il décrit l'état **vérifié** de la sécurité de l'application :
ce qui a été constaté, ce qui a été corrigé, comment cela a été testé et ce qui reste à faire.
Rien ici n'est déclaré « corrigé » sans test automatisé associé (`tests/test_securite.py`).

---

## 1. Architecture concernée

| Composant | Rôle sécurité |
|---|---|
| `src/app/main.py`, `accueil.py`, `admin_page.py` | Interface Streamlit multipage ; la page Admin est déclarée pour tous mais **re-vérifie le rôle côté serveur** à chaque exécution. |
| `src/app/identite.py` | Résolution de l'identité à chaque run à partir du jeton de session (cookie `assistdoc_sid`, seul son SHA-256 est stocké). |
| `src/app/utilisateurs_sqlite.py` | Comptes, sessions, quotas, rôles, MFA, limitation des tentatives, **journal d'audit chaîné**. |
| `src/app/securite_sqlite.py` | Incidents (et leur historique), indicateurs, alertes, sauvegardes. |
| `src/app/admin_securite.py` | Section **Admin → Sécurité** (affichage ; aucune règle de sécurité n'y est décidée). |
| `src/securite/` | Fonctions pures : politique (paramètres bornés), TOTP RFC 6238, détection d'injection, catalogue d'événements, vérifications. |
| `src/api/` | API FastAPI optionnelle (locale) : clés API, clé admin dédiée, limitation de débit. |
| `scripts/securite_admin.py` | Procédure de récupération hors interface. |

Stockage : SQLite (`data/app/*.db`). En production (Streamlit Community Cloud) le disque est
**éphémère** : bases, inscriptions MFA et sauvegardes locales disparaissent au redéploiement.

Principe directeur : **chaque contrôle d'autorisation est appliqué dans la couche de données**
(`set_tier`, `suspendre`, incidents, sauvegardes vérifient que l'acteur est un administrateur
actif), l'interface ne fait que masquer ce qui serait de toute façon refusé.

---

## 2. Vulnérabilités confirmées lors de l'audit

| Gravité | Constat (avant) | Correctif |
|---|---|---|
| Élevée | Aucune limitation des tentatives de connexion (force brute possible). | Limitation par e-mail, par adresse IP (seuil ×4) et par compte pour la MFA ; blocage temporaire ; journalisation. |
| Élevée | Aucun second facteur pour les administrateurs. | MFA TOTP (RFC 6238) sans dépendance, anti-rejeu ; admin initial configurable par `ADMIN_TOTP_SECRET`. |
| Élevée | Quota invité contournable en effaçant le cookie → abus de coût sur l'API LLM. | Plafond **global** horaire des requêtes invitées (`QUOTA_INVITES_GLOBAL_HEURE`, défaut 200). |
| Moyenne | Changements de rôle / suspension contrôlés seulement par la page ; pas de protection du dernier admin. | Vérification de l'acteur en base, interdiction de l'auto-rétrogradation et du retrait du dernier admin, révocation des sessions. |
| Moyenne | Journal d'audit modifiable, sans trace des connexions ni des refus. | Journal **en ajout seul** (déclencheurs SQLite) + **chaîne d'empreintes SHA-256** ; événements de sécurité classés par gravité. |
| Moyenne | Contenus externes (fichiers, web, corpus) injectés dans le prompt sans délimitation. | Délimitation des données non fiables + règle système ; détection de tentatives de manipulation (signal, jamais décision). |
| Moyenne | Fichiers et audio réservés aux comptes uniquement dans le widget. | Refus côté serveur dans `_joindre_fichiers` / `_transcrire` + journalisation. |
| Moyenne | API : la clé admin retombait sur `ADMIN_PASSWORD` ; messages d'erreur internes renvoyés. | `ADMIN_API_KEY` dédiée (sinon 503), erreurs génériques, limitation de débit (429), refus journalisés. |
| Faible | « Compte suspendu » affiché avant la vérification du mot de passe (énumération). | Message générique ; la suspension n'est révélée qu'après un mot de passe correct. |
| Faible | Mot de passe minimal de 6 caractères. | 8 caractères minimum (1024 maximum). |

**Vérifiés solides (inchangés)** : hachage scrypt, sessions hachées et révocables, états OAuth à
usage unique liés à la session, isolation des données par propriétaire, contrôle des signatures
de fichiers (`securite_fichiers.py`), requêtes SQL paramétrées, absence de XSS confirmée (seul du
HTML statique ou échappé est injecté ; les réponses du modèle passent par le Markdown Streamlit).

---

## 3. Section « Admin → Sécurité »

Nouvel onglet du tableau de bord d'administration existant (pas d'application séparée), avec un
sélecteur de période (24 heures, 7 jours, 30 jours) :

1. **Vue d'ensemble** — indicateurs calculés en base (échecs, blocages, refus, incidents ouverts,
   administrateurs et MFA, sessions, signaux d'injection, répartition par gravité), alertes actives,
   derniers événements.
2. **Authentification et sessions** — politique en vigueur, MFA personnelle de l'administrateur
   connecté (configuration, activation, désactivation avec code), révocation des sessions
   (sauf la session courante, avec confirmation), événements d'authentification.
3. **Utilisateurs et permissions** — comptes privilégiés, matrice des permissions, changements de
   rôle et accès refusés (la gestion des comptes reste dans l'onglet Utilisateurs existant).
4. **Menaces et incidents** — alertes (échecs répétés, volume anormal, refus, injections…),
   ouverture d'incident depuis une alerte ou manuellement, suivi des statuts
   (ouvert → en analyse → résolu / faux positif) avec commentaire obligatoire et historique.
5. **Protection des données** — volumes réels (conversations, messages, éléments en quarantaine),
   sauvegardes (création avec confirmation, liste), règles appliquées.
6. **Sécurité des fichiers** — limites effectives (taille, nombre, pages, archives, pixels, délai),
   fichiers refusés.
7. **Sécurité de l'IA** — mesures appliquées, signaux d'injection, erreurs du service, volumes.
8. **Configuration de sécurité** — paramètres modifiables **validés et bornés côté serveur**,
   chaque modification journalisée (ancienne → nouvelle valeur). Les secrets ne sont jamais affichés :
   seule leur présence est indiquée.
9. **Rapports et vérifications** — exécution de vérifications réelles (statuts : Conforme,
   Alerte, Non configuré, Non vérifié), export Markdown, rapport `pip-audit`.

L'onglet **Audit** existant a été enrichi (catégorie, gravité, filtre, état d'intégrité de la chaîne).
Aucune donnée n'est inventée : en l'absence d'information, l'interface affiche « Non configuré »,
« Non vérifié » ou « Données indisponibles ».

---

## 4. Mécanismes implémentés

### Authentification
- Message d'échec unique pour un compte existant ou non ; hachage leurre de coût constant pour les
  e-mails inconnus (pas d'énumération par le temps de réponse).
- Blocage après `SECU_MAX_ECHECS` échecs (défaut 5) pendant `SECU_FENETRE_MIN` minutes (défaut 15) ;
  le compteur repart à zéro après un succès. Les clés stockées sont des **empreintes** de l'e-mail
  ou de l'IP, pas les valeurs.
- MFA TOTP : secret de 160 bits, 6 chiffres, tolérance d'un pas, **anti-rejeu** (dernier pas
  accepté mémorisé atomiquement), tentatives limitées, étape MFA expirant après 5 minutes.
- Changement de mot de passe et rétrogradation → révocation des sessions.

### Autorisations
- `set_tier`, `suspendre`, incidents, sauvegardes : refus si l'acteur n'est pas un administrateur
  actif et non suspendu ; refus journalisé en gravité « élevée ».
- Impossible de se retirer soi-même le rôle admin, de se suspendre, ou de retirer le dernier admin.
- L'accès à la page Admin par un non-administrateur est refusé **et journalisé**.
- Le modèle d'IA n'intervient dans **aucune** décision d'autorisation.

### Journal d'audit
- Table `admin_audit` étendue (catégorie, gravité, empreinte, empreinte précédente) ; déclencheurs
  `BEFORE UPDATE` / `BEFORE DELETE` qui rejettent toute modification.
- Chaque entrée contient `SHA-256(empreinte précédente + contenu)` ; `verifier_journal()` détecte
  toute modification d'une entrée passée (même hors application, déclencheurs supprimés).
- Jamais journalisés : mots de passe, jetons, clés API, contenu des documents. Les e-mails sont
  masqués (`al***@domaine`), les questions ne sont pas recopiées.
- Migration : sauvegarde automatique de la base (`*.avant_securite_<date>.bak`) avant ajout des
  colonnes ; les entrées antérieures sont signalées « antérieures au chaînage ».

### IA
- Les contenus externes (fichiers joints, extraits du corpus, résultats web) sont encadrés par
  `<<<DONNEES_NON_FIABLES …>>>` / `<<<FIN_DONNEES_NON_FIABLES>>>` ; les marqueurs présents dans le
  contenu sont neutralisés pour empêcher la fermeture prématurée du bloc.
- Règle système : ces blocs sont des données, jamais des instructions ; ils ne peuvent ni modifier
  le rôle de l'assistant, ni révéler des consignes ou des secrets, ni accorder de droits.
- Détection de motifs de manipulation (ignorer les consignes, révéler le prompt, changement de rôle,
  jailbreak, exfiltration de secrets, balises de rôle, élévation de privilèges) : **signal journalisé**,
  la requête n'est pas bloquée (faux positifs possibles) et la détection n'est pas une protection.
- Aucun secret n'est présent dans les prompts (testé).

### API REST
- `/admin/*` : `ADMIN_API_KEY` obligatoire (≥ 24 caractères conseillés), comparaison en temps
  constant, aucune retombée sur `ADMIN_PASSWORD`.
- `/ask`, `/feedback` : limitation par clé (`API_LIMITE_PAR_MINUTE`, défaut 30) → `429` + `Retry-After`.
- Erreurs internes : message générique, type d'exception seulement dans les journaux serveur.

### Changement de mot de passe par l'administrateur
- Accès unique : barre latérale de la page Admin, bloc du compte connecté → **Modifier mon mot de passe**
  (boîte de dialogue : mot de passe actuel, nouveau, confirmation ; code MFA si la MFA est active).
- `UtilisateursSQLite.modifier_mon_mot_de_passe(jeton_session, …)` : le compte est **déduit du jeton de
  session** (aucun identifiant accepté en paramètre), vérification du mot de passe actuel par scrypt,
  tentatives limitées (même seuil que la connexion), politique appliquée côté serveur, mise à jour
  conditionnée à l'ancien hachage (deux soumissions simultanées ne peuvent pas aboutir toutes deux).
- Politique (`securite/mots_de_passe.py`, recommandations NIST SP 800-63B) : 12 à 128 caractères,
  pas uniquement des espaces, refus des mots de passe courants, des suites de touches, des répétitions,
  des mots de passe uniquement numériques et de ceux qui reprennent l'e-mail ou le nom ; différent de
  l'actuel. Pas de règles de composition imposées. Pas de vérification contre une base de fuites
  (aucun appel réseau sortant) — liste locale uniquement.
- Sessions : les **autres** sessions du compte sont révoquées dans la même transaction ; la session
  courante est conservée et l'administrateur en est informé.
- Audit : `mot_de_passe_modifie` (acteur, date, nombre de sessions révoquées) et `mot_de_passe_echec` ;
  jamais de mot de passe, de hachage ni de jeton (testé).
- Pas de route REST : l'API FastAPI s'authentifie par clés techniques, sans comptes utilisateurs ;
  y ajouter cette opération créerait un second système d'authentification. L'opération passe par la
  session Streamlit authentifiée ; une requête intersite ne peut pas l'exécuter sans connaître le mot
  de passe actuel (et le code MFA), et `enableXsrfProtection` est explicitement activé.
- La réinitialisation hors interface (`scripts/securite_admin.py mot-de-passe`) applique la même politique.

### Paramètres
Stockés dans `runtime_ia.json` (mécanisme existant), validés (types, bornes, clés connues) avant
enregistrement **et** ramenés dans les bornes à la lecture (un fichier modifié à la main ne peut pas
désactiver la protection).

| Paramètre | Défaut | Bornes |
|---|---|---|
| `SECU_MAX_ECHECS` | 5 | 3–20 |
| `SECU_FENETRE_MIN` | 15 | 1–1440 |
| `SESSION_JOURS_COMPTE` | 14 | 1–90 |
| `SESSION_JOURS_INVITE` | 30 | 1–90 |
| `QUOTA_INVITES_GLOBAL_HEURE` | 200 | 0–100000 |
| `SECU_SEUIL_REQ_HEURE` | 60 | 5–10000 |
| `SECU_RETENTION_TENTATIVES_JOURS` | 30 | 1–365 |

### Nouvelles tables (justification)
- `auth_tentatives` : nécessaire pour la limitation des tentatives (persistante entre sessions).
- `incidents`, `incident_historique` : suivi des incidents avec traçabilité des changements de statut.
- Colonnes `users.totp_*` : MFA. Colonnes `admin_audit.categorie/gravite/empreinte*` : réutilisation
  du journal existant pour les événements de sécurité (pas de second système de journalisation).

---

## 5. Tests et résultats

Exécutés le 29/10/2026 sous Windows, Python 3.13, environnement local avec bases temporaires
(aucune base réelle, aucun compte réel, aucun service externe).

| Commande | Résultat |
|---|---|
| `pytest tests/test_securite.py` | **47 réussis** |
| `pytest tests/test_mot_de_passe.py` | **40 réussis** (changement de mot de passe : serveur, politique, interface) |
| `pytest` (suite complète) | **255 réussis, 4 ignorés**, 0 échec (référence avant travaux : 168 réussis) |
| `flake8 src tests scripts --select=E9,F63,F7,F82` (sélection de la CI) | **0** erreur |
| `pip-audit -r requirements.txt` | **Aucune vulnérabilité connue** (102 paquets) — `docs/securite/pip_audit.json` |
| `scripts/securite_admin.py` (5 commandes, base temporaire) | Fonctionnel ; compte inconnu refusé |

Couverture de `tests/test_securite.py` :
- TOTP : vecteurs officiels RFC 6238, fenêtre de tolérance, rejeu refusé ;
- connexion : message identique compte existant/inexistant, blocage puis déblocage, expiration du
  blocage, remise à zéro après succès, blocage par IP sur plusieurs comptes, suspension révélée
  seulement avec le bon mot de passe, absence de mot de passe et d'e-mail complet dans le journal ;
- MFA : activation, rejeu, blocage, désactivation, admin initial avec MFA, promotion d'un compte
  existant par les secrets (sessions révoquées, ancien mot de passe invalide) ;
- autorisations : auto-promotion refusée et journalisée, admin suspendu sans pouvoir, dernier admin
  protégé, révocation des sessions à la rétrogradation et à la suspension ;
- journal : modification et suppression rejetées, falsification détectée, migration d'un ancien journal ;
- plafond global des invités ; incidents (droits, commentaire obligatoire, historique) ;
  indicateurs exacts et filtrés par période ; sauvegardes réservées aux admins ; vérifications ;
- IA : 7 tentatives d'injection détectées, 3 questions légitimes non signalées, délimitation
  inviolable, règle système présente, aucun secret dans le prompt ;
- API : mot de passe admin refusé comme clé, 429 au-delà de la limite, erreur générique,
  clé invalide journalisée ;
- page Admin exécutée réellement (`streamlit.testing`) : refusée et journalisée pour un invité et un
  compte ordinaire ; pour un admin, 9 sous-sections présentes, indicateurs conformes à la base,
  vérifications et préparation MFA fonctionnelles.

---

## 6. Vérifications restant à faire (non automatisables ici)

- Tester la MFA avec une vraie application d'authentification (Google Authenticator, Aegis…).
- Sur le déploiement : renseigner `STREAMLIT_PUBLIC_URL`, `ADMIN_TOTP_SECRET`, un `ADMIN_PASSWORD`
  d'au moins 12 caractères, puis lancer Admin → Sécurité → Rapports et vérifications.
- Vérifier que `st.context.ip_address` est renseigné derrière le proxy de Streamlit Cloud (sinon la
  limitation par IP est inactive ; la limitation par e-mail reste active).
- Régénérer les clés API (GitHub, OpenAI, Anthropic, Groq) qui ont circulé en clair par le passé.
- Relancer `pip-audit` à chaque mise à jour des dépendances.

---

## 7. Risques résiduels et recommandations

| Risque | Recommandation |
|---|---|
| Cookie de session lisible par JavaScript (pas `HttpOnly`, contrainte de Streamlit). | Maintenir l'absence de HTML non échappé ; durée de session bornée. |
| Blocage par e-mail utilisable pour gêner un utilisateur (déni de service temporaire). | Fenêtre courte ; déblocage par l'admin ou le script. |
| Secret TOTP stocké en clair en base. | Chiffrement applicatif avec une clé de déploiement. |
| Disque éphémère : bases, MFA et sauvegardes perdues au redéploiement. | Base persistante externe ; `ADMIN_TOTP_SECRET` pour l'admin initial ; sauvegardes hors plateforme. |
| La chaîne d'empreintes ne détecte pas la suppression des **dernières** entrées. | Exporter périodiquement la dernière empreinte hors de la base. |
| Limiteur de l'API en mémoire, par processus. | Stockage partagé si plusieurs instances. |
| Les admins voient des extraits de questions (onglet Activité) et les retours. | Limiter ces vues ou les anonymiser. |
| Pas de politique de rétention des conversations ni de canal d'alerte (e-mail, webhook). | À définir. |
| CORS `*` sur l'API (authentification par en-tête, sans cookie). | Restreindre les origines si l'API est exposée publiquement. |
| Détection d'injection par motifs : contournable. | La défense repose sur la délimitation et sur l'absence de droits du modèle, pas sur la détection. |

---

## 8. Procédure de récupération de l'administration

À préparer **avant** d'activer la MFA en production.

**En local / serveur avec terminal** (`PYTHONPATH=src`) :

```bash
python scripts/securite_admin.py desactiver-mfa admin@exemple.com   # téléphone perdu
python scripts/securite_admin.py debloquer admin@exemple.com        # blocage après échecs
python scripts/securite_admin.py mot-de-passe admin@exemple.com     # saisie masquée, sessions révoquées
python scripts/securite_admin.py verifier-journal                   # code retour 2 si anomalie
python scripts/securite_admin.py sauvegarder
```

Chaque opération est journalisée avec l'acteur `cli`. Aucun secret n'est passé en argument.

**Sur Streamlit Community Cloud** (pas de terminal) : modifier les secrets `ADMIN_PASSWORD`
(et `ADMIN_TOTP_SECRET` ou le retirer), puis redémarrer l'application. Au démarrage, l'administrateur
est recréé ou ré-initialisé depuis les secrets, ses anciennes sessions sont révoquées et l'opération
est journalisée (`seed_admin`, gravité élevée).

---

## 9. Fiche pour la soutenance

**Problème.** Une application RAG publique expose trois surfaces : les comptes (vol d'accès admin),
le coût de l'API LLM (abus anonyme) et le modèle lui-même (manipulation par des contenus externes).

**Démarche.** Audit du code existant → classement des risques confirmés par gravité → corrections
ciblées dans la couche de données (pas de réécriture) → section d'administration qui *rend visibles*
ces mécanismes → tests automatisés sur la logique serveur, pas sur l'interface seule.

**Points forts à présenter.**
1. *Défense en profondeur* : l'interface masque, la base refuse. Un appel direct à `set_tier` par un
   non-admin échoue et laisse une trace.
2. *Journal infalsifiable sans infrastructure* : déclencheurs SQLite + chaîne SHA-256 (même principe
   qu'une blockchain, sans consensus) ; démonstration : modifier une ligne → anomalie détectée.
3. *MFA sans dépendance* : TOTP implémenté en moins de 80 lignes et validé par les vecteurs officiels RFC 6238.
4. *Sécurité de l'IA réaliste* : on ne prétend pas détecter toutes les injections ; on sépare données et
   instructions, et le modèle n'a aucun pouvoir sur les autorisations.
5. *Honnêteté des indicateurs* : aucune statistique fictive, états « Non configuré / Non vérifié »
   explicites.

**Chiffres vérifiables.** 47 tests de sécurité, 215 tests au total sans régression, 0 vulnérabilité
connue sur 102 dépendances (pip-audit), 10 vulnérabilités corrigées (3 élevées, 5 moyennes, 2 faibles).

**Limites assumées.** Voir section 7 : cookie non `HttpOnly`, disque éphémère, secret TOTP en clair,
détection d'injection par motifs.
