"""
Comportements d'interface communs : notifications, erreurs, fenêtres de confirmation.

- Les notifications de succès sont mises en file puis affichées au run suivant : elles
  survivent au `st.rerun()` qui suit une action, et ne sont émises qu'après la réussite réelle.
- Les erreurs affichées ne contiennent jamais de trace, de requête ni de chemin interne :
  le détail technique part dans le journal `assistdoc.ui`.
- Une confirmation en attente est consommée une seule fois : un double clic ne peut pas
  exécuter deux fois une action destructive.
"""

from __future__ import annotations

import html
import logging
from typing import Any, Callable, List, MutableMapping, Optional, Tuple

journal = logging.getLogger("assistdoc.ui")

CLE_NOTIFICATIONS = "_ui_notifications"
NIVEAUX = {
    "succes": (":material/check_circle:", "short"),
    "info": (":material/info:", "short"),
    "avertissement": (":material/warning:", "long"),
    "erreur": (":material/error:", "long"),
}


def _etat(etat: Optional[MutableMapping]) -> MutableMapping:
    if etat is not None:
        return etat
    import streamlit as st

    return st.session_state


# ── Notifications ────────────────────────────────────────────────────────────


def notifier(message: str, niveau: str = "succes", *, etat: Optional[MutableMapping] = None) -> None:
    """Met une notification en file (affichée au prochain run, sans doublon)."""
    if niveau not in NIVEAUX:
        raise ValueError(niveau)
    file: List[Tuple[str, str]] = _etat(etat).setdefault(CLE_NOTIFICATIONS, [])
    if (niveau, message) not in file:
        file.append((niveau, message))


def afficher_notifications(
    *, etat: Optional[MutableMapping] = None, toast: Optional[Callable[..., Any]] = None
) -> List[Tuple[str, str]]:
    """Affiche puis vide la file (à appeler une fois par run)."""
    if toast is None:
        import streamlit as st

        toast = st.toast
    file = list(_etat(etat).pop(CLE_NOTIFICATIONS, []) or [])
    for niveau, message in file:
        icone, duree = NIVEAUX[niveau]
        toast(message, icon=icone, duration=duree)
    return file


# ── Erreurs ──────────────────────────────────────────────────────────────────


def message_erreur(message: str, exc: Optional[BaseException] = None, conseil: str = "") -> str:
    """Message affichable ; l'exception éventuelle est journalisée, jamais montrée."""
    if exc is not None:
        journal.warning("%s (%s: %s)", message, type(exc).__name__, exc, exc_info=exc)
    texte = message.strip()
    if conseil:
        texte = f"{texte} {conseil.strip()}"
    return texte


def afficher_erreur(message: str, exc: Optional[BaseException] = None, conseil: str = "") -> None:
    import streamlit as st

    st.error(message_erreur(message, exc, conseil), icon=NIVEAUX["erreur"][0])


def afficher_avertissement(message: str) -> None:
    import streamlit as st

    st.warning(message, icon=NIVEAUX["avertissement"][0])


# ── Réponses de l'assistant ──────────────────────────────────────────────────


def afficher_flux(flux, intervalle_s: float = 0.05) -> str:
    """Affiche une réponse streamée au fil de l'eau, déjà nettoyée (les éléments techniques
    incomplets en fin de flux sont masqués) ; renvoie le texte final nettoyé."""
    import time

    import streamlit as st

    from core.nettoyage_reponse import nettoyer_reponse

    zone = st.empty()
    brut, dernier = "", 0.0
    for delta in flux:
        brut += delta or ""
        if time.monotonic() - dernier >= intervalle_s:
            zone.markdown(nettoyer_reponse(brut, partiel=True))
            dernier = time.monotonic()
    final = nettoyer_reponse(brut)
    zone.markdown(final)
    return final


# ── Confirmations ────────────────────────────────────────────────────────────


def demander_confirmation(cle: str, cible: Any, *, etat: Optional[MutableMapping] = None) -> None:
    _etat(etat)[cle] = cible


def confirmation_en_attente(cle: str, *, etat: Optional[MutableMapping] = None) -> Any:
    return _etat(etat).get(cle)


def annuler_confirmation(cle: str, *, etat: Optional[MutableMapping] = None) -> None:
    _etat(etat).pop(cle, None)


def consommer_confirmation(cle: str, cible: Any, *, etat: Optional[MutableMapping] = None) -> bool:
    """True une seule fois pour la demande `cible` (la demande est retirée avant l'action)."""
    e = _etat(etat)
    if cible is None or e.get(cle) != cible:
        return False
    e.pop(cle, None)
    return True


def executer_confirmation(
    cle: str,
    cible: Any,
    action: Callable[[], bool],
    *,
    succes: str,
    echec: str,
    etat: Optional[MutableMapping] = None,
) -> Optional[bool]:
    """Exécute `action` une seule fois pour la demande `cible`.

    Retourne None si la demande n'est plus en attente (double clic), sinon le résultat.
    La notification de succès n'est émise qu'après une action réussie ; en cas d'échec ou
    d'exception, la demande est rétablie pour que l'utilisateur puisse réessayer ou annuler.
    """
    if not consommer_confirmation(cle, cible, etat=etat):
        return None
    try:
        ok = bool(action())
    except Exception as exc:  # noqa: BLE001 - message générique, détail journalisé
        message_erreur(echec, exc)
        ok = False
    if ok:
        notifier(succes, "succes", etat=etat)
    else:
        demander_confirmation(cle, cible, etat=etat)
        _etat(etat)[f"{cle}__erreur"] = echec
    return ok


def erreur_confirmation(cle: str, *, etat: Optional[MutableMapping] = None) -> str:
    """Message d'échec de la dernière tentative (lu une seule fois)."""
    return str(_etat(etat).pop(f"{cle}__erreur", "") or "")


# ── Contenu des fenêtres ─────────────────────────────────────────────────────


def html_texte_dialogue(message: str, *, nom: str = "", note: str = "") -> str:
    """Corps de fenêtre : `message` peut contenir `{nom}` (mis en évidence, échappé)."""
    corps = html.escape(message).replace("{nom}", f"<strong>{html.escape(nom)}</strong>")
    parties = [f"<p>{corps}</p>"]
    if note:
        parties.append(f'<p class="ui-note">{html.escape(note)}</p>')
    return '<div class="ui-dialog-texte">' + "".join(parties) + "</div>"


def texte_dialogue(message: str, *, nom: str = "", note: str = "") -> None:
    import streamlit as st

    st.markdown(html_texte_dialogue(message, nom=nom, note=note), unsafe_allow_html=True)


def pied_dialogue(
    cle: str,
    libelle_confirmer: str,
    *,
    danger: bool = False,
    libelle_annuler: str = "Annuler",
    desactiver: bool = False,
    icone: Optional[str] = None,
) -> Tuple[bool, bool]:
    """Pied de fenêtre standard : [Annuler] [Action] de même largeur, action à droite."""
    import streamlit as st

    gauche, droite = st.columns(2, gap="small")
    with gauche:
        annuler = st.button(libelle_annuler, key=f"{cle}_annuler", use_container_width=True)
    with droite:
        confirmer = st.button(
            libelle_confirmer,
            key=f"{'danger_' if danger else ''}{cle}_confirmer",
            type="primary",
            use_container_width=True,
            disabled=desactiver,
            icon=icone,
        )
    return annuler, confirmer
