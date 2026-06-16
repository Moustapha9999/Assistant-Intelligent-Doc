"""
Scraper GitHub enrichi
Collecte : README + docs + code source (.py, .js, .ts, .java, .go, .rs, .cpp, .sql, .ipynb)
ISI KOMUNIK · Master IAGE
"""

import os
import yaml
import time
import base64
from pathlib import Path
from github import Github, Auth, GithubException
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

# ── Extensions à collecter ───────────────────────────────────────
EXTENSIONS_CODE = {
    '.py', '.js', '.ts', '.java', '.go', '.rs',
    '.cpp', '.c', '.h', '.sql', '.ipynb',
}
EXTENSIONS_DOC = {
    '.md', '.rst', '.txt',
}
EXTENSIONS_CONFIG = {
    '.yaml', '.yml', '.json', '.toml',
}
TOUTES_EXTENSIONS = EXTENSIONS_CODE | EXTENSIONS_DOC | EXTENSIONS_CONFIG

# ── Dossiers à ignorer ───────────────────────────────────────────
DOSSIERS_EXCLUS = {
    'node_modules', 'dist', 'build', 'target', '.git',
    '__pycache__', '.venv', 'venv', 'env', '.env',
    'vendor', 'bower_components', 'coverage', '.nyc_output',
    'eggs', '.eggs', 'htmlcov', '.tox', '.pytest_cache',
}

# ── Limites ───────────────────────────────────────────────────────
MAX_FICHIERS_PAR_REPO  = 50   # max fichiers code par repo
MAX_TAILLE_FICHIER     = 100_000  # 100 KB max par fichier
MAX_PROFONDEUR         = 4    # profondeur max de récursion


class ScraperGitHub:

    def __init__(self, fichier_repos='data/raw/repos_selectionnes.yaml'):
        token = os.getenv('GITHUB_TOKEN')
        if not token:
            raise ValueError("GITHUB_TOKEN manquant dans .env")

        self.github = Github(auth=Auth.Token(token))

        if not os.path.exists(fichier_repos):
            raise FileNotFoundError(f"Introuvable : {fichier_repos}")

        with open(fichier_repos, 'r', encoding='utf-8') as f:
            self.repos = yaml.safe_load(f) or []

        print(f"✅ {len(self.repos)} repos à scraper")

    # ────────────────────────────────────────────────────────────
    # UTILITAIRES
    # ────────────────────────────────────────────────────────────

    def _dossier_exclu(self, chemin: str) -> bool:
        parts = Path(chemin).parts
        return any(p in DOSSIERS_EXCLUS for p in parts)

    def _extension_valide(self, nom: str) -> bool:
        return Path(nom).suffix.lower() in TOUTES_EXTENSIONS

    def _decoder_contenu(self, fichier_gh) -> str:
        try:
            if fichier_gh.size > MAX_TAILLE_FICHIER:
                return None
            raw = base64.b64decode(fichier_gh.content)
            try:
                return raw.decode('utf-8')
            except UnicodeDecodeError:
                return raw.decode('latin-1', errors='replace')
        except Exception:
            return None

    def _entete(self, infos_repo: dict, chemin: str, type_doc: str) -> str:
        return (
            f"---\n"
            f"nom_complet: {infos_repo['nom_complet']}\n"
            f"langage: {infos_repo.get('langage', 'Unknown')}\n"
            f"etoiles: {infos_repo.get('etoiles', 0)}\n"
            f"url: {infos_repo.get('url', '')}\n"
            f"type_doc: {type_doc}\n"
            f"chemin_fichier: {chemin}\n"
            f"---\n\n"
        )

    # ────────────────────────────────────────────────────────────
    # COLLECTE README
    # ────────────────────────────────────────────────────────────

    def _collecter_readme(self, repo_gh) -> str:
        try:
            readme = repo_gh.get_readme()
            return base64.b64decode(readme.content).decode('utf-8', errors='replace')
        except Exception:
            return None

    # ────────────────────────────────────────────────────────────
    # COLLECTE FICHIERS CODE (récursif)
    # ────────────────────────────────────────────────────────────

    def _lister_fichiers(self, repo_gh, chemin='', profondeur=0) -> list:
        """Liste récursivement les fichiers pertinents"""
        if profondeur > MAX_PROFONDEUR:
            return []

        fichiers = []
        try:
            items = repo_gh.get_contents(chemin)
            if not isinstance(items, list):
                items = [items]

            for item in items:
                if self._dossier_exclu(item.path):
                    continue

                if item.type == 'file':
                    if self._extension_valide(item.name):
                        fichiers.append(item)

                elif item.type == 'dir':
                    sous = self._lister_fichiers(repo_gh, item.path, profondeur + 1)
                    fichiers.extend(sous)

                # Limiter pour éviter les timeouts
                if len(fichiers) >= MAX_FICHIERS_PAR_REPO * 2:
                    break

        except GithubException:
            pass
        except Exception:
            pass

        return fichiers

    # ────────────────────────────────────────────────────────────
    # SCRAPING D'UN REPO
    # ────────────────────────────────────────────────────────────

    def scraper_repo(self, infos_repo: dict, dossier_sortie: str) -> dict:
        """Scrape README + code source d'un repo"""
        nom_complet  = infos_repo['nom_complet']
        nom_securise = nom_complet.replace('/', '_')
        stats = {'readme': 0, 'code': 0, 'doc': 0, 'erreurs': 0}

        try:
            repo_gh = self.github.get_repo(nom_complet)

            # 1. README
            readme = self._collecter_readme(repo_gh)
            if readme:
                chemin_out = Path(dossier_sortie) / f"{nom_securise}_README.md"
                with open(chemin_out, 'w', encoding='utf-8') as f:
                    f.write(self._entete(infos_repo, 'README.md', 'readme'))
                    f.write(readme)
                stats['readme'] += 1

            # 2. Fichiers code & docs
            fichiers = self._lister_fichiers(repo_gh)

            # Trier par priorité : code d'abord, puis doc
            def priorite(f):
                ext = Path(f.name).suffix.lower()
                if ext in EXTENSIONS_CODE: return 0
                if ext in EXTENSIONS_DOC:  return 1
                return 2

            fichiers.sort(key=priorite)
            fichiers = fichiers[:MAX_FICHIERS_PAR_REPO]

            for fichier in fichiers:
                # Skip README (déjà collecté)
                if fichier.name.upper().startswith('README'):
                    continue

                contenu = self._decoder_contenu(fichier)
                if not contenu or len(contenu.strip()) < 50:
                    continue

                ext      = Path(fichier.name).suffix.lower()
                type_doc = 'code' if ext in EXTENSIONS_CODE else 'documentation'

                # Nom de fichier sécurisé
                chemin_rel  = fichier.path.replace('/', '_').replace(' ', '-')
                nom_fichier = f"{nom_securise}_{chemin_rel}"
                chemin_out  = Path(dossier_sortie) / nom_fichier

                with open(chemin_out, 'w', encoding='utf-8') as f:
                    f.write(self._entete(infos_repo, fichier.path, type_doc))
                    f.write(contenu)

                if ext in EXTENSIONS_CODE:
                    stats['code'] += 1
                else:
                    stats['doc'] += 1

                time.sleep(0.05)  # Rate limiting léger

        except GithubException as e:
            print(f"   ❌ {nom_complet}: {e.status}")
            stats['erreurs'] += 1
        except Exception as e:
            print(f"   ❌ {nom_complet}: {e}")
            stats['erreurs'] += 1

        return stats

    # ────────────────────────────────────────────────────────────
    # PIPELINE PRINCIPAL
    # ────────────────────────────────────────────────────────────

    def scraper_tous(self, dossier_sortie='data/raw/readmes'):
        os.makedirs(dossier_sortie, exist_ok=True)

        print("=" * 60)
        print("📥 SCRAPING — README + CODE SOURCE")
        print("=" * 60)

        total_stats = {
            'repos_ok': 0, 'repos_ko': 0,
            'readme': 0, 'code': 0, 'doc': 0,
        }

        for infos in tqdm(self.repos, desc="📥 Scraping"):
            if 'nom_complet' not in infos:
                continue

            stats = self.scraper_repo(infos, dossier_sortie)

            if stats['erreurs'] == 0:
                total_stats['repos_ok'] += 1
            else:
                total_stats['repos_ko'] += 1

            total_stats['readme'] += stats['readme']
            total_stats['code']   += stats['code']
            total_stats['doc']    += stats['doc']

            time.sleep(0.3)

        total_docs = total_stats['readme'] + total_stats['code'] + total_stats['doc']

        print(f"\n{'=' * 60}")
        print(f"✅ Scraping terminé !")
        print(f"   Repos OK    : {total_stats['repos_ok']}/{len(self.repos)}")
        print(f"   Repos KO    : {total_stats['repos_ko']}")
        print(f"   README      : {total_stats['readme']}")
        print(f"   Code source : {total_stats['code']}")
        print(f"   Docs        : {total_stats['doc']}")
        print(f"   TOTAL docs  : {total_docs}")
        print(f"   Dossier     : {dossier_sortie}/")
        print(f"{'=' * 60}")

        # Récapitulatif
        recap = {**total_stats, 'total_docs': total_docs,
                 'date': time.strftime('%Y-%m-%d %H:%M:%S')}
        with open(Path(dossier_sortie) / '_recap_scraping.yaml', 'w') as f:
            yaml.dump(recap, f)

        return total_stats


if __name__ == "__main__":
    scraper = ScraperGitHub()
    scraper.scraper_tous()