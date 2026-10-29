"""Contrôles de sécurité des pièces jointes : signatures, archives Office, images.

Les fichiers ne sont jamais écrits sur disque ni exécutés : tout est traité en mémoire.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Optional, Tuple

import config


class FichierRefuse(Exception):
    """Fichier rejeté ; le message est destiné à l'utilisateur (aucun détail interne)."""


_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

_MEMBRES_OFFICE = {
    ".docx": "word/document.xml",
    ".xlsx": "xl/workbook.xml",
    ".pptx": "ppt/presentation.xml",
}

EXTENSIONS_TEXTE = {
    ".txt", ".md", ".rst", ".csv", ".tsv", ".json", ".yaml", ".yml", ".toml",
    ".xml", ".html", ".htm", ".py", ".js", ".ts", ".java", ".go", ".rs", ".c",
    ".cpp", ".h", ".sql", ".sh",
}


def _signature_image(contenu: bytes) -> Optional[str]:
    if contenu.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if contenu.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if contenu[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if contenu[:4] == b"RIFF" and contenu[8:12] == b"WEBP":
        return "webp"
    if contenu[:2] == b"BM":
        return "bmp"
    return None


def _signature_audio(contenu: bytes) -> bool:
    tete = contenu[:16]
    return (
        (tete[:4] == b"RIFF" and tete[8:12] == b"WAVE")
        or tete[:3] == b"ID3"
        or (len(tete) > 1 and tete[0] == 0xFF and (tete[1] & 0xE0) == 0xE0)
        or tete[:4] == b"OggS"
        or tete[:4] == b"fLaC"
        or tete[4:8] == b"ftyp"
        or tete[:4] == b"\x1a\x45\xdf\xa3"
    )


def verifier_archive_office(contenu: bytes, ext: str) -> bool:
    """Valide un conteneur OOXML (zip) : structure attendue, taille décompressée bornée.

    Retourne True si le fichier contient des macros VBA (jamais exécutées, signalées).
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(contenu))
    except zipfile.BadZipFile as exc:
        raise FichierRefuse("Le fichier est corrompu ou n'est pas un document Office valide.") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > config.ARCHIVE_MAX_MEMBRES:
            raise FichierRefuse("Le document contient trop d'éléments internes pour être analysé.")
        total = sum(i.file_size for i in infos)
        if total > config.ARCHIVE_MAX_DECOMPRESSE:
            raise FichierRefuse("Le document est trop volumineux une fois décompressé.")
        for i in infos:
            if i.compress_size and i.file_size / i.compress_size > 200 and i.file_size > 10 * 1024 * 1024:
                raise FichierRefuse("Le document présente un taux de compression anormal (refusé par sécurité).")
        noms = {i.filename for i in infos}
        attendu = _MEMBRES_OFFICE.get(ext)
        if attendu and attendu not in noms:
            raise FichierRefuse(
                f"Le contenu ne correspond pas à un fichier {ext} (extension trompeuse ou fichier corrompu)."
            )
        return any(n.lower().endswith("vbaproject.bin") for n in noms)


def verifier_signature(nom: str, contenu: bytes) -> Tuple[str, bool]:
    """Vérifie que le contenu correspond à l'extension. Retourne (ext, macros_detectees)."""
    ext = Path(nom).suffix.lower()
    if not contenu:
        raise FichierRefuse("Le fichier est vide.")
    if ext == ".pdf":
        if b"%PDF-" not in contenu[:1024]:
            raise FichierRefuse("Le contenu ne correspond pas à un PDF (fichier corrompu ou renommé).")
        return ext, False
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
        if _signature_image(contenu) is None:
            raise FichierRefuse("Le contenu ne correspond pas à une image valide.")
        return ext, False
    if ext in _MEMBRES_OFFICE:
        return ext, verifier_archive_office(contenu, ext)
    if ext == ".xls":
        if not contenu.startswith(_OLE):
            raise FichierRefuse("Le contenu ne correspond pas à un classeur Excel .xls.")
        return ext, False
    if ext in {".wav", ".mp3", ".m4a", ".ogg", ".webm"}:
        if not _signature_audio(contenu):
            raise FichierRefuse("Le contenu ne correspond pas à un fichier audio reconnu.")
        return ext, False
    if ext in EXTENSIONS_TEXTE:
        if b"\x00" in contenu[:8192]:
            raise FichierRefuse("Ce fichier texte contient des données binaires : il est peut-être corrompu ou renommé.")
        return ext, False
    raise FichierRefuse(f"Format {ext or 'sans extension'} non pris en charge.")


def normaliser_image(contenu: bytes, cote_max: int = 2000) -> Tuple[bytes, str, Tuple[int, int]]:
    """Décode l'image (validation réelle), la réduit si besoin et la ré-encode (PNG/JPEG).

    Le ré-encodage supprime les métadonnées et tout contenu caché ; GIF animé : 1re image.
    """
    from PIL import Image, UnidentifiedImageError

    Image.MAX_IMAGE_PIXELS = config.IMAGE_MAX_PIXELS
    try:
        with Image.open(io.BytesIO(contenu)) as img:
            img.load()
            taille = img.size
            img = img.convert("RGBA") if img.mode in ("P", "LA", "RGBA") else img.convert("RGB")
    except Image.DecompressionBombError as exc:
        raise FichierRefuse("L'image a une résolution trop élevée pour être analysée.") from exc
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise FichierRefuse("L'image est corrompue ou illisible.") from exc

    if max(img.size) > cote_max:
        img.thumbnail((cote_max, cote_max))
    sortie = io.BytesIO()
    if img.mode == "RGBA":
        img.save(sortie, format="PNG", optimize=True)
        media = "image/png"
        if sortie.tell() > 3_500_000:
            fond = Image.new("RGB", img.size, "white")
            fond.paste(img, mask=img.split()[-1])
            img = fond
    if img.mode != "RGBA":
        sortie = io.BytesIO()
        img.save(sortie, format="JPEG", quality=88)
        media = "image/jpeg"
    return sortie.getvalue(), media, taille
