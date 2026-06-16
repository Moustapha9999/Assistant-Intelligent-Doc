"""
Module de découpage en chunks — Version enrichie
Gère : Markdown, Code Python, JS, Java, Go, SQL, Notebooks Jupyter
ISI KOMUNIK · Master IAGE
"""

import os
import re
import json
import yaml
from pathlib import Path
from tqdm import tqdm

# ── Paramètres de chunking ────────────────────────────────────────
TAILLE_CHUNK_TEXTE  = 500   # mots pour texte/doc
TAILLE_CHUNK_CODE   = 80    # lignes pour code
OVERLAP_TEXTE       = 100   # mots overlap
OVERLAP_CODE        = 15    # lignes overlap

EXTENSIONS_CODE = {
    '.py', '.js', '.ts', '.java', '.go', '.rs',
    '.cpp', '.c', '.h', '.sql',
}

def detecter_type(nom_fichier: str) -> str:
    ext = Path(nom_fichier).suffix.lower()
    if ext == '.ipynb': return 'notebook'
    if ext in EXTENSIONS_CODE: return 'code'
    if ext in {'.md', '.rst', '.txt'}: return 'markdown'
    return 'texte'


# ── Extraction métadonnées ────────────────────────────────────────
def extraire_metadonnees(contenu: str) -> tuple:
    """Extrait les métadonnées YAML du frontmatter"""
    meta = {}
    corps = contenu

    if contenu.startswith('---'):
        try:
            fin = contenu.index('---', 3)
            bloc_yaml = contenu[3:fin].strip()
            meta = yaml.safe_load(bloc_yaml) or {}
            corps = contenu[fin + 3:].strip()
        except (ValueError, yaml.YAMLError):
            pass

    return meta, corps


# ── Chunking Markdown / Texte ─────────────────────────────────────
def chunker_markdown(texte: str, meta: dict) -> list:
    """Découpe le texte en chunks par sections avec overlap"""
    chunks = []
    sections = re.split(r'\n#{1,4}\s+', texte)
    titres   = re.findall(r'\n(#{1,4}\s+[^\n]+)', '\n' + texte)

    section_titre = meta.get('chemin_fichier', 'Introduction')

    for i, section in enumerate(sections):
        if not section.strip():
            continue

        titre = titres[i - 1].strip('#').strip() if i > 0 and i - 1 < len(titres) else section_titre
        mots  = section.split()

        for j in range(0, len(mots), TAILLE_CHUNK_TEXTE - OVERLAP_TEXTE):
            bloc = mots[j:j + TAILLE_CHUNK_TEXTE]
            if len(bloc) < 20:
                continue

            chunks.append({
                'texte'        : ' '.join(bloc),
                'section_titre': titre[:200],
                'type_chunk'   : 'markdown',
                **meta,
            })

    return chunks


# ── Chunking Code ─────────────────────────────────────────────────
def chunker_code(code: str, meta: dict) -> list:
    """Découpe le code en chunks logiques par fonctions/classes"""
    chunks = []
    lignes = code.split('\n')
    ext    = Path(meta.get('chemin_fichier', '.py')).suffix.lower()

    # Patterns de séparation selon le langage
    patterns = {
        '.py'  : r'^(def |class |async def )',
        '.js'  : r'^(function |class |const .+ = .*(function|\(.*\) =>)|export )',
        '.ts'  : r'^(function |class |interface |type |export |const .+ = )',
        '.java': r'^(public |private |protected |class |interface |enum )',
        '.go'  : r'^(func |type |var |const )',
        '.rs'  : r'^(fn |pub fn |impl |struct |enum |trait )',
        '.cpp' : r'^(void |int |bool |class |struct |namespace |template)',
        '.c'   : r'^(void |int |bool |char |float |double |struct )',
        '.sql' : r'^(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|WITH)',
    }

    pattern = patterns.get(ext, r'^(def |class |function )')

    # Trouver les points de séparation
    separateurs = [0]
    for i, ligne in enumerate(lignes):
        if i > 0 and re.match(pattern, ligne, re.IGNORECASE):
            separateurs.append(i)
    separateurs.append(len(lignes))

    for k in range(len(separateurs) - 1):
        debut = separateurs[k]
        fin   = min(separateurs[k + 1], debut + TAILLE_CHUNK_CODE)
        bloc  = lignes[debut:fin]

        if len([l for l in bloc if l.strip()]) < 3:
            continue

        # Titre : première ligne non vide
        titre = next((l.strip() for l in bloc if l.strip()), 'code')[:100]

        chunks.append({
            'texte'        : '\n'.join(bloc),
            'section_titre': titre,
            'type_chunk'   : 'code',
            **meta,
        })

    # Si pas de séparateurs trouvés → chunking par lignes
    if len(chunks) == 0:
        for j in range(0, len(lignes), TAILLE_CHUNK_CODE - OVERLAP_CODE):
            bloc = lignes[j:j + TAILLE_CHUNK_CODE]
            if len([l for l in bloc if l.strip()]) < 3:
                continue
            titre = next((l.strip() for l in bloc if l.strip()), 'code')[:100]
            chunks.append({
                'texte'        : '\n'.join(bloc),
                'section_titre': titre,
                'type_chunk'   : 'code',
                **meta,
            })

    return chunks


# ── Chunking Notebook Jupyter ─────────────────────────────────────
def chunker_notebook(contenu: str, meta: dict) -> list:
    """Extrait les cellules d'un notebook Jupyter"""
    chunks = []
    try:
        nb = json.loads(contenu)
        cells = nb.get('cells', [])

        for i, cell in enumerate(cells):
            cell_type = cell.get('cell_type', '')
            source    = ''.join(cell.get('source', []))

            if not source.strip():
                continue

            if cell_type == 'markdown':
                # Cellule markdown
                chunks.append({
                    'texte'        : source[:2000],
                    'section_titre': f'Notebook cell {i+1} (markdown)',
                    'type_chunk'   : 'notebook_markdown',
                    **meta,
                })
            elif cell_type == 'code':
                # Cellule code
                chunks.append({
                    'texte'        : source[:2000],
                    'section_titre': f'Notebook cell {i+1} (code)',
                    'type_chunk'   : 'notebook_code',
                    **meta,
                })

                # Outputs (résultats)
                outputs = cell.get('outputs', [])
                for out in outputs[:2]:
                    texte_out = ''.join(out.get('text', out.get('data', {}).get('text/plain', [])))
                    if texte_out.strip():
                        chunks.append({
                            'texte'        : f"# Output:\n{texte_out[:500]}",
                            'section_titre': f'Notebook cell {i+1} (output)',
                            'type_chunk'   : 'notebook_output',
                            **meta,
                        })

    except (json.JSONDecodeError, KeyError):
        pass

    return chunks


# ── Découpage principal ───────────────────────────────────────────
def decouper_fichier(chemin: str) -> list:
    """Découpe un fichier en chunks selon son type"""
    try:
        with open(chemin, 'r', encoding='utf-8', errors='replace') as f:
            contenu = f.read()
    except Exception:
        return []

    if not contenu.strip():
        return []

    meta, corps = extraire_metadonnees(contenu)

    # Métadonnées par défaut depuis le nom du fichier
    if not meta.get('nom_complet'):
        meta['nom_complet'] = Path(chemin).stem.replace('_', '/', 1)
    if not meta.get('chemin_fichier'):
        meta['chemin_fichier'] = Path(chemin).name

    type_doc = detecter_type(meta.get('chemin_fichier', chemin))

    if type_doc == 'notebook':
        return chunker_notebook(corps, meta)
    elif type_doc == 'code':
        return chunker_code(corps, meta)
    else:
        return chunker_markdown(corps, meta)


# ── Pipeline principal ────────────────────────────────────────────
def decouper_corpus(
    dossier_entree : str = 'data/raw/readmes',
    dossier_sortie : str = 'data/processed/chunks',
    fichier_sortie : str = 'tous_chunks.json',
):
    os.makedirs(dossier_sortie, exist_ok=True)

    fichiers = list(Path(dossier_entree).glob('*'))
    fichiers = [f for f in fichiers if f.is_file() and not f.name.startswith('_')]

    print(f"📄 Découpage de {len(fichiers)} fichiers...")

    tous_chunks = []
    stats = {}

    for fichier in tqdm(fichiers, desc="Découpage"):
        chunks = decouper_fichier(str(fichier))
        tous_chunks.extend(chunks)

        for chunk in chunks:
            lang = chunk.get('langage', 'Unknown')
            stats[lang] = stats.get(lang, 0) + 1

    # Sauvegarde
    chemin_sortie = Path(dossier_sortie) / fichier_sortie
    with open(chemin_sortie, 'w', encoding='utf-8') as f:
        json.dump(tous_chunks, f, ensure_ascii=False)

    print(f"\n✅ {len(tous_chunks)} chunks créés")
    print(f"   Sauvegardés dans {chemin_sortie}")
    print(f"\n📊 Statistiques par langage :")
    for lang, nb in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"      - {lang}: {nb} chunks")

    return tous_chunks


if __name__ == "__main__":
    decouper_corpus()