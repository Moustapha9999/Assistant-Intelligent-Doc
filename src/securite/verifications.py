"""Vérifications de sécurité exécutables depuis l'Admin.

Chaque contrôle lit un état réel (base, variables d'environnement, fichiers). S'il ne peut
pas conclure, il le dit (« non_verifie » / « non_configure ») au lieu de supposer.
Aucune valeur secrète n'est renvoyée : seulement sa présence ou sa robustesse.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import config
from app.sqlite_outils import lecture
from securite import politique

OK, ALERTE, NON_CONFIGURE, NON_VERIFIE = "ok", "alerte", "non_configure", "non_verifie"
LIBELLES_STATUT = {
    OK: "Conforme",
    ALERTE: "À corriger",
    NON_CONFIGURE: "Non configuré",
    NON_VERIFIE: "Non vérifié",
}

RAPPORT_DEPENDANCES = config.PROJECT_ROOT / "docs" / "securite" / "pip_audit.json"


@dataclass
class Verification:
    code: str
    titre: str
    statut: str
    detail: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


def _env(nom: str) -> str:
    return (os.getenv(nom) or "").strip()


def lire_rapport_dependances(chemin: Path = RAPPORT_DEPENDANCES) -> Optional[Dict[str, Any]]:
    """Rapport `pip-audit --format json` versionné ; None s'il n'a jamais été produit."""
    if not chemin.exists():
        return None
    try:
        data = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    deps = data.get("dependencies", data) if isinstance(data, dict) else data
    vulnerables = [
        {"nom": d.get("name"), "version": d.get("version"),
         "vulns": [v.get("id") for v in d.get("vulns") or []],
         "correctifs": sorted({f for v in d.get("vulns") or [] for f in v.get("fix_versions") or []})}
        for d in deps or [] if d.get("vulns")
    ]
    return {
        "date": datetime.fromtimestamp(chemin.stat().st_mtime, timezone.utc).isoformat(),
        "paquets": len(deps or []),
        "vulnerables": vulnerables,
        "nb_vulns": sum(len(v["vulns"]) for v in vulnerables),
    }


def executer(users, securite) -> List[Verification]:
    """`users` : UtilisateursSQLite ; `securite` : SecuriteSQLite."""
    resultats: List[Verification] = []
    ajouter = lambda *a: resultats.append(Verification(*a))  # noqa: E731

    with lecture(users.chemin) as conn:
        anciens = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE password_hash IS NOT NULL "
            "AND password_hash NOT LIKE 'scrypt$%'"
        ).fetchone()["n"]
    ajouter("hachage", "Hachage des mots de passe (scrypt)",
            ALERTE if anciens else OK,
            f"{anciens} compte(s) avec l'ancien format SHA-256 (re-hachés à la prochaine connexion)."
            if anciens else "Tous les mots de passe stockés utilisent scrypt avec sel aléatoire.")

    secret_admin = _env("ADMIN_PASSWORD") or _env("STREAMLIT_PASSWORD")
    if not secret_admin:
        ajouter("secret_admin", "Secret de l'administrateur initial", NON_CONFIGURE,
                "ADMIN_PASSWORD absent : aucun administrateur n'est créé automatiquement.")
    elif len(secret_admin) < 12:
        ajouter("secret_admin", "Secret de l'administrateur initial", ALERTE,
                "ADMIN_PASSWORD fait moins de 12 caractères.")
    else:
        ajouter("secret_admin", "Secret de l'administrateur initial", OK, "Longueur suffisante (≥ 12).")

    res = securite.resume(datetime.now(timezone.utc).isoformat())
    ajouter("admins", "Administrateurs actifs", OK if res["admins"] else ALERTE,
            f"{res['admins']} administrateur(s) actif(s)." if res["admins"]
            else "Aucun administrateur actif : l'administration est inaccessible.")
    ajouter("mfa_admins", "Second facteur des administrateurs",
            ALERTE if res["admins_sans_mfa"] else (OK if res["admins"] else NON_VERIFIE),
            f"{res['admins_sans_mfa']} administrateur(s) sans MFA." if res["admins_sans_mfa"]
            else "Tous les administrateurs actifs ont activé la MFA.")

    ajouter("limitation", "Limitation des tentatives de connexion", OK,
            f"Blocage après {politique.valeur('SECU_MAX_ECHECS')} échecs sur "
            f"{politique.valeur('SECU_FENETRE_MIN')} min (e-mail), seuil ×4 par adresse IP.")
    plafond = politique.valeur("QUOTA_INVITES_GLOBAL_HEURE")
    ajouter("plafond_invites", "Plafond global des requêtes invitées", OK if plafond else ALERTE,
            f"{plafond} requêtes invitées par heure au maximum." if plafond
            else "Désactivé : un invité peut contourner son quota en effaçant le cookie.")

    journal = users.verifier_journal()
    ajouter("journal", "Intégrité du journal d'audit", OK if journal["valide"] else ALERTE,
            (f"{journal['total']} entrée(s), chaîne d'empreintes intacte"
             + (f" ({journal['non_chainees']} antérieure(s) au chaînage)." if journal["non_chainees"] else "."))
            if journal["valide"] else
            f"Chaîne rompue à l'entrée #{journal['premiere_anomalie']} : entrée modifiée ou supprimée.")

    ajouter("ssl", "Vérification des certificats TLS sortants",
            ALERTE if _env("DISABLE_SSL_VERIFY") == "1" else OK,
            "DISABLE_SSL_VERIFY=1 : les certificats ne sont plus vérifiés." if _env("DISABLE_SSL_VERIFY") == "1"
            else "Vérification active (valeur par défaut).")

    url = _env("STREAMLIT_PUBLIC_URL")
    if url.startswith("https://"):
        ajouter("https", "HTTPS de l'application", OK, "URL publique en HTTPS : cookie de session « Secure ».")
    elif url.startswith("http://") and not any(h in url for h in ("localhost", "127.0.0.1")):
        ajouter("https", "HTTPS de l'application", ALERTE, "URL publique en HTTP : le cookie circule en clair.")
    else:
        ajouter("https", "HTTPS de l'application", NON_VERIFIE,
                "STREAMLIT_PUBLIC_URL non déclarée ou locale : HTTPS non vérifiable depuis le serveur.")

    cle_admin_api = _env("ADMIN_API_KEY")
    if not cle_admin_api:
        ajouter("api_admin", "Clé d'administration de l'API REST", NON_CONFIGURE,
                "ADMIN_API_KEY absente : les routes /admin/* de l'API répondent 503 (fermées).")
    elif len(cle_admin_api) < 24 or cle_admin_api == secret_admin:
        ajouter("api_admin", "Clé d'administration de l'API REST", ALERTE,
                "Clé trop courte (< 24 caractères) ou identique au mot de passe administrateur.")
    else:
        ajouter("api_admin", "Clé d'administration de l'API REST", OK, "Clé dédiée et suffisamment longue.")
    ajouter("api_cles", "Clés d'accès de l'API REST", OK if _env("API_KEYS") else NON_CONFIGURE,
            "API_KEYS définie : /ask et /feedback exigent X-API-Key." if _env("API_KEYS")
            else "API_KEYS vide : si l'API est lancée, /ask est accessible sans clé (usage local uniquement).")

    gitignore = config.PROJECT_ROOT / ".gitignore"
    if gitignore.exists():
        lignes = {ligne.strip() for ligne in gitignore.read_text(encoding="utf-8").splitlines()}
        manquants = [m for m in (".env", ".streamlit/secrets.toml") if m not in lignes]
        ajouter("gitignore", "Secrets exclus du dépôt Git", ALERTE if manquants else OK,
                f"Absents de .gitignore : {', '.join(manquants)}." if manquants
                else ".env et .streamlit/secrets.toml sont ignorés par Git.")
    else:
        ajouter("gitignore", "Secrets exclus du dépôt Git", NON_VERIFIE, ".gitignore introuvable sur ce serveur.")

    ajouter("cle_llm", "Clé du fournisseur d'IA (Groq)", OK if _env("GROQ_API_KEY") else NON_CONFIGURE,
            "Définie côté serveur uniquement (jamais affichée ni transmise au navigateur)."
            if _env("GROQ_API_KEY") else "GROQ_API_KEY absente : génération indisponible.")

    rapport = lire_rapport_dependances()
    if rapport is None:
        ajouter("dependances", "Vulnérabilités connues des dépendances", NON_VERIFIE,
                "Aucun rapport pip-audit (docs/securite/pip_audit.json).")
    else:
        ajouter("dependances", "Vulnérabilités connues des dépendances",
                ALERTE if rapport["nb_vulns"] else OK,
                f"Rapport du {rapport['date'][:10]} : {rapport['nb_vulns']} vulnérabilité(s) "
                f"dans {len(rapport['vulnerables'])} paquet(s) sur {rapport['paquets']}.")

    sauvegardes = securite.lister_sauvegardes()
    if not sauvegardes:
        ajouter("sauvegardes", "Sauvegardes des bases", NON_CONFIGURE,
                "Aucune sauvegarde : créez-en une depuis « Protection des données ».")
    else:
        ajouter("sauvegardes", "Sauvegardes des bases", OK,
                f"Dernière sauvegarde : {sauvegardes[0]['date'][:16]} ({len(sauvegardes)} conservée(s)). "
                "Stockées sur le même disque que les bases.")
    return resultats


def resume_resultats(resultats: List[Verification]) -> Dict[str, int]:
    compte = {s: 0 for s in LIBELLES_STATUT}
    for r in resultats:
        compte[r.statut] = compte.get(r.statut, 0) + 1
    return compte
