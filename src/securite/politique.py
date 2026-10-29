"""Paramètres de sécurité : valeurs par défaut, bornes et validation côté serveur.

Ordre de lecture : `runtime_ia.json` (modifié depuis l'Admin) > variable d'environnement > défaut.
Toute valeur est ramenée dans ses bornes à la lecture : un fichier modifié à la main ne peut pas
désactiver une protection en dehors des limites prévues.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class Parametre:
    cle: str
    libelle: str
    defaut: int
    mini: int
    maxi: int
    aide: str = ""


PARAMETRES: Tuple[Parametre, ...] = (
    Parametre(
        "SECU_MAX_ECHECS", "Échecs de connexion avant blocage", 5, 3, 20,
        "Nombre d'échecs (par adresse e-mail) qui déclenche un blocage temporaire.",
    ),
    Parametre(
        "SECU_FENETRE_MIN", "Fenêtre de comptage et durée du blocage (minutes)", 15, 1, 1440,
        "Les échecs plus anciens ne comptent plus ; le blocage se lève de lui-même.",
    ),
    Parametre(
        "SESSION_JOURS_COMPTE", "Durée d'une session de compte (jours)", 14, 1, 90,
        "Session glissante : prolongée tant que le compte est utilisé.",
    ),
    Parametre(
        "SESSION_JOURS_INVITE", "Durée d'une session invitée (jours)", 30, 1, 90,
    ),
    Parametre(
        "QUOTA_INVITES_GLOBAL_HEURE", "Plafond global des requêtes invitées par heure", 200, 0, 100_000,
        "Limite le coût si des invités contournent leur quota en effaçant le cookie. 0 = désactivé.",
    ),
    Parametre(
        "SECU_SEUIL_REQ_HEURE", "Seuil d'alerte : requêtes d'un même compte par heure", 60, 5, 10_000,
        "Au-delà, le compte apparaît dans les volumes anormaux (aucun blocage automatique).",
    ),
    Parametre(
        "SECU_RETENTION_TENTATIVES_JOURS", "Conservation des tentatives de connexion (jours)", 30, 1, 365,
    ),
)

_PAR_CLE: Dict[str, Parametre] = {p.cle: p for p in PARAMETRES}


def _brut(cle: str) -> Any:
    try:
        from app import runtime_config

        valeurs = runtime_config.charger()
        if cle in valeurs:
            return valeurs[cle]
    except Exception:
        pass
    return os.getenv(cle)


def valeur(cle: str) -> int:
    p = _PAR_CLE[cle]
    try:
        v = int(float(_brut(cle)))
    except (TypeError, ValueError):
        return p.defaut
    return min(max(v, p.mini), p.maxi)


def valeurs() -> Dict[str, int]:
    return {p.cle: valeur(p.cle) for p in PARAMETRES}


def valider(saisies: Dict[str, Any]) -> Tuple[Dict[str, int], List[str]]:
    """Retourne (valeurs acceptées, erreurs). Une clé inconnue ou hors bornes est refusée."""
    propres: Dict[str, int] = {}
    erreurs: List[str] = []
    for cle, brut in saisies.items():
        p = _PAR_CLE.get(cle)
        if p is None:
            erreurs.append(f"Paramètre inconnu : {cle}.")
            continue
        if isinstance(brut, bool):
            erreurs.append(f"{p.libelle} : nombre entier attendu.")
            continue
        try:
            v = int(brut)
        except (TypeError, ValueError):
            erreurs.append(f"{p.libelle} : nombre entier attendu.")
            continue
        if isinstance(brut, float) and brut != v:
            erreurs.append(f"{p.libelle} : nombre entier attendu.")
            continue
        if not p.mini <= v <= p.maxi:
            erreurs.append(f"{p.libelle} : valeur attendue entre {p.mini} et {p.maxi}.")
            continue
        propres[cle] = v
    return propres, erreurs
