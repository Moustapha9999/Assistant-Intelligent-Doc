"""

Module de sélection des meilleurs repositories GitHub

selon les critères définis dans configs/repos_github.yaml

"""



import os
import yaml
from datetime import datetime, timedelta
from github import Github, Auth
from dotenv import load_dotenv



# Charger les variables d'environnement

load_dotenv()


class SelecteurRepo:
    def __init__(self, chemin_config='configs/repos_github.yaml'):

        """Initialise le sélecteur avec la config"""

        self.github_token = os.getenv('GITHUB_TOKEN')
        if not self.github_token:
            raise ValueError("GITHUB_TOKEN non trouvé dans le fichier .env")


        # Correction de la dépréciation : Utilisation de github.Auth

        auth = Auth.Token(self.github_token)
        self.github = Github(auth=auth)

        
        # Charger la configuration

        if not os.path.exists(chemin_config):
            raise FileNotFoundError(f"Le fichier de configuration {chemin_config} est introuvable.")

            

        with open(chemin_config, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        self.criteres = self.config['criteres_selection']
        self.repos_selectionnes = []

    

    def chercher_repos_par_langage(self, langage):
        """Recherche les meilleurs repos pour un langage donné"""
        print(f"\n🔍 Recherche des repos {langage}...")


        # Construire la requête de recherche
        min_stars = self.criteres['min_stars']

        # Calcul de la date limite
        date_limite = datetime.now() - timedelta(days=self.criteres['max_age_mois'] * 30)  
        date_limite_str = date_limite.strftime('%Y-%m-%d')
        requete = f"language:{langage} stars:>={min_stars} pushed:>={date_limite_str}"


        # Synchronisation avec les clés du YAML (exclure_forks / exclure_archives)

        if self.criteres.get('exclure_forks', False):
            requete += " fork:false"
        if self.criteres.get('exclure_archives', False):
            requete += " archived:false"


        # Recherche via l'API

        resultats = self.github.search_repositories(
            query=requete,
            sort='stars',
            order='desc'

        )
        return resultats

    
    def filtrer_repo(self, repo):
        """Vérifie si un repo respecte tous les critères"""
        # Vérifier README (Clé YAML: doit_avoir_readme)

        if self.criteres.get('doit_avoir_readme', True):
            try:
                repo.get_readme()
            except:
                return False

        

        # Vérifier topics exclus

        mots_exclus = ['awesome', 'awesome-list', 'documentation']
        topics_du_repo = [topic.lower() for topic in repo.get_topics()]

        

        if any(mot in ' '.join(topics_du_repo) for mot in mots_exclus):
            return False

        return True


    def selectionner_repos(self):
        """Sélectionne les meilleurs repos selon la config"""
        
        langages = self.criteres['langages']
        max_par_langage = self.criteres['max_repos_par_langage']


        all_selection = []

        for langage in langages:
            resultats = self.chercher_repos_par_langage(langage)

            
            compteur_selection = 0

            for position, repo in enumerate(resultats, start=1):
                if compteur_selection >= max_par_langage:
                    break


                # Filtrage manuel

                if self.filtrer_repo(repo):
                    infos_repo = {

                        'rang_dans_recherche': position,
                        'nom_complet': repo.full_name,
                        'nom': repo.name,
                        'proprietaire': repo.owner.login,
                        'langage': langage,
                        'etoiles': repo.stargazers_count,
                        'url': repo.html_url,
                        'url_clone': repo.clone_url,
                        'description': repo.description,
                        'topics': repo.get_topics(),
                        'mis_a_jour_le': repo.updated_at.isoformat()

                    }


                    all_selection.append(infos_repo)
                    compteur_selection += 1
                    print(f"   [{position}] {repo.full_name} ({repo.stargazers_count} ⭐)")

        

        self.repos_selectionnes = all_selection
        print(f"\n--> Total des repos sélectionnés : {len(all_selection)} repos")
        return all_selection

    

    def sauvegarder_liste(self, chemin_sortie='data/raw/repos_selectionnes.yaml'):
        """Sauvegarde la liste dans un fichier YAML"""

        os.makedirs(os.path.dirname(chemin_sortie), exist_ok=True)

        with open(chemin_sortie, 'w', encoding='utf-8') as f:
         yaml.dump(self.repos_selectionnes, f, allow_unicode=True, default_flow_style=False)

        
        print(f"\n Liste des repos sauvegardée dans : {chemin_sortie}")





if __name__ == "__main__":

    # Test du module
    selecteur = SelecteurRepo()
    resultats = selecteur.selectionner_repos()
    selecteur.sauvegarder_liste()