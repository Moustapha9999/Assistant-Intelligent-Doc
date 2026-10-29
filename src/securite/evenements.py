"""Vocabulaire des événements de sécurité enregistrés dans le journal d'audit.

Un événement est une observation (ex. un échec de connexion), pas une attaque confirmée :
seul un administrateur qualifie un incident.
"""

from __future__ import annotations

import hashlib

GRAVITES = ("info", "faible", "moyenne", "elevee", "critique")
LIBELLES_GRAVITE = {
    "info": "Information",
    "faible": "Faible",
    "moyenne": "Moyenne",
    "elevee": "Élevée",
    "critique": "Critique",
}

CATEGORIE_ADMIN = "admin"
CATEGORIE_SECURITE = "securite"

TYPES = {
    "auth_succes": "Connexion réussie",
    "auth_echec": "Échec de connexion",
    "auth_verrouillage": "Blocage après échecs répétés",
    "auth_bloquee": "Tentative pendant un blocage",
    "auth_compte_suspendu": "Connexion d'un compte suspendu",
    "auth_deblocage": "Blocage de connexion levé",
    "mot_de_passe_reinitialise": "Mot de passe réinitialisé",
    "mot_de_passe_modifie": "Mot de passe modifié par son titulaire",
    "mot_de_passe_echec": "Échec de changement de mot de passe",
    "oauth_echec": "Échec de connexion OAuth",
    "mfa_echec": "Code MFA invalide",
    "mfa_active": "MFA activée",
    "mfa_desactive": "MFA désactivée",
    "acces_refuse": "Accès refusé",
    "session_revoquee": "Sessions révoquées",
    "quota_depasse": "Quota dépassé",
    "quota_global_invites": "Plafond global invités atteint",
    "fichier_refuse": "Fichier refusé",
    "ia_injection_suspecte": "Manipulation d'instructions suspectée",
    "ia_erreur": "Erreur du service d'IA",
    "api_acces_refuse": "Accès API refusé",
    "api_limite": "Limite de débit API atteinte",
    "config_securite": "Paramètres de sécurité modifiés",
    "verification_securite": "Vérifications de sécurité exécutées",
    "sauvegarde": "Sauvegarde des bases",
    "incident_cree": "Incident ouvert",
    "incident_statut": "Statut d'incident modifié",
    "seed_admin": "Administrateur initial (secrets)",
    "set_tier": "Rôle modifié",
    "suspend": "Compte suspendu",
    "unsuspend": "Compte réactivé",
}

# Échecs d'authentification comptés dans le tableau de bord
TYPES_ECHEC_AUTH = ("auth_echec", "auth_bloquee", "mfa_echec", "oauth_echec", "mot_de_passe_echec")


def libelle_type(action: str) -> str:
    return TYPES.get(action, action)


def gravite_valide(gravite: str) -> str:
    return gravite if gravite in GRAVITES else "info"


def masquer_email(email: str) -> str:
    """« alice@exemple.com » → « al***@exemple.com » (journal sans adresse complète)."""
    email = (email or "").strip().lower()
    if "@" not in email:
        return "***"
    local, domaine = email.split("@", 1)
    return f"{local[:2]}***@{domaine}"


def cle_tentative(nature: str, valeur: str) -> str:
    """Clé de comptage des tentatives : empreinte, jamais la valeur (e-mail, IP) en clair."""
    h = hashlib.sha256((valeur or "").strip().lower().encode("utf-8")).hexdigest()[:32]
    return f"{nature}:{h}"
