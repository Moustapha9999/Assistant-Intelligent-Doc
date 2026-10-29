"""
Politique des mots de passe définis par leur titulaire (changement depuis l'interface).

Approche NIST SP 800-63B : longueur plutôt que règles de composition, refus des mots de passe
courants ou dérivés de l'identité. Aucune vérification contre une base de fuites en ligne
(pas d'envoi réseau depuis le serveur) : seule une liste locale de mots de passe courants est utilisée.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Tuple

LONGUEUR_MIN = 12
# scrypt accepte toute longueur ; la borne évite des calculs coûteux sur des saisies démesurées.
LONGUEUR_MAX = 128

_COURANTS = frozenset({
    "password", "passw0rd", "motdepasse", "azerty", "azertyuiop", "qwerty", "qwertyuiop", "qwertz",
    "abc", "abcdef", "abcdefgh", "admin", "administrateur", "administrator", "root", "user",
    "utilisateur", "assistdoc", "assistant", "letmein", "welcome", "bienvenue", "iloveyou",
    "jetaime", "soleil", "doudou", "loulou", "chouchou", "marseille", "football", "dragon",
    "monkey", "sunshine", "princess", "master", "secret", "changeme", "changezmoi", "test",
    "testtest", "default", "streamlit", "github", "google", "dakar", "senegal",
})
_SUITES = ("0123456789", "abcdefghijklmnopqrstuvwxyz", "azertyuiop", "qwertyuiop", "qsdfghjklm",
           "asdfghjkl", "wxcvbn", "zxcvbnm", "1q2w3e4r5t6y7u8i9o0p")


def _racine(mdp: str) -> str:
    """Forme réduite : minuscules, sans séparateurs, sans chiffres ni symboles en fin de chaîne."""
    s = re.sub(r"[\s._\-]+", "", mdp.lower())
    return re.sub(r"[\d\W_]+$", "", s)


def _est_suite(mdp: str) -> bool:
    s = mdp.lower()
    if len(set(s)) <= 3 or re.fullmatch(r"(.+?)\1+", s):
        return True
    return any(s in suite or s in suite[::-1] for suite in _SUITES)


def _identifiants(identifiants: Iterable[str]) -> List[str]:
    morceaux: List[str] = []
    for ident in identifiants:
        for partie in re.split(r"[@.\s_\-+]+", (ident or "").lower()):
            if len(partie) >= 4:
                morceaux.append(partie)
    return morceaux


def evaluer(mdp: str, identifiants: Iterable[str] = ()) -> List[Tuple[str, bool]]:
    """Exigences (libellé, respectée) — affichées telles quelles et appliquées par le serveur."""
    mdp = mdp or ""
    racine = _racine(mdp)
    bas = mdp.lower()
    return [
        (f"Au moins {LONGUEUR_MIN} caractères", len(mdp) >= LONGUEUR_MIN),
        (f"Au plus {LONGUEUR_MAX} caractères", len(mdp) <= LONGUEUR_MAX),
        ("Pas uniquement des espaces", bool(mdp.strip())),
        ("Pas un mot de passe courant, une suite de touches ou uniquement des chiffres",
         bool(racine) and racine not in _COURANTS and not _est_suite(mdp) and not _est_suite(racine)),
        ("Ne reprend pas votre adresse e-mail ou votre nom",
         not any(m in bas for m in _identifiants(identifiants))),
    ]


def erreurs(mdp: str, identifiants: Iterable[str] = ()) -> List[str]:
    return [f"Exigence non respectée : {libelle.lower()}." for libelle, ok in evaluer(mdp, identifiants) if not ok]
