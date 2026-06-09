"""
Module de sélection des repositories GitHub
Supporte les repos forcés ET la recherche automatique par critères
"""

import os
import sys
import yaml
from pathlib import Path
from datetime import datetime, timedelta
from github import Github, Auth, GithubException
from dotenv import load_dotenv

# Rendre le projet importable (src/ sur le path) quel que soit le CWD
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config as cfg

load_dotenv()


class SelecteurRepo:
    def __init__(self, chemin_config=cfg.REPOS_CONFIG_FILE):
        """Initialise le sélecteur avec la config"""
        self.github_token = os.getenv('GITHUB_TOKEN')
        if not self.github_token:
            raise ValueError("GITHUB_TOKEN non trouvé dans .env")

        auth = Auth.Token(self.github_token)
        self.github = Github(auth=auth)

        if not os.path.exists(chemin_config):
            raise FileNotFoundError(f"Config introuvable : {chemin_config}")

        with open(chemin_config, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        self.criteres       = self.config.get('criteres_selection', {})
        self.repos_forces   = self.config.get('repos_forces', [])
        self.repos_exclus   = self.config.get('repos_exclus', [])
        self.repos_selectionnes = []

        print(f"✅ Config chargée — {len(self.repos_forces)} repos forcés")

    # ────────────────────────────────────────────────────────────────
    # REPOS FORCÉS (liste explicite dans le YAML)
    # ────────────────────────────────────────────────────────────────

    def _charger_repos_forces(self):
        """Charge directement les repos listés dans repos_forces"""
        resultats = []
        total = len(self.repos_forces)

        print(f"\n📌 Chargement de {total} repos forcés...")

        for i, nom_complet in enumerate(self.repos_forces, 1):
            # Ignorer les repos exclus
            if nom_complet in self.repos_exclus:
                print(f"   ⏭  [{i}/{total}] {nom_complet} — exclu")
                continue

            try:
                repo = self.github.get_repo(nom_complet)

                infos = {
                    'rang_dans_recherche' : i,
                    'nom_complet'         : repo.full_name,
                    'nom'                 : repo.name,
                    'proprietaire'        : repo.owner.login,
                    'langage'             : repo.language or 'Unknown',
                    'etoiles'             : repo.stargazers_count,
                    'url'                 : repo.html_url,
                    'url_clone'           : repo.clone_url,
                    'description'         : repo.description or '',
                    'topics'              : repo.get_topics(),
                    'mis_a_jour_le'       : repo.updated_at.isoformat(),
                    'source'              : 'force',
                }

                resultats.append(infos)
                print(f"   ✅ [{i}/{total}] {repo.full_name} ({repo.stargazers_count:,} ⭐)")

            except GithubException as e:
                print(f"   ❌ [{i}/{total}] {nom_complet} — {e.status}: {e.data.get('message','')}")
            except Exception as e:
                print(f"   ❌ [{i}/{total}] {nom_complet} — {e}")

        print(f"\n   → {len(resultats)} repos forcés chargés")
        return resultats

    # ────────────────────────────────────────────────────────────────
    # RECHERCHE AUTOMATIQUE PAR LANGAGE
    # ────────────────────────────────────────────────────────────────

    def chercher_repos_par_langage(self, langage):
        """Recherche les meilleurs repos pour un langage donné"""
        print(f"\n🔍 Recherche repos {langage}...")

        min_stars     = self.criteres.get('min_stars', 250)
        max_age_mois  = self.criteres.get('max_age_mois', 24)
        date_limite   = datetime.now() - timedelta(days=max_age_mois * 30)
        date_str      = date_limite.strftime('%Y-%m-%d')

        requete = f"language:{langage} stars:>={min_stars} pushed:>={date_str}"

        if self.criteres.get('exclure_forks', True):
            requete += " fork:false"
        if self.criteres.get('exclure_archives', True):
            requete += " archived:false"

        return self.github.search_repositories(query=requete, sort='stars', order='desc')

    def filtrer_repo(self, repo):
        """Vérifie si un repo respecte les critères"""
        # Vérifier README
        if self.criteres.get('doit_avoir_readme', True):
            try:
                repo.get_readme()
            except Exception:
                return False

        # Vérifier topics exclus
        mots_exclus = ['awesome', 'awesome-list', 'documentation-only']
        topics      = [t.lower() for t in repo.get_topics()]
        if any(mot in ' '.join(topics) for mot in mots_exclus):
            return False

        # Vérifier exclusions explicites
        if repo.full_name in self.repos_exclus:
            return False

        return True

    def chercher_repos_auto(self):
        """Recherche automatique par langage selon les critères"""
        langages        = self.criteres.get('langages', [])
        max_par_langage = self.criteres.get('max_repos_par_langage', 10)
        resultats       = []

        # Noms déjà chargés (éviter les doublons avec repos forcés)
        noms_existants = {r['nom_complet'] for r in self.repos_selectionnes}

        for langage in langages:
            recherche = self.chercher_repos_par_langage(langage)
            compteur  = 0

            for pos, repo in enumerate(recherche, 1):
                if compteur >= max_par_langage:
                    break
                if repo.full_name in noms_existants:
                    continue
                if not self.filtrer_repo(repo):
                    continue

                infos = {
                    'rang_dans_recherche' : pos,
                    'nom_complet'         : repo.full_name,
                    'nom'                 : repo.name,
                    'proprietaire'        : repo.owner.login,
                    'langage'             : langage,
                    'etoiles'             : repo.stargazers_count,
                    'url'                 : repo.html_url,
                    'url_clone'           : repo.clone_url,
                    'description'         : repo.description or '',
                    'topics'              : repo.get_topics(),
                    'mis_a_jour_le'       : repo.updated_at.isoformat(),
                    'source'              : 'auto',
                }

                resultats.append(infos)
                noms_existants.add(repo.full_name)
                compteur += 1
                print(f"   [{pos}] {repo.full_name} ({repo.stargazers_count:,} ⭐)")

        print(f"\n   → {len(resultats)} repos auto trouvés")
        return resultats

    # ────────────────────────────────────────────────────────────────
    # PIPELINE PRINCIPAL
    # ────────────────────────────────────────────────────────────────

    def selectionner_repos(self):
        """Pipeline complet : forcés + auto"""
        print("=" * 60)
        print("📦 SÉLECTION DES REPOSITORIES")
        print("=" * 60)

        # 1. Repos forcés
        forces = self._charger_repos_forces()
        self.repos_selectionnes = forces

        # 2. Repos auto (complément)
        print("\n🔄 Recherche automatique complémentaire...")
        auto = self.chercher_repos_auto()
        self.repos_selectionnes.extend(auto)

        # 3. Déduplication finale
        vus = set()
        uniques = []
        for r in self.repos_selectionnes:
            if r['nom_complet'] not in vus:
                vus.add(r['nom_complet'])
                uniques.append(r)

        self.repos_selectionnes = uniques

        print(f"\n{'=' * 60}")
        print(f"✅ TOTAL : {len(self.repos_selectionnes)} repos sélectionnés")
        print(f"   Forcés : {len(forces)}")
        print(f"   Auto   : {len(auto)}")
        print(f"{'=' * 60}")

        return self.repos_selectionnes

    # ────────────────────────────────────────────────────────────────
    # SAUVEGARDE
    # ────────────────────────────────────────────────────────────────

    def sauvegarder_liste(self, chemin_sortie=cfg.REPOS_SELECTIONNES_FILE):
        """Sauvegarde la liste dans un fichier YAML"""
        os.makedirs(os.path.dirname(chemin_sortie), exist_ok=True)

        with open(chemin_sortie, 'w', encoding='utf-8') as f:
            yaml.dump(
                self.repos_selectionnes, f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False
            )

        print(f"\n💾 Liste sauvegardée : {chemin_sortie}")
        print(f"   {len(self.repos_selectionnes)} repos enregistrés")


if __name__ == "__main__":
    selecteur = SelecteurRepo()
    resultats = selecteur.selectionner_repos()
    selecteur.sauvegarder_liste()