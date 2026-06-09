"""
Module de nettoyage des README
"""

import re
import os
import sys
from pathlib import Path
from tqdm import tqdm

# Rendre le projet importable (src/ sur le path) quel que soit le CWD
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config


class NettoyeurReadme:
    def __init__(self):
        """Initialise le nettoyeur"""

        self.patterns_a_supprimer = [
            # Badges (shields.io, travis-ci, etc.)
            r'\[!\[.*?\]\(.*?\)\]\(.*?\)',
            r'!\[.*?\]\(https://img\.shields\.io/.*?\)',
            r'!\[.*?\]\(https://travis-ci\..*?\)',
            r'!\[.*?\]\(https://badge\..*?\)',
            
            # Liens images cassés
            r'!\[.*?\]\(broken.*?\)',
            
            # HTML comments
            r'<!--.*?-->',
            
            # Lignes vides multiples
            r'\n\n\n+',
        ]
    
    def nettoyer_contenu(self, contenu):
        """Nettoie le contenu d'un README"""
        
        # Séparer métadonnées et contenu
        if contenu.startswith('---'):
            parties = contenu.split('---', 2)
            if len(parties) >= 3:
                metadonnees = f"---{parties[1]}---\n"
                texte = parties[2]
            else:
                metadonnees = ""
                texte = contenu
        else:
            metadonnees = ""
            texte = contenu
        
        # Appliquer les patterns de nettoyage
        for pattern in self.patterns_a_supprimer:
            texte = re.sub(pattern, '', texte, flags=re.DOTALL)
        
        # Normaliser les espaces
        texte = re.sub(r' +', ' ', texte)  # Espaces multiples
        texte = re.sub(r'\n\n+', '\n\n', texte)  # Sauts de ligne multiples
        
        # Enlever espaces en début/fin
        texte = texte.strip()
        
        return metadonnees + texte
    
    def nettoyer_tous(self, dossier_entree=config.READMES_RAW_DIR,
                      dossier_sortie=config.READMES_NETTOYES_DIR):
        """Nettoie tous les README"""
        
        os.makedirs(dossier_sortie, exist_ok=True)
        
        fichiers = list(Path(dossier_entree).glob('*.md'))
        
        # Exclure le fichier récapitulatif
        fichiers = [f for f in fichiers if not f.name.startswith('_')]
        
        print(f" Nettoyage de {len(fichiers)} README...")
        
        for fichier in tqdm(fichiers, desc="Nettoyage"):
            # Lire le contenu
            with open(fichier, 'r', encoding='utf-8') as f:
                contenu = f.read()
            
            # Nettoyer
            contenu_nettoye = self.nettoyer_contenu(contenu)
            
            # Sauvegarder
            chemin_sortie = Path(dossier_sortie) / fichier.name
            with open(chemin_sortie, 'w', encoding='utf-8') as f:
                f.write(contenu_nettoye)
        
        print(f" {len(fichiers)} README nettoyés dans {dossier_sortie}/")


if __name__ == "__main__":
    nettoyeur = NettoyeurReadme()
    nettoyeur.nettoyer_tous()