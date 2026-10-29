"""
Récupération et contrôle de sécurité hors interface (accès au serveur requis).

À utiliser si un administrateur perd son second facteur, est bloqué par la limitation des
tentatives ou a oublié son mot de passe. Chaque opération est enregistrée dans le journal
d'audit (acteur « cli »). Aucun secret n'est accepté en argument de ligne de commande
(il resterait dans l'historique du shell) : le mot de passe est demandé de façon masquée.

Usage :
  python scripts/securite_admin.py desactiver-mfa admin@exemple.com
  python scripts/securite_admin.py debloquer admin@exemple.com
  python scripts/securite_admin.py mot-de-passe admin@exemple.com
  python scripts/securite_admin.py verifier-journal
  python scripts/securite_admin.py sauvegarder
  python scripts/securite_admin.py --base data/app_copie/utilisateurs.db verifier-journal

Sur Streamlit Community Cloud (pas de terminal) : le disque est réinitialisé au redémarrage
(« Reboot ») et l'administrateur est recréé depuis les secrets ADMIN_EMAIL / ADMIN_PASSWORD
(et ADMIN_TOTP_SECRET si la MFA doit être active dès le démarrage).
"""

from __future__ import annotations

import argparse
import getpass
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import config  # noqa: E402
from app.utilisateurs_sqlite import UtilisateursSQLite  # noqa: E402
from securite.evenements import CATEGORIE_SECURITE, cle_tentative  # noqa: E402

ACTEUR = "cli"


def _compte(db: UtilisateursSQLite, email: str) -> dict:
    with sqlite3.connect(db.chemin) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT id FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    if row is None:
        sys.exit(f"Aucun compte pour {email}.")
    return db.obtenir(row["id"])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", type=Path, default=config.DB_DIR / "utilisateurs.db")
    sous = parser.add_subparsers(dest="commande", required=True)
    for nom in ("desactiver-mfa", "debloquer", "mot-de-passe"):
        sous.add_parser(nom).add_argument("email")
    sous.add_parser("verifier-journal")
    sous.add_parser("sauvegarder")
    args = parser.parse_args(argv)

    db = UtilisateursSQLite(args.base)
    if args.commande == "desactiver-mfa":
        compte = _compte(db, args.email)
        db.desactiver_totp(compte["id"], acteur=ACTEUR)
        db.debloquer(cle_tentative("mfa", compte["id"]), acteur=ACTEUR)
        print("MFA désactivée. Réactivez-la depuis Admin → Sécurité après connexion.")
    elif args.commande == "debloquer":
        compte = _compte(db, args.email)
        db.debloquer(cle_tentative("email", args.email), acteur=ACTEUR)
        db.debloquer(cle_tentative("mfa", compte["id"]), acteur=ACTEUR)
        print("Blocage levé pour ce compte.")
    elif args.commande == "mot-de-passe":
        compte = _compte(db, args.email)
        nouveau = getpass.getpass("Nouveau mot de passe : ")
        if nouveau != getpass.getpass("Confirmation : "):
            sys.exit("Les deux saisies diffèrent.")
        ok, msg = db.changer_mot_de_passe(compte["id"], nouveau, acteur=ACTEUR)
        print(msg)
        return 0 if ok else 1
    elif args.commande == "verifier-journal":
        r = db.verifier_journal()
        if r["valide"]:
            print(f"Journal intègre : {r['total']} entrée(s), dont {r['non_chainees']} antérieure(s) au chaînage.")
        else:
            print(f"ANOMALIE : chaîne rompue à l'entrée #{r['premiere_anomalie']}.")
        db.audit(ACTEUR, "verification_securite",
                 "Journal intègre" if r["valide"] else f"Chaîne rompue (#{r['premiere_anomalie']})",
                 categorie=CATEGORIE_SECURITE, gravite="info" if r["valide"] else "critique")
        return 0 if r["valide"] else 2
    elif args.commande == "sauvegarder":
        horodatage = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        cible = args.base.parent / "sauvegardes" / horodatage
        cible.mkdir(parents=True, exist_ok=True)
        for base in sorted(args.base.parent.glob("*.db")):
            src, dst = sqlite3.connect(str(base)), sqlite3.connect(str(cible / base.name))
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
        db.audit(ACTEUR, "sauvegarde", f"Sauvegarde hors interface dans {cible.name}",
                 categorie=CATEGORIE_SECURITE)
        print(f"Bases copiées dans {cible}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
