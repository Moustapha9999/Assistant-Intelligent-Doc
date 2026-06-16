"""
Module de gestion des fichiers uploadés
Supporte : PDF, Images, Code (.py, .js, .ts, .java, .c, .cpp, .go, .rs), Markdown, Texte
"""

import io
import base64
import importlib
from pathlib import Path
from typing import Dict

# ── Extraction PDF ──────────────────────────────────────────────
def extraire_pdf(contenu_bytes: bytes) -> str:
    """Extrait le texte d'un PDF"""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(contenu_bytes)) as pdf:
            pages = []
            for i, page in enumerate(pdf.pages, 1):
                texte = page.extract_text()
                if texte and texte.strip():
                    pages.append(f"[Page {i}]\n{texte.strip()}")
            return "\n\n".join(pages) if pages else "PDF vide ou non lisible."
    except ImportError:
        try:
            pypdf = importlib.import_module("pypdf")
            reader = pypdf.PdfReader(io.BytesIO(contenu_bytes))
            pages = []
            for i, page in enumerate(reader.pages, 1):
                texte = page.extract_text()
                if texte:
                    pages.append(f"[Page {i}]\n{texte.strip()}")
            return "\n\n".join(pages) if pages else "PDF vide."
        except Exception as e:
            return f"Erreur extraction PDF : {e}"
    except Exception as e:
        return f"Erreur PDF : {e}"


# ── Extraction Image ────────────────────────────────────────────
def encoder_image_base64(contenu_bytes: bytes, media_type: str) -> str:
    """Encode une image en base64 pour envoi au LLM"""
    return base64.b64encode(contenu_bytes).decode("utf-8")


# ── Extraction Code & Texte ─────────────────────────────────────
def extraire_texte(contenu_bytes: bytes, nom_fichier: str) -> str:
    """Extrait le contenu texte/code d'un fichier"""
    try:
        return contenu_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return contenu_bytes.decode("latin-1")
        except Exception:
            return f"Impossible de lire le fichier {nom_fichier}"


# ── Détection type de fichier ───────────────────────────────────
EXTENSIONS_CODE = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".java": "java", ".c": "c", ".cpp": "c++", ".h": "c",
    ".go": "go", ".rs": "rust", ".php": "php", ".rb": "ruby",
    ".cs": "csharp", ".kt": "kotlin", ".swift": "swift",
    ".sh": "bash", ".sql": "sql", ".r": "r", ".dart": "dart",
}

EXTENSIONS_DOC = {
    ".md": "markdown", ".txt": "texte", ".rst": "rst",
    ".yaml": "yaml", ".yml": "yaml", ".json": "json",
    ".toml": "toml", ".xml": "xml", ".html": "html", ".css": "css",
}

EXTENSIONS_IMAGE = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
EXTENSIONS_PDF   = {".pdf"}


def detecter_type(nom_fichier: str) -> str:
    """Retourne le type du fichier"""
    ext = Path(nom_fichier).suffix.lower()
    if ext in EXTENSIONS_PDF:    return "pdf"
    if ext in EXTENSIONS_IMAGE:  return "image"
    if ext in EXTENSIONS_CODE:   return "code"
    if ext in EXTENSIONS_DOC:    return "doc"
    return "inconnu"


def get_langage(nom_fichier: str) -> str:
    """Retourne le langage de programmation"""
    ext = Path(nom_fichier).suffix.lower()
    return EXTENSIONS_CODE.get(ext, EXTENSIONS_DOC.get(ext, "texte"))


# ── Traitement principal ────────────────────────────────────────
def traiter_fichier(fichier_uploade) -> Dict:
    """
    Traite un fichier uploadé depuis Streamlit.
    Retourne un dict avec type, contenu, métadonnées.
    """
    nom     = fichier_uploade.name
    contenu = fichier_uploade.read()
    taille  = len(contenu)
    type_f  = detecter_type(nom)
    langage = get_langage(nom)

    resultat = {
        "nom"    : nom,
        "type"   : type_f,
        "langage": langage,
        "taille" : taille,
        "contenu": "",
        "image_b64": None,
        "media_type": None,
        "erreur" : None,
    }

    try:
        if type_f == "pdf":
            resultat["contenu"] = extraire_pdf(contenu)

        elif type_f == "image":
            ext = Path(nom).suffix.lower()
            media_map = {
                ".png": "image/png", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg", ".gif": "image/gif",
                ".webp": "image/webp",
            }
            resultat["media_type"] = media_map.get(ext, "image/png")
            resultat["image_b64"]  = encoder_image_base64(contenu, resultat["media_type"])
            resultat["contenu"]    = f"[Image : {nom}]"

        elif type_f in ("code", "doc"):
            texte = extraire_texte(contenu, nom)
            # Limiter à 8000 chars pour le contexte
            if len(texte) > 8000:
                texte = texte[:8000] + f"\n\n[... fichier tronqué à 8000 caractères sur {len(texte)} ...]"
            resultat["contenu"] = texte

        else:
            resultat["contenu"] = extraire_texte(contenu, nom)

    except Exception as e:
        resultat["erreur"]  = str(e)
        resultat["contenu"] = f"Erreur lors du traitement : {e}"

    return resultat


def formater_pour_prompt(fichiers_traites: list) -> str:
    """Formate les fichiers uploadés pour injection dans le prompt"""
    if not fichiers_traites:
        return ""

    blocs = []
    for f in fichiers_traites:
        if f["type"] == "image":
            blocs.append(f"[Fichier image : {f['nom']}] — analyse visuelle disponible")
        elif f["contenu"]:
            lang = f["langage"]
            if f["type"] == "code":
                blocs.append(
                    f"[Fichier {f['nom']} — {lang}]\n"
                    f"```{lang}\n{f['contenu']}\n```"
                )
            else:
                blocs.append(
                    f"[Fichier {f['nom']} — {lang}]\n{f['contenu']}"
                )

    return "\n\n" + ("─" * 50 + "\n").join(blocs) if blocs else ""