"""Mots de passe à usage unique basés sur le temps (TOTP, RFC 6238) — sans dépendance externe.

Compatible avec les applications d'authentification courantes (Google Authenticator,
Microsoft Authenticator, FreeOTP…) : HMAC-SHA1, 6 chiffres, pas de 30 secondes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from typing import Optional
from urllib.parse import quote, urlencode

PAS_S = 30
CHIFFRES = 6


def generer_secret() -> str:
    """Secret aléatoire de 160 bits, encodé en base32 sans remplissage."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _cle(secret: str) -> bytes:
    s = (secret or "").replace(" ", "").upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def pas_courant(instant: Optional[float] = None) -> int:
    return int((time.time() if instant is None else instant) // PAS_S)


def code_pour_pas(secret: str, pas: int, chiffres: int = CHIFFRES) -> str:
    mac = hmac.new(_cle(secret), struct.pack(">Q", pas), hashlib.sha1).digest()
    decalage = mac[-1] & 0x0F
    valeur = struct.unpack(">I", mac[decalage:decalage + 4])[0] & 0x7FFFFFFF
    return str(valeur % (10 ** chiffres)).zfill(chiffres)


def verifier(
    secret: str,
    code: str,
    dernier_pas: Optional[int] = None,
    instant: Optional[float] = None,
    tolerance: int = 1,
) -> Optional[int]:
    """Pas correspondant au code (dérive d'horloge ±`tolerance`), sinon None.

    Un code d'un pas déjà utilisé (`dernier_pas`) est refusé : pas de rejeu.
    """
    code = (code or "").strip().replace(" ", "")
    if not secret or len(code) != CHIFFRES or not code.isdigit():
        return None
    try:
        actuel = pas_courant(instant)
        for pas in range(actuel - tolerance, actuel + tolerance + 1):
            if dernier_pas is not None and pas <= dernier_pas:
                continue
            if hmac.compare_digest(code_pour_pas(secret, pas), code):
                return pas
    except (ValueError, TypeError):
        return None
    return None


def uri_provisioning(secret: str, compte: str, emetteur: str = "AssistDoc") -> str:
    """URI `otpauth://` à saisir (ou scanner) dans l'application d'authentification."""
    libelle = quote(f"{emetteur}:{compte}")
    return f"otpauth://totp/{libelle}?" + urlencode(
        {"secret": secret, "issuer": emetteur, "algorithm": "SHA1", "digits": CHIFFRES, "period": PAS_S}
    )
