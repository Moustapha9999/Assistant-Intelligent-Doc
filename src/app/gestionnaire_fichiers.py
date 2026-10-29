"""
Pièces jointes de la conversation : validation, extraction, préparation multimodale
et mise en forme pour le prompt.

Chaîne : `traiter_fichier` (validation serveur + extraction en mémoire)
→ `preparer_contenus_multimodaux` (vision, OCR des pages numérisées, transcription audio)
→ `formater_pour_prompt` (sélection des passages pertinents dans le budget de contexte).
"""

from __future__ import annotations

import base64
import logging
import math
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from app.extraction_documents import extraire
from app.securite_fichiers import FichierRefuse, normaliser_image, verifier_signature

log = logging.getLogger(__name__)

# ── Types de fichiers ───────────────────────────────────────────
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
    ".toml": "toml", ".xml": "xml", ".html": "html", ".htm": "html", ".css": "css",
}

EXTENSIONS_WORD = {".docx"}
EXTENSIONS_TABLEUR = {".xlsx", ".xls", ".csv", ".tsv"}
EXTENSIONS_PRESENTATION = {".pptx"}
EXTENSIONS_IMAGE = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
EXTENSIONS_PDF = {".pdf"}
EXTENSIONS_AUDIO = {".wav", ".mp3", ".m4a", ".ogg", ".webm", ".flac", ".mpeg", ".mp4"}

LIBELLES_TYPE = {
    "pdf": "PDF", "word": "Word", "tableur": "Tableur", "presentation": "PowerPoint",
    "image": "Image", "audio": "Audio", "code": "Code", "doc": "Texte",
}

# Clés volumineuses ou transitoires : jamais persistées ni journalisées
CLES_TRANSITOIRES = ("image_b64", "audio_bytes", "bytes", "pages_ocr", "pages_figures")


def detecter_type(nom_fichier: str) -> str:
    ext = Path(nom_fichier).suffix.lower()
    if ext in EXTENSIONS_PDF:
        return "pdf"
    if ext in EXTENSIONS_WORD:
        return "word"
    if ext in EXTENSIONS_TABLEUR:
        return "tableur"
    if ext in EXTENSIONS_PRESENTATION:
        return "presentation"
    if ext in EXTENSIONS_IMAGE:
        return "image"
    if ext in EXTENSIONS_AUDIO:
        return "audio"
    if ext in EXTENSIONS_CODE:
        return "code"
    if ext in EXTENSIONS_DOC:
        return "doc"
    return "inconnu"


def get_langage(nom_fichier: str) -> str:
    ext = Path(nom_fichier).suffix.lower()
    return EXTENSIONS_CODE.get(ext, EXTENSIONS_DOC.get(ext, "texte"))


def taille_lisible(octets: int) -> str:
    if octets < 1024:
        return f"{octets} o"
    if octets < 1024 * 1024:
        return f"{octets / 1024:.0f} Ko"
    return f"{octets / (1024 * 1024):.1f} Mo"


def _nom_sur(nom: str) -> str:
    """Nom affichable : sans chemin ni caractères de contrôle (jamais utilisé comme chemin)."""
    nom = Path(str(nom or "fichier").replace("\\", "/")).name
    nom = "".join(c for c in nom if c.isprintable()).strip()
    return nom[:120] or "fichier"


def _lire_octets(fichier) -> bytes:
    if isinstance(fichier, (bytes, bytearray)):
        return bytes(fichier)
    if hasattr(fichier, "getvalue"):
        return fichier.getvalue()
    data = fichier.read()
    if hasattr(fichier, "seek"):
        try:
            fichier.seek(0)
        except Exception:
            pass
    return data


def _texte_segments(segments: List[Dict[str, str]]) -> str:
    return "\n\n".join(
        (f"[{s['ref']}]\n" if s.get("ref") else "") + s["texte"] for s in segments
    )


# ── Traitement principal ────────────────────────────────────────
def traiter_fichier(fichier_uploade, nom: Optional[str] = None) -> Dict[str, Any]:
    """Valide (extension, taille, signature) puis extrait le contenu d'une pièce jointe.

    `resultat["erreur"]` contient un message destiné à l'utilisateur si le fichier est refusé.
    """
    nom = _nom_sur(nom or getattr(fichier_uploade, "name", "fichier"))
    ext = Path(nom).suffix.lower()
    type_f = detecter_type(nom)
    resultat: Dict[str, Any] = {
        "nom": nom,
        "type": type_f,
        "langage": get_langage(nom),
        "taille": 0,
        "contenu": "",
        "segments": [],
        "resume": "",
        "avertissements": [],
        "image_b64": None,
        "media_type": None,
        "erreur": None,
    }

    if ext in config.UPLOAD_FORMATS_REFUSES:
        resultat["erreur"] = config.UPLOAD_FORMATS_REFUSES[ext]
        return resultat
    if ext not in config.UPLOAD_EXTENSIONS_OK:
        resultat["erreur"] = f"Format non pris en charge : {ext or 'fichier sans extension'}."
        return resultat

    try:
        contenu = _lire_octets(fichier_uploade)
    except Exception:
        resultat["erreur"] = "Le fichier n'a pas pu être lu. Réessayez l'import."
        return resultat
    resultat["taille"] = len(contenu)
    if len(contenu) > config.UPLOAD_MAX_BYTES:
        mo = config.UPLOAD_MAX_BYTES / (1024 * 1024)
        resultat["erreur"] = (
            f"Fichier trop volumineux ({taille_lisible(len(contenu))}, maximum {mo:.0f} Mo)."
        )
        return resultat

    try:
        _, macros = verifier_signature(nom, contenu)
        if macros:
            resultat["avertissements"].append(
                "Le document contient des macros : elles ont été ignorées (jamais exécutées)."
            )
        if type_f == "image":
            octets, media, (larg, haut) = normaliser_image(contenu)
            resultat["image_b64"] = base64.b64encode(octets).decode("ascii")
            resultat["media_type"] = media
            resultat["resume"] = f"Image · {larg}×{haut}"
        elif type_f == "audio":
            resultat["audio_bytes"] = contenu
            resultat["resume"] = "Audio"
        else:
            ex = extraire(contenu, ext)
            resultat["segments"] = ex["segments"]
            resultat["avertissements"] += ex["avertissements"]
            resultat["resume"] = ex["resume"]
            if ex.get("pages_ocr"):
                resultat["pages_ocr"] = ex["pages_ocr"]
            if ex.get("pages_figures"):
                resultat["pages_figures"] = ex["pages_figures"]
            resultat["contenu"] = _texte_segments(resultat["segments"])
    except FichierRefuse as exc:
        resultat["erreur"] = str(exc)
    except Exception as exc:
        log.warning("Extraction échouée (%s, %s) : %s", ext, nom, type(exc).__name__)
        resultat["erreur"] = (
            "Le contenu n'a pas pu être extrait. Vérifiez que le fichier n'est pas corrompu "
            "ou convertissez-le dans un autre format."
        )
    return resultat


# ── Préparation multimodale (vision, OCR, audio) ────────────────
_MOTS_VISUELS = re.compile(
    r"graphi|figure|sch[ée]ma|diagram|courbe|image|illustration|photo|visuel|chart|plot|logo|capture",
    re.I,
)


def _prompt_image(question: str) -> str:
    q = (question or "").strip()
    return (
        "Tu analyses une image jointe par l'utilisateur.\n"
        + (f"Question de l'utilisateur : {q}\n" if q else "")
        + "Réponds en français avec :\n"
        "1. La transcription fidèle de tout le texte lisible (OCR), en conservant la structure "
        "(tableaux en Markdown, code dans un bloc de code).\n"
        "2. La description des éléments visuels pertinents (interface, graphique : axes, séries, "
        "valeurs lisibles ; schéma, photo).\n"
        "3. Les éléments qui répondent à la question.\n"
        "Si une partie est floue ou illisible, dis-le explicitement. N'invente aucun texte ni valeur."
    )


_PROMPT_OCR = (
    "Transcris fidèlement et intégralement le texte de cette page de document numérisé, "
    "en conservant les titres, paragraphes, listes et tableaux (tableaux en Markdown). "
    "N'ajoute aucun commentaire. Remplace un passage illisible par [illisible]. "
    "Si la page ne contient aucun texte, réponds exactement : [page sans texte]."
)


def _client_vision(llm_client):
    if llm_client is not None:
        return llm_client
    from generation.llm_client import LLMClient

    return LLMClient()


def _inserer_segment_page(segments: List[Dict[str, str]], num: int, seg: Dict[str, str]) -> None:
    for i, s in enumerate(segments):
        m = re.match(r"page (\d+)", s.get("ref", ""))
        if m and int(m.group(1)) > num:
            segments.insert(i, seg)
            return
    segments.append(seg)


def preparer_contenus_multimodaux(
    fichiers_traites: List[Dict[str, Any]],
    question: str = "",
    llm_client=None,
) -> List[Dict[str, Any]]:
    """Transmet réellement les contenus non textuels aux modèles adaptés.

    - images : modèle de vision Groq (contenu visuel en base64) ;
    - pages PDF sans texte : OCR par le modèle de vision ;
    - pages PDF à figures : analyse visuelle si la question porte sur un élément visuel ;
    - audio : transcription Whisper.
    Les dicts sont enrichis en place ; les échecs deviennent des avertissements explicites.
    """
    if not fichiers_traites:
        return fichiers_traites
    besoin_vision = any(
        (f.get("type") == "image" and f.get("image_b64"))
        or f.get("pages_ocr")
        or (f.get("pages_figures") and _MOTS_VISUELS.search(question or ""))
        for f in fichiers_traites
    )
    client = None
    if besoin_vision:
        try:
            client = _client_vision(llm_client)
        except Exception:
            client = None

    def _vision(b64: str, media: str, prompt: str) -> Optional[str]:
        if client is None:
            return None
        texte, _ = client.analyser_image(image_b64=b64, media_type=media, question=prompt)
        return texte or None

    def _raison() -> str:
        return (getattr(client, "derniere_erreur_vision", None)
                or "le service d'analyse d'images est indisponible.")

    nb_images = 0
    for f in fichiers_traites:
        avert = f.setdefault("avertissements", [])

        if f.get("type") == "image" and f.get("image_b64"):
            nb_images += 1
            if nb_images > config.FICHIERS_MAX_IMAGES_VISION:
                f["vision_ok"] = False
                avert.append(
                    f"Image non analysée : au plus {config.FICHIERS_MAX_IMAGES_VISION} images par message."
                )
                continue
            description = _vision(f["image_b64"], f.get("media_type") or "image/png",
                                  _prompt_image(question))
            if description:
                f["contenu"] = description
                f["segments"] = [{"ref": "analyse visuelle", "texte": description}]
                f["vision_ok"] = True
            else:
                f["vision_ok"] = False
                avert.append(f"Image non analysée : {_raison()}")

        if f.get("pages_ocr"):
            echecs = []
            for p in f.pop("pages_ocr"):
                texte = _vision(p["image_b64"], p["media_type"], _PROMPT_OCR)
                if texte:
                    _inserer_segment_page(f.setdefault("segments", []), p["page"],
                                          {"ref": f"page {p['page']} (OCR)", "texte": texte})
                else:
                    echecs.append(str(p["page"]))
            if echecs:
                avert.append(f"OCR impossible pour les pages {', '.join(echecs)} : {_raison()}")
            f["contenu"] = _texte_segments(f.get("segments", []))
            if not f.get("segments"):
                f["erreur_analyse"] = "Aucun texte n'a pu être lu dans ce document numérisé."

        if f.get("pages_figures") and _MOTS_VISUELS.search(question or ""):
            segs = [s for s in f.get("segments", []) if not s["ref"].endswith("(figures)")]
            for p in f["pages_figures"]:
                texte = _vision(p["image_b64"], p["media_type"], _prompt_image(question))
                if texte:
                    _inserer_segment_page(segs, p["page"],
                                          {"ref": f"page {p['page']} (figures)", "texte": texte})
            f["segments"] = segs
            f["contenu"] = _texte_segments(segs)

        if f.get("type") == "audio" and f.get("audio_bytes"):
            try:
                texte = transcrire_audio(f["audio_bytes"], nom=f.get("nom") or "audio.wav")
            except Exception as exc:
                log.warning("Transcription échouée : %s", type(exc).__name__)
                texte = ""
            if texte:
                f["segments"] = [{"ref": "transcription", "texte": texte}]
                f["contenu"] = texte
                f.pop("audio_bytes", None)
            else:
                avert.append("Audio non transcrit : service de transcription indisponible.")
    return fichiers_traites


# Compat : ancien nom utilisé par l'orchestrateur
analyser_images_vision = preparer_contenus_multimodaux


def necessite_preparation(fichiers: List[Dict[str, Any]], question: str = "") -> bool:
    return any(
        (f.get("type") == "image" and f.get("image_b64"))
        or f.get("pages_ocr")
        or (f.get("type") == "audio" and f.get("audio_bytes"))
        or (f.get("pages_figures") and _MOTS_VISUELS.search(question or ""))
        for f in fichiers or []
    )


# ── Sélection des passages pertinents (documents volumineux) ────
_MOTS_VIDES = set(
    "les des une un le la de du et en au aux dans pour par sur avec sans que qui quoi est sont "
    "ce cet cette ces mon ma mes ton ta tes son sa ses nos vos leur leurs il elle ils elles on "
    "nous vous je tu me te se ne pas plus moins tres fait faire peux peut quel quelle quels "
    "quelles comment pourquoi combien donne donner dis dire explique fichier document joint "
    "jointe piece analyse analyser ceci cela the and for with what this that from".split()
)
_GENERIQUE = re.compile(
    r"r[ée]sum|synth[eè]s|global|ensemble|g[ée]n[ée]ral|tout le|enti[eè]r|anomal|principa|"
    r"de quoi parle|que contient|analyse (ce|le|la|les|cet)",
    re.I,
)


def _normaliser(texte: str) -> str:
    t = unicodedata.normalize("NFKD", texte.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def _termes(texte: str) -> List[str]:
    return [m for m in re.findall(r"[a-z0-9_]{3,}", _normaliser(texte)) if m not in _MOTS_VIDES]


def _decouper(segments: List[Dict[str, str]], taille: int = 1500) -> List[Dict[str, str]]:
    morceaux = []
    for s in segments:
        texte = s.get("texte") or ""
        if len(texte) <= taille:
            morceaux.append({"ref": s.get("ref", ""), "texte": texte})
            continue
        courant, n = "", 0
        for para in re.split(r"(\n\s*\n|\n)", texte):
            if len(courant) + len(para) > taille and courant.strip():
                morceaux.append({"ref": f"{s.get('ref', '')} (partie {n + 1})", "texte": courant.strip()})
                courant, n = "", n + 1
            while len(para) > taille:
                morceaux.append({"ref": f"{s.get('ref', '')} (partie {n + 1})", "texte": para[:taille]})
                para, n = para[taille:], n + 1
            courant += para
        if courant.strip():
            morceaux.append({"ref": f"{s.get('ref', '')} (partie {n + 1})" if n else s.get("ref", ""),
                             "texte": courant.strip()})
    return morceaux


def selectionner_passages(segments: List[Dict[str, str]], question: str, budget: int):
    """Retourne (passages dans l'ordre du document, complet: bool)."""
    morceaux = _decouper(segments)
    total = sum(len(m["texte"]) + len(m["ref"]) + 10 for m in morceaux)
    if total <= budget or not morceaux:
        return morceaux, True

    termes_q = set(_termes(question))
    generique = bool(_GENERIQUE.search(question or "")) or not termes_q
    tf = [Counter(_termes(m["ref"] + " " + m["texte"])) for m in morceaux]
    n = len(morceaux)
    df = Counter(t for c in tf for t in set(c) if t in termes_q)
    scores = [
        sum(min(c[t], 3) * math.log(1 + n / df[t]) for t in termes_q if c.get(t))
        for c in tf
    ]

    choisis: List[int] = []
    taille = 0

    def prendre(i: int) -> bool:
        nonlocal taille
        cout = len(morceaux[i]["texte"]) + len(morceaux[i]["ref"]) + 10
        if i in choisis or taille + cout > budget:
            return False
        choisis.append(i)
        taille += cout
        return True

    prioritaires = [i for i, m in enumerate(morceaux)
                    if "structure" in m["ref"] or "statistiques" in m["ref"]]
    for i in [0] + prioritaires:
        prendre(i)
    if not generique and max(scores, default=0) > 0:
        for i in sorted(range(n), key=lambda k: -scores[k]):
            if scores[i] <= 0:
                break
            prendre(i)
    # Couverture répartie sur tout le document (résumés, questions générales, budget restant)
    pas = max(1, n // 12)
    for i in list(range(0, n, pas)) + list(range(n)):
        if taille >= budget * 0.97:
            break
        prendre(i)
    return [morceaux[i] for i in sorted(choisis)], False


def _repartir_budget(tailles: List[int], budget: int) -> List[int]:
    alloc = [0] * len(tailles)
    restant = budget
    ordre = sorted(range(len(tailles)), key=lambda i: tailles[i])
    for k, i in enumerate(ordre):
        part = restant // (len(tailles) - k)
        alloc[i] = min(tailles[i], part)
        restant -= alloc[i]
    return alloc


_REGLES = (
    "Règles pour les pièces jointes :\n"
    "- Fonde ta réponse sur le contenu ci-dessous, réellement extrait des fichiers ; cite la référence "
    "(page, feuille et lignes, section, diapositive) des informations utilisées.\n"
    "- N'invente jamais de valeur, de texte ou de cellule absent de ce contenu ; si l'information "
    "manque ou si seuls des extraits sont fournis, dis-le.\n"
    "- Distingue les valeurs présentes dans le fichier des calculs (les tiens ou ceux marqués "
    "« calculées par l'application »).\n"
    "- Si un fichier est signalé comme non analysé, ne décris pas son contenu et explique la limite."
)


def formater_pour_prompt(
    fichiers_traites: List[Dict[str, Any]],
    question: str = "",
    max_chars: Optional[int] = None,
    avec_regles: bool = True,
) -> str:
    """Contexte « pièces jointes » pour le prompt, dans un budget de caractères borné."""
    if not fichiers_traites:
        return ""
    budget = max_chars or config.FICHIERS_MAX_CHARS_PROMPT

    def _segments(f) -> List[Dict[str, str]]:
        if f.get("segments"):
            return f["segments"]
        contenu = (f.get("contenu") or "").strip()
        if not contenu or (f.get("type") == "image" and not f.get("vision_ok")):
            return []
        return [{"ref": "", "texte": contenu}]

    segs_par_fichier = [_segments(f) for f in fichiers_traites]
    tailles = [sum(len(s["texte"]) + len(s.get("ref", "")) + 10 for s in segs) for segs in segs_par_fichier]
    allocations = _repartir_budget(tailles, budget)

    blocs = []
    for f, segs, alloc, total in zip(fichiers_traites, segs_par_fichier, allocations, tailles):
        nom = f.get("nom", "fichier")
        libelle = LIBELLES_TYPE.get(f.get("type"), "Fichier")
        resume = f.get("resume") or libelle
        if f.get("type") == "image":
            entete = (f"[Image analysée : {nom}]" if f.get("vision_ok") else f"[Image : {nom}]")
        else:
            entete = f"[Fichier : {nom} — {resume}]"
        if f.get("rappel"):
            entete += " (joint plus tôt dans la conversation)"
        lignes = [entete]
        for a in f.get("avertissements") or []:
            lignes.append(f"Avertissement : {a}")
        if f.get("type") == "image" and not f.get("vision_ok"):
            lignes.append("Contenu visuel NON analysé : ne décris pas cette image.")
            blocs.append("\n".join(lignes))
            continue
        if not segs:
            lignes.append(f.get("erreur_analyse") or "Aucun contenu exploitable n'a été extrait.")
            blocs.append("\n".join(lignes))
            continue
        passages, complet = selectionner_passages(segs, question, max(alloc, 1200))
        if not complet:
            refs = [p["ref"] for p in passages if p["ref"]]
            lignes.append(
                f"Couverture : EXTRAITS sélectionnés ({sum(len(p['texte']) for p in passages)} "
                f"caractères transmis sur {total}) — références : {', '.join(refs[:25])}"
                + ("…" if len(refs) > 25 else "")
            )
        for p in passages:
            if p["ref"]:
                lignes.append(f"--- {p['ref']} ---")
            texte = p["texte"]
            if f.get("type") == "code":
                texte = f"```{f.get('langage', '')}\n{texte}\n```"
            lignes.append(texte)
        blocs.append("\n".join(lignes))

    corps = "\n\n".join(blocs)
    return f"{_REGLES}\n\n{corps}" if avec_regles else corps


def fichiers_de_rappel(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pièces jointes du dernier message utilisateur qui en contenait, marquées « rappel ».

    Copies superficielles : une nouvelle analyse visuelle ne remplace pas la description
    enregistrée avec le message d'origine.
    """
    for m in reversed(messages[:-1]):
        if m.get("role") == "user" and m.get("fichiers"):
            return [{**f, "rappel": True} for f in m["fichiers"]]
    return []


def fichiers_pour_persistance(f: Dict[str, Any]) -> Dict[str, Any]:
    """Version légère d'une pièce jointe pour SQLite : ni binaire, texte borné."""
    out = {k: v for k, v in f.items() if k not in CLES_TRANSITOIRES}
    if f.get("type") == "image" and f.get("image_b64"):
        out["image_omise"] = True
    limite = config.FICHIERS_PERSIST_MAX_CHARS
    segs, cumul = [], 0
    for s in out.get("segments") or []:
        if cumul >= limite:
            out["persistance_tronquee"] = True
            break
        texte = s.get("texte") or ""
        segs.append({"ref": s.get("ref", ""), "texte": texte[: limite - cumul]})
        cumul += len(texte)
    if out.get("segments"):
        out["segments"] = segs
        out["contenu"] = ""
    elif isinstance(out.get("contenu"), str):
        out["contenu"] = out["contenu"][:limite]
    return out


def transcrire_audio(fichier_audio, modele: str = "whisper-large-v3", nom: Optional[str] = None) -> str:
    """Transcrit un enregistrement audio via Groq Whisper. Retourne le texte."""
    import os
    from groq import Groq

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return ""

    nom = nom or getattr(fichier_audio, "name", "audio.wav") or "audio.wav"
    data = _lire_octets(fichier_audio)

    client = Groq(api_key=api_key, timeout=120)
    transcription = client.audio.transcriptions.create(
        file=(nom, data),
        model=modele,
        language="fr",
        response_format="text",
    )
    if isinstance(transcription, str):
        return transcription.strip()
    return str(getattr(transcription, "text", transcription) or "").strip()
