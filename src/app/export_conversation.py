"""Export de conversations AssistDoc — Markdown & PDF clairement présentés."""

from __future__ import annotations

import io
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _utc_now_label() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _titre_conversation(messages: List[Dict[str, Any]], fallback: str = "Discussion") -> str:
    for m in messages:
        if m.get("role") == "user" and (m.get("content") or "").strip():
            t = m["content"].strip().replace("\n", " ")
            return (t[:72] + "…") if len(t) > 72 else t
    return fallback


def _stats(messages: List[Dict[str, Any]]) -> Dict[str, Any]:
    n_user = sum(1 for m in messages if m.get("role") == "user")
    n_asst = sum(1 for m in messages if m.get("role") == "assistant")
    n_src = 0
    modes = set()
    for m in messages:
        if m.get("role") != "assistant":
            continue
        n_src += len(m.get("docs") or [])
        if m.get("mode"):
            modes.add(str(m["mode"]))
    return {
        "questions": n_user,
        "reponses": n_asst,
        "sources": n_src,
        "modes": sorted(modes),
    }


def _nettoyer_texte(texte: str) -> str:
    return (texte or "").strip()


def _lignes_sources(docs: List[Dict[str, Any]], limite: int = 10) -> List[str]:
    out: List[str] = []
    for i, d in enumerate(docs[:limite], 1):
        conf = d.get("score_confiance")
        conf_s = f" — confiance {conf:.0%}" if isinstance(conf, (int, float)) else ""
        repo = d.get("nom_complet") or d.get("repo") or "source"
        url = d.get("url") or ""
        section = d.get("section_titre") or ""
        src = d.get("source_file") or ""
        cite = d.get("citation_courte") or src or section or ""
        if url and str(url).startswith("http"):
            label = f"[{repo}]({url})"
            if cite:
                label += f" · `{cite}`"
            out.append(f"{i}. {label}{conf_s}")
        else:
            detail = " · ".join(x for x in (repo, cite) if x)
            out.append(f"{i}. {detail}{conf_s}")
    return out


def export_markdown(
    messages: List[Dict[str, Any]],
    *,
    conversation_id: str = "",
    titre: Optional[str] = None,
) -> str:
    """Document Markdown structuré (en-tête, échanges, sources, méta)."""
    titre_doc = titre or _titre_conversation(messages)
    stats = _stats(messages)
    cid = (conversation_id or "")[:8]

    lignes = [
        "# AssistDoc — Export de conversation",
        "",
        f"**Sujet :** {titre_doc}",
        f"**Date d'export :** {_utc_now_label()}",
    ]
    if cid:
        lignes.append(f"**Référence :** `{cid}`")
    lignes.extend(
        [
            "",
            "---",
            "",
            "## Résumé",
            "",
            f"| | |",
            f"|---|---|",
            f"| Questions | {stats['questions']} |",
            f"| Réponses | {stats['reponses']} |",
            f"| Sources citées | {stats['sources']} |",
        ]
    )
    if stats["modes"]:
        lignes.append(f"| Modes | {', '.join(stats['modes'])} |")
    lignes.extend(["", "---", "", "## Conversation", ""])

    echange = 0
    for m in messages:
        role = m.get("role")
        content = _nettoyer_texte(m.get("content") or "")
        if not content and not (m.get("docs") or []):
            continue

        if role == "user":
            echange += 1
            lignes.append(f"### {echange}. Question")
            lignes.append("")
            lignes.append(content)
            lignes.append("")
        elif role == "assistant":
            if echange == 0:
                echange = 1
            meta_bits = []
            if m.get("mode"):
                meta_bits.append(f"mode `{m['mode']}`")
            score = m.get("score_rag")
            if isinstance(score, (int, float)) and score > 0:
                meta_bits.append(f"score RAG {float(score):.0%}")
            if m.get("abstention"):
                meta_bits.append("abstention")
            lignes.append(f"### {echange}. Réponse AssistDoc")
            if meta_bits:
                lignes.append("")
                lignes.append("*" + " · ".join(meta_bits) + "*")
            lignes.append("")
            lignes.append(content)
            lignes.append("")
            docs = m.get("docs") or []
            if docs:
                lignes.append("#### Sources")
                lignes.append("")
                lignes.extend(_lignes_sources(docs))
                lignes.append("")
            lignes.append("---")
            lignes.append("")

    lignes.extend(
        [
            "",
            "## Pied de page",
            "",
            "*Généré par **AssistDoc** — assistant documentation intelligent.*",
            "",
        ]
    )
    return "\n".join(lignes)


def _fonts_candidates() -> List[Tuple[Path, Optional[Path]]]:
    """(regular, bold_or_none)."""
    return [
        (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
        (Path("C:/Windows/Fonts/segoeui.ttf"), Path("C:/Windows/Fonts/segoeuib.ttf")),
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        ),
        (Path("/System/Library/Fonts/Supplemental/Arial.ttf"), None),
    ]


def export_pdf(
    messages: List[Dict[str, Any]],
    titre: str = "AssistDoc",
    *,
    conversation_id: str = "",
) -> bytes:
    """PDF soigné : couverture, échanges numérotés, sources, pied de page."""
    try:
        from fpdf import FPDF
    except ImportError as exc:
        raise RuntimeError("fpdf2 manquant — pip install fpdf2") from exc

    titre_doc = titre if titre != "AssistDoc" else _titre_conversation(messages)
    stats = _stats(messages)
    cid = (conversation_id or "")[:8]

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(16, 16, 16)
    pdf.add_page()
    largeur = pdf.epw

    font_reg = "Helvetica"
    font_bold = "Helvetica"
    for regular, bold in _fonts_candidates():
        if regular.exists():
            pdf.add_font("ExportR", "", str(regular))
            font_reg = "ExportR"
            if bold and bold.exists():
                pdf.add_font("ExportB", "", str(bold))
                font_bold = "ExportB"
            else:
                font_bold = "ExportR"
            break

    def _text(value: str) -> str:
        text = value or ""
        if font_reg == "Helvetica":
            return text.encode("latin-1", "replace").decode("latin-1")
        return text

    def _set_font(bold: bool = False, size: int = 11) -> None:
        pdf.set_font(font_bold if bold else font_reg, size=size)

    def _ecrire(taille: int, texte: str, hauteur: float = 5.5, bold: bool = False) -> None:
        pdf.set_x(pdf.l_margin)
        _set_font(bold=bold, size=taille)
        pdf.multi_cell(largeur, hauteur, _text(texte))

    def _ligne() -> None:
        y = pdf.get_y()
        pdf.set_draw_color(200, 200, 200)
        pdf.set_line_width(0.2)
        pdf.line(pdf.l_margin, y, pdf.l_margin + largeur, y)
        pdf.ln(4)

    # ── En-tête ──
    _ecrire(16, "AssistDoc", 8, bold=True)
    _ecrire(11, "Export de conversation", 6)
    pdf.ln(2)
    _ligne()
    _ecrire(12, titre_doc, 6.5, bold=True)
    pdf.ln(1)
    _ecrire(9, f"Exporté le {_utc_now_label()}" + (f"  ·  Réf. {cid}" if cid else ""), 5)
    pdf.ln(2)
    _ecrire(
        9,
        f"Questions : {stats['questions']}   ·   "
        f"Réponses : {stats['reponses']}   ·   "
        f"Sources : {stats['sources']}",
        5,
    )
    if stats["modes"]:
        _ecrire(9, "Modes : " + ", ".join(stats["modes"]), 5)
    pdf.ln(3)
    _ligne()

    echange = 0
    for m in messages:
        role = m.get("role")
        content = _nettoyer_texte(m.get("content") or "")
        if not content and not (m.get("docs") or []):
            continue

        if role == "user":
            echange += 1
            pdf.set_fill_color(240, 244, 248)
            pdf.set_x(pdf.l_margin)
            _set_font(bold=True, size=11)
            pdf.cell(largeur, 7, _text(f"{echange}. Question"), fill=True, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
            contenu = re.sub(r"[#*`>]{1,3}", "", content)
            _ecrire(10, contenu or "(vide)", 5)
            pdf.ln(3)

        elif role == "assistant":
            if echange == 0:
                echange = 1
            pdf.set_fill_color(232, 242, 235)
            pdf.set_x(pdf.l_margin)
            _set_font(bold=True, size=11)
            label = f"{echange}. Réponse AssistDoc"
            if m.get("mode"):
                label += f"  ({m['mode']})"
            pdf.cell(largeur, 7, _text(label), fill=True, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
            contenu = re.sub(r"[#*`>]{1,3}", "", content)
            _ecrire(10, contenu or "(vide)", 5)
            docs = m.get("docs") or []
            if docs:
                pdf.ln(2)
                _ecrire(9, "Sources", 5, bold=True)
                for line in _lignes_sources(docs, limite=8):
                    # strip markdown links for PDF
                    plain = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
                    plain = plain.replace("`", "")
                    _ecrire(8, plain, 4.5)
            pdf.ln(3)
            _ligne()

    pdf.ln(2)
    _ecrire(8, "Généré par AssistDoc — assistant documentation intelligent.", 4)

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()
