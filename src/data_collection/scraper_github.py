"""
Module de récupération des README depuis GitHub
"""

import os
import yaml
import time
from pathlib import Path
from github import Github, Auth
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

class ScraperGitHub:
    def __init__(self, fichier_repos='data/raw/repos_selectionnes.yaml'):
        """Initialise le scraper"""
        self.github_token = os.getenv('GITHUB_TOKEN')
        if not self.github_token:
            raise ValueError("GITHUB_TOKEN non trouvé dans .env")
        
        # Utiliser Auth.Token pour éviter la dépréciation
        auth = Auth.Token(self.github_token)
        self.github = Github(auth=auth)
        
        # Charger la liste des repos
        if not os.path.exists(fichier_repos):
            raise FileNotFoundError(f"Le fichier {fichier_repos} est introuvable.")
        
        with open(fichier_repos, 'r', encoding='utf-8') as f:
            self.repos = yaml.safe_load(f)
        
        print(f" {len(self.repos)} repos à scraper")
    
    def recuperer_contenu_readme(self, nom_complet):
        """Récupère le contenu du README d'un repo"""
        try:
            repo = self.github.get_repo(nom_complet)
            readme = repo.get_readme()
            contenu = readme.decoded_content.decode('utf-8')
            return contenu
        except Exception as e:
            print(f"   Erreur {nom_complet}: {str(e)}")
            return None
    
    def scraper_tous(self, dossier_sortie='data/raw/readmes'):
        """Scrape tous les README"""
        os.makedirs(dossier_sortie, exist_ok=True)
        
        compteur_succes = 0
        compteur_echecs = 0
        
        for infos_repo in tqdm(self.repos, desc="📥 Scraping README"):
            if 'nom_complet' not in infos_repo:
                continue
            
            nom_complet = infos_repo['nom_complet']
            
            # Récupérer le README
            contenu = self.recuperer_contenu_readme(nom_complet)
            
            if contenu:
                # Sauvegarder dans un fichier
                nom_securise = nom_complet.replace('/', '_')
                chemin_sortie = Path(dossier_sortie) / f"{nom_securise}.md"
                
                # Ajouter métadonnées en haut du fichier
                metadonnees = f"""---
nom_complet: {infos_repo['nom_complet']}
langage: {infos_repo['langage']}
etoiles: {infos_repo['etoiles']}
url: {infos_repo['url']}
---

"""
                
                with open(chemin_sortie, 'w', encoding='utf-8') as f:
                    f.write(metadonnees + contenu)
                
                compteur_succes += 1
            else:
                compteur_echecs += 1
            
            # Rate limiting (éviter de dépasser les limites GitHub)
            time.sleep(0.2)
        
        print(f"\n Succès: {compteur_succes}")
        print(f" Échecs: {compteur_echecs}")
        print(f" README sauvegardés dans {dossier_sortie}/")
        
        # Sauvegarder un fichier récapitulatif
        self.sauvegarder_recapitulatif(dossier_sortie, compteur_succes, compteur_echecs)
    
    def sauvegarder_recapitulatif(self, dossier_sortie, succes, echecs):
        """Sauvegarde un fichier récapitulatif"""
        recap = {
            'total_repos': len(self.repos),
            'scraped_success': succes,
            'scraped_failed': echecs,
            'date_scraping': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        chemin_recap = Path(dossier_sortie) / '_recap_scraping.yaml'
        with open(chemin_recap, 'w', encoding='utf-8') as f:
            yaml.dump(recap, f, allow_unicode=True)
        
        print(f" Récapitulatif sauvegardé: {chemin_recap}")


if __name__ == "__main__":
    scraper = ScraperGitHub()
    scraper.scraper_tous()