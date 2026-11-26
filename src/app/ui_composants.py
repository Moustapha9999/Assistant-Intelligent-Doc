"""
Comportements d'interface communs : notifications, erreurs, fenêtres de confirmation.

- Les notifications de succès sont mises en file puis affichées au run suivant : elles
  survivent au `st.rerun()` qui suit une action, et ne sont émises qu'après la réussite réelle.
- Les erreurs affichées ne contiennent jamais de trace, de requête ni de chemin interne :
  le détail technique part dans le journal `assistdoc.ui`.
- Une confirmation en attente est consommée une seule fois : un double clic ne peut pas
  exécuter deux fois une action destructive.
- Les notifications UI sont injectées dans document.body du parent (viewport) pour un
  centrage réel et une fermeture immédiate, hors des contextes transform de Streamlit.
"""

from __future__ import annotations

import html
import json
import logging
from typing import Any, Callable, List, MutableMapping, Optional, Tuple

journal = logging.getLogger("assistdoc.ui")

CLE_NOTIFICATIONS = "_ui_notifications"
NIVEAUX = {
    # icône material, durée toast, accent carte, glyphe
    "succes": (":material/check_circle:", "short", "#4fae7f", "✓"),
    "info": (":material/info:", "short", "#5b9fd4", "ℹ"),
    "avertissement": (":material/warning:", "long", "#d6a243", "!"),
    "erreur": (":material/error:", "long", "#c94a4a", "✕"),
}
DUREES_MS = {"short": 3200, "long": 5200}


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


def _injecter_notifications_viewport(file: List[Tuple[str, str]]) -> None:
    """Cartes centrées dans le viewport du document parent + fermeture immédiate."""
    import streamlit.components.v1 as components

    items = []
    for niveau, message in file:
        _icone, duree_cle, accent, glyphe = NIVEAUX[niveau]
        items.append(
            {
                "message": message,
                "accent": accent,
                "glyphe": glyphe,
                "duree": DUREES_MS.get(duree_cle, 3200),
            }
        )
    payload = json.dumps(items, ensure_ascii=False)
    components.html(
        f"""
<script>
(function () {{
  const win = window.parent;
  const doc = win.document;
  const items = {payload};

  // Style singleton (v3) : centrage viewport réel, indépendant sidebar/composer
  const STYLE_ID = 'assist-notif-style-v3';
  let style = doc.getElementById(STYLE_ID);
  if (!style) {{
    // Retirer les anciennes feuilles pour éviter les conflits de position
    ['assist-notif-style-v2', 'assist-notif-style'].forEach(function (id) {{
      const old = doc.getElementById(id);
      if (old) old.remove();
    }});
    style = doc.createElement('style');
    style.id = STYLE_ID;
    style.textContent = `
      #assist-notif-host {{
        position: fixed !important;
        inset: 0 !important;
        top: 0 !important; left: 0 !important; right: 0 !important; bottom: 0 !important;
        width: 100vw !important; height: 100dvh !important;
        max-width: 100vw !important; max-height: 100dvh !important;
        margin: 0 !important; padding: 12px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        pointer-events: none !important;
        z-index: 2147483646 !important;
        transform: none !important;
        filter: none !important;
        perspective: none !important;
        contain: none !important;
        box-sizing: border-box !important;
      }}
      #assist-notif-host .assist-notif-stack {{
        display: flex; flex-direction: column; gap: 8px;
        max-width: min(380px, 92vw); width: 100%;
        pointer-events: none;
        transform: none !important;
        margin: 0 !important;
      }}
      #assist-notif-host .assist-notif {{
        pointer-events: auto;
        display: flex; align-items: flex-start; gap: 10px;
        padding: 11px 12px; border-radius: 12px; background: #0d0d0d;
        border: 1px solid rgba(255,255,255,.14);
        border-left: 3px solid var(--assist-notif-accent, #5b9fd4);
        box-shadow: 0 16px 40px rgba(0,0,0,.55); color: #f5f4ef;
        font-family: Inter, system-ui, sans-serif; font-size: 14px; line-height: 1.4;
        animation: assistNotifInV3 .1s ease-out;
        will-change: opacity;
      }}
      #assist-notif-host .assist-notif.assist-notif-out {{
        opacity: 0 !important;
        transition: opacity .06s linear !important;
        animation: none !important;
        pointer-events: none !important;
      }}
      #assist-notif-host .assist-notif-icon {{
        flex: 0 0 26px; width: 26px; height: 26px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        background: color-mix(in srgb, var(--assist-notif-accent) 22%, transparent);
        color: var(--assist-notif-accent); font-weight: 700; font-size: 13px;
      }}
      #assist-notif-host .assist-notif-body {{ flex: 1 1 auto; padding-top: 2px; }}
      #assist-notif-host .assist-notif-close {{
        border: none; background: transparent; color: #9a978c; cursor: pointer;
        font-size: 22px; line-height: 1; padding: 0;
        min-width: 36px; min-height: 36px;
        display: inline-flex; align-items: center; justify-content: center;
        border-radius: 8px; touch-action: manipulation; -webkit-tap-highlight-color: transparent;
        flex: 0 0 36px;
      }}
      #assist-notif-host .assist-notif-close:hover,
      #assist-notif-host .assist-notif-close:focus-visible {{
        color: #f5f4ef; background: rgba(255,255,255,.08); outline: none;
      }}
      @keyframes assistNotifInV3 {{
        from {{ opacity: 0; }}
        to {{ opacity: 1; }}
      }}
      div[data-testid="stToastContainer"],
      [data-testid="stToastContainer"] {{
        top: 50% !important; left: 50% !important; right: auto !important; bottom: auto !important;
        transform: translate(-50%, -50%) !important; width: min(380px, 92vw) !important;
      }}
    `;
    doc.head.appendChild(style);
  }}

  // Monter sur <html> : évite les containing blocks (transform/filter) sur body/app
  function assurerHost() {{
    let host = doc.getElementById('assist-notif-host');
    if (!host) {{
      host = doc.createElement('div');
      host.id = 'assist-notif-host';
      host.setAttribute('aria-live', 'polite');
    }}
    const ancre = doc.documentElement || doc.body;
    if (host.parentNode !== ancre) {{
      ancre.appendChild(host);
    }}
    let stack = host.querySelector('.assist-notif-stack');
    if (!stack) {{
      stack = doc.createElement('div');
      stack.className = 'assist-notif-stack';
      host.appendChild(stack);
    }}
    return {{ host: host, stack: stack }};
  }}

  const ctx = assurerHost();
  const stack = ctx.stack;

  function fermerImmediat(el) {{
    if (!el || el._assistClosed) return;
    el._assistClosed = true;
    if (el._assistTimer) {{
      try {{ clearTimeout(el._assistTimer); }} catch (e) {{}}
      el._assistTimer = null;
    }}
    // Masquage immédiat puis retrait DOM (transition 60 ms max, non bloquante)
    try {{ el.classList.add('assist-notif-out'); }} catch (e) {{}}
    try {{
      if (el.parentNode) el.parentNode.removeChild(el);
    }} catch (e) {{
      try {{ el.style.display = 'none'; }} catch (e2) {{}}
    }}
  }}

  function echapper(s) {{
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }}

  items.forEach(function (it) {{
    const fingerprint = (it.glyphe || '') + '|' + (it.message || '');
    // Anti-doublon DOM : même message déjà visible → ne pas empiler
    const deja = Array.prototype.slice.call(stack.children).some(function (n) {{
      return n._assistFp === fingerprint && !n._assistClosed;
    }});
    if (deja) return;

    const el = doc.createElement('div');
    el.className = 'assist-notif';
    el.setAttribute('role', 'status');
    el._assistFp = fingerprint;
    el.style.setProperty('--assist-notif-accent', it.accent || '#5b9fd4');
    el.innerHTML =
      '<div class="assist-notif-icon" aria-hidden="true">' + echapper(it.glyphe || 'ℹ') + '</div>' +
      '<div class="assist-notif-body">' + echapper(it.message || '') + '</div>' +
      '<button type="button" class="assist-notif-close" aria-label="Fermer" title="Fermer">×</button>';
    const btn = el.querySelector('.assist-notif-close');
    function onClose(ev) {{
      if (ev) {{
        try {{ ev.preventDefault(); }} catch (e) {{}}
        try {{ ev.stopPropagation(); }} catch (e) {{}}
        try {{ ev.stopImmediatePropagation(); }} catch (e) {{}}
      }}
      fermerImmediat(el);
    }}
    // pointerdown capture + once : fermeture au premier contact, sans attendre click/rerun
    btn.addEventListener('pointerdown', onClose, {{ capture: true, once: true, passive: false }});
    btn.addEventListener('click', onClose, {{ capture: true, once: true }});
    stack.appendChild(el);
    el._assistTimer = setTimeout(function () {{ fermerImmediat(el); }}, it.duree || 3200);
  }});
}})();
</script>
        """,
        height=0,
        width=0,
    )


def afficher_notifications(
    *, etat: Optional[MutableMapping] = None, toast: Optional[Callable[..., Any]] = None
) -> List[Tuple[str, str]]:
    """Affiche puis vide la file (cartes viewport ; toast callback pour les tests)."""
    import streamlit as st

    file = list(_etat(etat).pop(CLE_NOTIFICATIONS, []) or [])
    if not file:
        return file

    if toast is not None:
        for niveau, message in file:
            icone, duree = NIVEAUX[niveau][0], NIVEAUX[niveau][1]
            toast(message, icon=icone, duration=duree)
        return file

    _injecter_notifications_viewport(file)
    # Marqueur AppTest / accessibilité (hors écran)
    msgs = " · ".join(html.escape(m) for _, m in file)
    st.markdown(
        f'<div class="assist-notif" data-assist-notif="1" hidden aria-hidden="true">{msgs}</div>',
        unsafe_allow_html=True,
    )
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


def afficher_flux(flux, intervalle_s: float = 0.05, *, zone=None) -> str:
    """Affiche une réponse streamée au fil de l'eau, déjà nettoyée (les éléments techniques
    incomplets en fin de flux sont masqués) ; renvoie le texte final nettoyé.

    `zone` : st.empty() existant (fil de conversation) ; sinon une zone locale est créée.
    """
    import time

    import streamlit as st

    from core.nettoyage_reponse import nettoyer_reponse

    cible = zone if zone is not None else st.empty()
    brut, dernier = "", 0.0
    for delta in flux:
        brut += delta or ""
        if time.monotonic() - dernier >= intervalle_s:
            cible.markdown(nettoyer_reponse(brut, partiel=True))
            dernier = time.monotonic()
    final = nettoyer_reponse(brut)
    cible.markdown(final)
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
