"""
Migration « isolation des utilisateurs » des bases SQLite de l'interface.

- ajoute `owner_id` aux conversations, feedbacks, collections et favoris ;
- ajoute les tables `sessions` et `oauth_etats` à la base des utilisateurs ;
- sauvegarde chaque base modifiée (`*.avant_isolation_<horodatage>.bak`) avant migration ;
- ne supprime aucune donnée : les lignes sans propriétaire restent en base, en quarantaine
  (jamais renvoyées à un utilisateur) ;
- idempotente : une base déjà migrée n'est ni modifiée ni sauvegardée une seconde fois.

Usage :
  python scripts/migrer_isolation_sqlite.py --dry-run     # simulation sur une copie temporaire
  python scripts/migrer_isolation_sqlite.py               # migration réelle
  python scripts/migrer_isolation_sqlite.py --dossier data/app_copie
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import config  # noqa: E402
from app.favoris_sqlite import FavorisSQLite  # noqa: E402
from app.historique_sqlite import HistoriqueSQLite  # noqa: E402
from app.utilisateurs_sqlite import UtilisateursSQLite  # noqa: E402


def _compter(chemin: Path, requete: str) -> int:
    if not chemin.exists():
        return 0
    conn = sqlite3.connect(chemin)
    try:
        return int(conn.execute(requete).fetchone()[0])
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def _a_colonne(chemin: Path, table: str, colonne: str) -> bool:
    if not chemin.exists():
        return False
    conn = sqlite3.connect(chemin)
    try:
        return colonne in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def migrer(dossier: Path) -> dict:
    histo_db = dossier / Path(config.HISTORIQUE_DB).name
    favoris_db = dossier / "favoris.db"
    users_db = dossier / "utilisateurs.db"

    avant = {
        "historique_migre": _a_colonne(histo_db, "conversations", "owner_id"),
        "favoris_migre": _a_colonne(favoris_db, "collections", "owner_id"),
        "conversations": _compter(histo_db, "SELECT COUNT(*) FROM conversations"),
        "messages": _compter(histo_db, "SELECT COUNT(*) FROM messages"),
        "feedbacks": _compter(histo_db, "SELECT COUNT(*) FROM feedback"),
        "collections": _compter(favoris_db, "SELECT COUNT(*) FROM collections"),
        "favoris": _compter(favoris_db, "SELECT COUNT(*) FROM favoris"),
        "utilisateurs": _compter(users_db, "SELECT COUNT(*) FROM users"),
    }

    histo = HistoriqueSQLite(histo_db)
    favoris = FavorisSQLite(favoris_db)
    UtilisateursSQLite(users_db)

    apres = {
        "conversations": _compter(histo_db, "SELECT COUNT(*) FROM conversations"),
        "messages": _compter(histo_db, "SELECT COUNT(*) FROM messages"),
        "feedbacks": _compter(histo_db, "SELECT COUNT(*) FROM feedback"),
        "collections": _compter(favoris_db, "SELECT COUNT(*) FROM collections"),
        "favoris": _compter(favoris_db, "SELECT COUNT(*) FROM favoris"),
        "utilisateurs": _compter(users_db, "SELECT COUNT(*) FROM users"),
        "sessions": _compter(users_db, "SELECT COUNT(*) FROM sessions"),
    }
    quarantaine = {
        "conversations": _compter(histo_db, "SELECT COUNT(*) FROM conversations WHERE owner_id IS NULL"),
        "messages": _compter(
            histo_db,
            "SELECT COUNT(*) FROM messages m JOIN conversations c ON c.id = m.conversation_id "
            "WHERE c.owner_id IS NULL",
        ),
        "feedbacks (visibles admin uniquement)": _compter(
            histo_db, "SELECT COUNT(*) FROM feedback WHERE owner_id IS NULL"
        ),
        "collections": _compter(favoris_db, "SELECT COUNT(*) FROM collections WHERE owner_id IS NULL"),
        "favoris": _compter(favoris_db, "SELECT COUNT(*) FROM favoris WHERE owner_id IS NULL"),
        "préférences 'default' (mémoire long terme)": _compter(
            histo_db, "SELECT COUNT(*) FROM preferences_utilisateur WHERE user_id = 'default'"
        ),
    }
    return {
        "avant": avant,
        "apres": apres,
        "quarantaine": quarantaine,
        "sauvegardes": [str(p) for p in (histo.sauvegarde_migration, favoris.sauvegarde_migration) if p],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dossier", type=Path, default=Path(config.DB_DIR))
    parser.add_argument("--dry-run", action="store_true", help="Migrer une copie temporaire, sans toucher aux bases")
    args = parser.parse_args()

    source = args.dossier.resolve()
    if args.dry_run:
        tmp = Path(tempfile.mkdtemp(prefix="isolation_dry_"))
        for f in source.glob("*.db"):
            shutil.copy2(f, tmp / f.name)
        cible = tmp
        print(f"Simulation sur une copie : {cible}")
    else:
        cible = source
        print(f"Migration réelle : {cible}")

    rapport = migrer(cible)
    for section in ("avant", "apres", "quarantaine"):
        print(f"\n[{section}]")
        for k, v in rapport[section].items():
            print(f"  {k:45s} {v}")
    pertes = [
        k for k in ("conversations", "messages", "feedbacks", "collections", "favoris", "utilisateurs")
        if rapport["apres"][k] < rapport["avant"][k]
    ]
    print("\nSauvegardes :", ", ".join(rapport["sauvegardes"]) or "aucune (déjà migré ou base absente)")
    print("Perte de données :", ", ".join(pertes) if pertes else "aucune")
    if args.dry_run:
        shutil.rmtree(cible, ignore_errors=True)
    return 1 if pertes else 0


if __name__ == "__main__":
    raise SystemExit(main())
