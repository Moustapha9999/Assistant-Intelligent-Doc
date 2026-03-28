"""
Module de découpage (chunking) des README en segments
"""

import os
import re
import yaml
from pathlib import Path
from tqdm import tqdm


class DecoupeurReadme:
    def __init__(self, taille_chunk=500, overlap=100):
        """
        Initialise le découpeur
        
        Args:
            taille_chunk: Taille cible d'un chunk (en mots)
            overlap: Chevauchement entre chunks (en mots)
        """
        self.taille_chunk = taille_chunk
        self.overlap = overlap
    
    def extraire_metadonnees(self, contenu):
        """Extrait les métadonnées YAML du README"""

        if contenu.startswith('---'):
            parties = contenu.split('---', 2)
            if len(parties) >= 3:
                metadonnees_yaml = parties[1]
                texte = parties[2]
                metadonnees = yaml.safe_load(metadonnees_yaml)
                return metadonnees, texte
        
        return {}, contenu
    
    def decouper_par_sections(self, texte):
        """Découpe le texte par sections Markdown (titres)"""
        
        # Regex pour détecter les titres Markdown (# Titre)
        pattern_titre = r'^(#{1,6})\s+(.+)$'
        
        sections = []
        section_courante = {
            'niveau': 0,
            'titre': 'Introduction',
            'contenu': []
        }
        
        lignes = texte.split('\n')
        
        for ligne in lignes:
            match = re.match(pattern_titre, ligne.strip())
            
            if match:
                # Nouvelle section trouvée
                if section_courante['contenu']:
                    sections.append(section_courante)
                
                niveau = len(match.group(1))  # Nombre de #
                titre = match.group(2).strip()
                
                section_courante = {
                    'niveau': niveau,
                    'titre': titre,
                    'contenu': []
                }
            else:
                section_courante['contenu'].append(ligne)
        
        # Ajouter la dernière section
        if section_courante['contenu']:
            sections.append(section_courante)
        
        return sections
    
    def decouper_section_en_chunks(self, section_texte):
        """Découpe une section en chunks de taille fixe avec overlap"""
        
        mots = section_texte.split()
        chunks = []
        
        i = 0
        while i < len(mots):
            # Prendre taille_chunk mots
            chunk_mots = mots[i:i + self.taille_chunk]
            chunk_texte = ' '.join(chunk_mots)
            
            chunks.append(chunk_texte)
            
            # Avancer avec overlap
            i += (self.taille_chunk - self.overlap)
        
        return chunks
    
    def decouper_readme(self, fichier_path):
        """Découpe un README complet en chunks"""
        
        with open(fichier_path, 'r', encoding='utf-8') as f:
            contenu = f.read()
        
        # Extraire métadonnées
        metadonnees, texte = self.extraire_metadonnees(contenu)
        
        # Découper par sections
        sections = self.decouper_par_sections(texte)
        
        # Créer les chunks
        tous_chunks = []
        
        for section in sections:
            section_texte = '\n'.join(section['contenu']).strip()
            
            if not section_texte:
                continue
            
            # Découper la section en chunks
            chunks = self.decouper_section_en_chunks(section_texte)
            
            for idx, chunk_texte in enumerate(chunks):
                chunk = {
                    'texte': chunk_texte,
                    'metadonnees': {
                        **metadonnees,
                        'section_titre': section['titre'],
                        'section_niveau': section['niveau'],
                        'chunk_index': idx,
                        'source_file': fichier_path.name
                    }
                }
                tous_chunks.append(chunk)
        
        return tous_chunks
    
    def decouper_tous(self, dossier_entree='data/processed/readmes_nettoyes',
                     dossier_sortie='data/processed/chunks'):
        """Découpe tous les README en chunks"""
        
        os.makedirs(dossier_sortie, exist_ok=True)
        
        fichiers = list(Path(dossier_entree).glob('*.md'))
        
        print(f" Découpage de {len(fichiers)} README...")
        
        tous_chunks = []
        
        for fichier in tqdm(fichiers, desc="Découpage"):
            chunks = self.decouper_readme(fichier)
            tous_chunks.extend(chunks)
        
        # Sauvegarder tous les chunks dans un seul fichier YAML
        chemin_sortie = Path(dossier_sortie) / 'tous_chunks.yaml'
        
        with open(chemin_sortie, 'w', encoding='utf-8') as f:
            yaml.dump(tous_chunks, f, allow_unicode=True, default_flow_style=False)
        
        print(f" {len(tous_chunks)} chunks créés")
        print(f" Sauvegardés dans {chemin_sortie}")
        
        # Statistiques
        self.afficher_statistiques(tous_chunks)
        
        return tous_chunks
    
    def afficher_statistiques(self, chunks):
        """Affiche des statistiques sur les chunks"""
        
        nb_chunks = len(chunks)
        
        # Stats par langage
        langages = {}
        for chunk in chunks:
            lang = chunk['metadonnees'].get('langage', 'Inconnu')
            langages[lang] = langages.get(lang, 0) + 1
        
        print("\n Statistiques:")
        print(f"   Total chunks: {nb_chunks}")
        print(f"   Par langage:")
        for lang, count in sorted(langages.items(), key=lambda x: x[1], reverse=True):
            print(f"      - {lang}: {count} chunks")


if __name__ == "__main__":
    decoupeur = DecoupeurReadme(taille_chunk=500, overlap=100)
    decoupeur.decouper_tous()
