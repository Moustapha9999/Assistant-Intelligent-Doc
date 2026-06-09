"""
Module de collecte de documentation GitHub
Collecte : README + fichiers .md du dossier /docs + wikis
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


class ScraperGitHub:
    def __init__(self, fichier_repos='data/raw/repos_selectionnes.yaml'):
        """Initialise le scraper"""
        self.github_token = os.getenv('GITHUB_TOKEN')
        if not self.github_token:
            raise ValueError("GITHUB_TOKEN non trouvé dans .env")

        auth = Auth.Token(self.github_token)
        self.github = Github(auth=auth)

        if not os.path.exists(fichier_repos):
            raise FileNotFoundError(f"Fichier introuvable : {fichier_repos}")

        with open(fichier_repos, 'r', encoding='utf-8') as f:
            self.repos = yaml.safe_load(f) or []

        print(f"✅ {len(self.repos)} repos à scraper")

    # ────────────────────────────────────────────────────────────────
    # COLLECTE README
    # ────────────────────────────────────────────────────────────────

    def _recuperer_readme(self, repo_gh):
        """Récupère le README principal"""
        try:
            readme = repo_gh.get_readme()
            return readme.decoded_content.decode('utf-8', errors='replace')
        except Exception:
            return None

    # ────────────────────────────────────────────────────────────────
    # COLLECTE FICHIERS .MD (docs/, wiki/, etc.)
    # ────────────────────────────────────────────────────────────────

    def _lister_fichiers_md(self, repo_gh, dossiers=None, profondeur_max=3):
        """
        Liste tous les fichiers .md dans les dossiers spécifiés.
        Par défaut : racine + docs/ + documentation/ + wiki/ + guide/ + tutorial/
        """
        if dossiers is None:
            dossiers = ['', 'docs', 'documentation', 'doc', 'wiki',
                        'guide', 'guides', 'tutorial', 'tutorials',
                        'examples', 'example', 'getting-started',
                        'reference', 'api', 'src/docs']

        fichiers_trouves = []

        for dossier in dossiers:
            try:
                contenu = repo_gh.get_contents(dossier)
                if not isinstance(contenu, list):
                    contenu = [contenu]

                for item in contenu:
                    if item.type == 'file' and item.name.lower().endswith('.md'):
                        fichiers_trouves.append(item)
                    elif item.type == 'dir' and profondeur_max > 1:
                        # Récursion limitée
                        try:
                            sous_contenu = repo_gh.get_contents(item.path)
                            if not isinstance(sous_contenu, list):
                                sous_contenu = [sous_contenu]
                            for sous_item in sous_contenu:
                                if sous_item.type == 'file' and sous_item.name.lower().endswith('.md'):
                                    fichiers_trouves.append(sous_item)
                        except Exception:
                            pass

            except GithubException:
                pass
            except Exception:
                pass

        return fichiers_trouves

    def _recuperer_contenu_fichier(self, fichier_gh):
        """Récupère le contenu d'un fichier GitHub"""
        try:
            if fichier_gh.encoding == 'base64':
                return base64.b64decode(fichier_gh.content).decode('utf-8', errors='replace')
            return fichier_gh.decoded_content.decode('utf-8', errors='replace')
        except Exception:
            return None

    # ────────────────────────────────────────────────────────────────
    # FORMATAGE AVEC MÉTADONNÉES
    # ────────────────────────────────────────────────────────────────

    def _formater_contenu(self, infos_repo, contenu, type_doc='readme', chemin_fichier=''):
        """Ajoute les métadonnées au contenu"""
        entete = f"""---
nom_complet: {infos_repo['nom_complet']}
langage: {infos_repo.get('langage', 'Unknown')}
etoiles: {infos_repo.get('etoiles', 0)}
url: {infos_repo.get('url', '')}
type_doc: {type_doc}
chemin_fichier: {chemin_fichier}
---

"""
        return entete + contenu

    # ────────────────────────────────────────────────────────────────
    # SCRAPING COMPLET D'UN REPO
    # ────────────────────────────────────────────────────────────────

    def scraper_repo(self, infos_repo, dossier_sortie):
        """Scrape toute la documentation d'un repo"""
        nom_complet  = infos_repo['nom_complet']
        nom_securise = nom_complet.replace('/', '_')
        docs_collectes = []

        try:
            repo_gh = self.github.get_repo(nom_complet)

            # 1. README principal
            contenu_readme = self._recuperer_readme(repo_gh)
            if contenu_readme:
                chemin = Path(dossier_sortie) / f"{nom_securise}_README.md"
                with open(chemin, 'w', encoding='utf-8') as f:
                    f.write(self._formater_contenu(
                        infos_repo, contenu_readme, 'readme', 'README.md'
                    ))
                docs_collectes.append('README')

            # 2. Fichiers .md dans /docs et autres dossiers
            fichiers_md = self._lister_fichiers_md(repo_gh)

            for fichier in fichiers_md[:30]:  # max 30 fichiers par repo
                # Éviter de re-scraper le README
                if fichier.name.upper() in ['README.MD', 'README.MD']:
                    continue

                contenu = self._recuperer_contenu_fichier(fichier)
                if not contenu or len(contenu.strip()) < 100:
                    continue

                # Nom de fichier sécurisé
                chemin_relatif = fichier.path.replace('/', '_').replace(' ', '-')
                nom_fichier    = f"{nom_securise}_{chemin_relatif}"
                chemin_sortie_fichier = Path(dossier_sortie) / nom_fichier

                with open(chemin_sortie_fichier, 'w', encoding='utf-8') as f:
                    f.write(self._formater_contenu(
                        infos_repo, contenu, 'documentation', fichier.path
                    ))
                docs_collectes.append(fichier.path)
                time.sleep(0.1)  # Rate limiting

            return docs_collectes

        except GithubException as e:
            print(f"   ❌ GitHub error {nom_complet}: {e.status}")
            return []
        except Exception as e:
            print(f"   ❌ Erreur {nom_complet}: {e}")
            return []

    # ────────────────────────────────────────────────────────────────
    # PIPELINE PRINCIPAL
    # ────────────────────────────────────────────────────────────────

    def scraper_tous(self, dossier_sortie='data/raw/readmes'):
        """Scrape toute la documentation de tous les repos"""
        os.makedirs(dossier_sortie, exist_ok=True)

        print("=" * 60)
        print("📥 SCRAPING DE LA DOCUMENTATION")
        print("=" * 60)

        stats = {
            'total'          : len(self.repos),
            'succes'         : 0,
            'echecs'         : 0,
            'docs_collectes' : 0,
        }

        for infos_repo in tqdm(self.repos, desc="📥 Scraping"):
            if 'nom_complet' not in infos_repo:
                continue

            nom = infos_repo['nom_complet']
            docs = self.scraper_repo(infos_repo, dossier_sortie)

            if docs:
                stats['succes']         += 1
                stats['docs_collectes'] += len(docs)
            else:
                stats['echecs'] += 1

            time.sleep(0.3)  # Rate limiting global

        # Récapitulatif
        print(f"\n{'=' * 60}")
        print(f"✅ Scraping terminé !")
        print(f"   Repos avec succès : {stats['succes']}/{stats['total']}")
        print(f"   Repos en échec    : {stats['echecs']}")
        print(f"   Documents totaux  : {stats['docs_collectes']}")
        print(f"   Dossier de sortie : {dossier_sortie}/")
        print(f"{'=' * 60}")

        self._sauvegarder_recap(dossier_sortie, stats)
        return stats

    def _sauvegarder_recap(self, dossier_sortie, stats):
        """Sauvegarde le récapitulatif du scraping"""
        recap = {
            **stats,
            'date_scraping': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        chemin = Path(dossier_sortie) / '_recap_scraping.yaml'
        with open(chemin, 'w', encoding='utf-8') as f:
            yaml.dump(recap, f, allow_unicode=True)
        print(f"💾 Récapitulatif : {chemin}")


if __name__ == "__main__":
    scraper = ScraperGitHub()
    scraper.scraper_tous()