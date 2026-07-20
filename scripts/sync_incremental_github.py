"""Planifie ou lance un scraping GitHub incrémental.

Par défaut, le script est non destructif : il affiche les dépôts sélectionnés.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import config


def charger_repos() -> list[dict]:
    chemin = config.REPOS_SELECTIONNES_FILE
    if not chemin.exists():
        print(f"Aucun fichier de sélection : {chemin}")
        return []
    data = yaml.safe_load(chemin.read_text(encoding="utf-8")) or []
    return data if isinstance(data, list) else []


def est_recent(repo: dict, depuis: datetime | None) -> bool:
    if depuis is None:
        return True
    valeur = repo.get("mis_a_jour_le")
    if not valeur:
        return True  # état inconnu : le garder dans le plan
    try:
        date = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
        return date >= depuis
    except ValueError:
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Synchronisation GitHub incrémentale")
    parser.add_argument("--since", help="Date ISO, par ex. 2026-01-01")
    parser.add_argument("--run", action="store_true", help="Exécute le scraper pour les dépôts planifiés")
    args = parser.parse_args()
    depuis = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc) if args.since else None
    repos = [r for r in charger_repos() if est_recent(r, depuis)]
    print(f"Plan : {len(repos)} dépôt(s) à synchroniser" + (f" depuis {args.since}" if args.since else ""))
    for repo in repos:
        print(f"- {repo.get('nom_complet', '?')} (mis à jour : {repo.get('mis_a_jour_le', 'inconnu')})")
    if not args.run or not repos:
        return

    # Le scraper existant lit le fichier de sélection ; l'exécution reste explicite.
    from data_collection.scraper_github import ScraperGitHub
    scraper = ScraperGitHub(str(config.REPOS_SELECTIONNES_FILE))
    scraper.repos = repos
    scraper.scraper_tous(str(config.READMES_RAW_DIR))


if __name__ == "__main__":
    main()
