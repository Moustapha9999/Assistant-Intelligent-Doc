"""
Nettoyage des réponses du modèle avant affichage.

Le modèle renvoie parfois des éléments qui ne sont pas destinés à l'utilisateur :
- du HTML dans le Markdown (`<br>`, `<ul><li>` dans les cellules de tableau, `<b>`…) que
  Streamlit affiche en texte brut (le HTML n'est jamais interprété : `unsafe_allow_html` est désactivé) ;
- des marqueurs de citation internes (`【ventes.csv – statistiques】`, `【3†L10-L20】`) ;
- des blocs de raisonnement `<think>…</think>` et des jetons de contrôle (`<|channel|>`…) ;
- les délimiteurs de données non fiables injectés dans le prompt (`<<<DONNEES_NON_FIABLES …>>>`).

Seule une liste fermée de balises connues est convertie en Markdown équivalent ; tout autre `<…>`
est conservé tel quel (génériques `List<T>`, comparaisons `a < b`…). Les blocs de code et le code
en ligne ne sont jamais modifiés.
"""

from __future__ import annotations

import re
from typing import List

# Le raisonnement est émis en tête de réponse ; ailleurs (blocs de code) `<think>` peut être légitime
_REFLEXION = re.compile(r"\A\s*<think>.*?</think>\s*", re.I | re.S)
_REFLEXION_OUVERTE = re.compile(r"\A\s*<think>.*\Z", re.I | re.S)
_BALISE_REFLEXION = re.compile(r"</?think>", re.I)
_JETONS_CONTROLE = re.compile(r"<\|[a-z_]{1,24}\|>", re.I)
_MARQUEURS_DONNEES = re.compile(r"<<<(?:FIN_)?DONNEES_NON_FIABLES[^\n]*?>>>[ \t]*\n?")
_CITATION_OPAQUE = re.compile(r"【\d+(?:[†:][^】]*)?】")
_CITATION = re.compile(r"[ \t]*【([^】\n]{1,160})】")

# Blocs de code clos ou ouverts en fin de texte (streaming) ; code en ligne
_BLOC_CODE = re.compile(r"(^[ \t]*(?:```|~~~).*?(?:^[ \t]*(?:```|~~~)[ \t]*$|\Z))", re.M | re.S)
_CODE_EN_LIGNE = re.compile(r"(`+)[^`\n]+?\1")

_BR = re.compile(r"\s*<br\s*/?>\s*", re.I)
_LISTES = re.compile(r"\s*</?(?:ul|ol)\s*>\s*", re.I)
_LI_OUVRANT = re.compile(r"\s*<li\s*>\s*", re.I)
_LI_FERMANT = re.compile(r"\s*</li\s*>", re.I)
_PARAGRAPHE = re.compile(r"\s*</?p\s*>\s*", re.I)
_HR = re.compile(r"<hr\s*/?>", re.I)
_GRAS = re.compile(r"<(b|strong)>(.*?)</\1>", re.I | re.S)
_ITALIQUE = re.compile(r"<(i|em)>(.*?)</\1>", re.I | re.S)
_CODE_HTML = re.compile(r"<code>(.*?)</code>", re.I | re.S)
_ENVELOPPES = re.compile(r"<(sup|sub|u|span|font|mark|small)(?:\s[^>]*)?>(.*?)</\1>", re.I | re.S)

# Fin de flux incomplète : masquée jusqu'à l'arrivée de la suite
_FIN_INCOMPLETE = re.compile(
    r"(?:【[^】\n]*|<\|[a-z_]*\|?|<<<[^\n]*|<(?:/?(?:t(?:h(?:i(?:n(?:k)?)?)?)?|br?|l(?:i)?|u(?:l)?|o(?:l)?|p|s(?:t(?:r(?:o(?:n(?:g)?)?)?)?)?|em?|i|c(?:o(?:d(?:e)?)?)?|h(?:r)?)\s*/?)?)\Z",
    re.I,
)


def _ligne_tableau(ligne: str) -> bool:
    s = ligne.strip()
    return s.startswith("|") and s.count("|") >= 2


def _br_tableau(m: re.Match) -> str:
    suite = m.string[m.end():m.end() + 1]
    return " " if suite in ("•", "-", "–", "·") else " ; "


def _html_tableau(ligne: str) -> str:
    """Une cellule de tableau ne peut pas contenir de saut de ligne : séparateurs en ligne."""
    ligne = _LISTES.sub(" ", ligne)
    ligne = _LI_OUVRANT.sub(" • ", ligne)
    ligne = _LI_FERMANT.sub("", ligne)
    ligne = _BR.sub(_br_tableau, ligne)
    ligne = _PARAGRAPHE.sub(" ", ligne)
    ligne = _HR.sub(" ", ligne)
    ligne = re.sub(r"\|\s*;\s*", "| ", ligne)
    return re.sub(r"(\S)[ \t]{2,}(?=\S)", r"\1 ", ligne)


def _html_texte(ligne: str) -> str:
    ligne = _BR.sub("  \n", ligne)
    ligne = _LISTES.sub("\n", ligne)
    ligne = _LI_OUVRANT.sub("\n- ", ligne)
    ligne = _LI_FERMANT.sub("", ligne)
    ligne = _PARAGRAPHE.sub("\n\n", ligne)
    return _HR.sub("\n\n---\n\n", ligne)


def _citation(m: re.Match) -> str:
    return f" ({m.group(1).strip()})"


def _nettoyer_prose(texte: str) -> str:
    codes: List[str] = []

    def _proteger(m: re.Match) -> str:
        codes.append(m.group(0))
        return f"\x00{len(codes) - 1}\x00"

    texte = _CODE_EN_LIGNE.sub(_proteger, texte)
    texte = _BALISE_REFLEXION.sub("", texte)
    texte = _JETONS_CONTROLE.sub("", texte)
    texte = _MARQUEURS_DONNEES.sub("", texte)
    texte = _CITATION_OPAQUE.sub("", texte)
    texte = _CITATION.sub(_citation, texte)
    texte = _GRAS.sub(r"**\2**", texte)
    texte = _ITALIQUE.sub(r"*\2*", texte)
    texte = _CODE_HTML.sub(r"`\1`", texte)
    texte = _ENVELOPPES.sub(r"\2", texte)
    texte = "\n".join(
        _html_tableau(ligne) if _ligne_tableau(ligne) else _html_texte(ligne)
        for ligne in texte.split("\n")
    )
    texte = re.sub(r"\n{3,}", "\n\n", texte)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], texte)


def nettoyer_reponse(texte: str, partiel: bool = False) -> str:
    """Texte prêt pour `st.markdown`. `partiel=True` pendant le streaming : un élément technique
    encore incomplet en fin de flux est masqué au lieu d'être affiché brièvement."""
    if not texte:
        return ""
    texte = _REFLEXION.sub("", texte)
    if partiel:
        texte = _REFLEXION_OUVERTE.sub("", texte)
    morceaux = _BLOC_CODE.split(texte)
    sortie = [m if i % 2 else _nettoyer_prose(m) for i, m in enumerate(morceaux)]
    if partiel and sortie and len(morceaux) % 2 == 1:
        sortie[-1] = _FIN_INCOMPLETE.sub("", sortie[-1])
    resultat = "".join(sortie)
    return resultat.rstrip() if partiel else resultat.strip()


REGLE_FORMAT = (
    "Format de sortie : Markdown uniquement, jamais de balises HTML (pas de <br>, <ul>, <li>, <b>…). "
    "Dans un tableau, sépare plusieurs éléments d'une même cellule par « ; ». Cite une source par son "
    "nom entre parenthèses, par exemple (ventes.csv), jamais avec des crochets 【】. Ne reproduis "
    "jamais les marqueurs <<<DONNEES_NON_FIABLES>>> ni tes réflexions internes."
)
