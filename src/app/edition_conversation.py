"""Édition de messages de conversation (troncature de branche, resync historique)."""

from __future__ import annotations

from typing import Any, Dict, List, MutableMapping, Optional, Tuple


def resync_historique_llm(messages: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    return [
        {"role": m["role"], "content": m["content"]}
        for m in messages
        if m.get("role") in ("user", "assistant")
    ]


def appliquer_edition_contenu(
    messages: List[Dict[str, Any]], idx: int, nouveau_contenu: str
) -> Optional[List[Dict[str, Any]]]:
    """Met à jour le texte d'un message sans tronquer la suite."""
    if idx < 0 or idx >= len(messages):
        return None
    contenu = (nouveau_contenu or "").strip()
    if not contenu:
        return None
    maj = [dict(m) for m in messages]
    maj[idx] = dict(maj[idx])
    maj[idx]["content"] = contenu
    return maj


def appliquer_edition_prompt(
    messages: List[Dict[str, Any]], idx: int, nouveau_contenu: str
) -> Optional[Tuple[List[Dict[str, Any]], List[Dict[str, str]]]]:
    """Édite un prompt utilisateur et retire les messages suivants (branche obsolète).

    Retourne (messages_tronqués, historique_llm) ou None si refus.
    """
    if idx < 0 or idx >= len(messages):
        return None
    if messages[idx].get("role") != "user":
        maj = appliquer_edition_contenu(messages, idx, nouveau_contenu)
        if maj is None:
            return None
        return maj, resync_historique_llm(maj)

    contenu = (nouveau_contenu or "").strip()
    if not contenu:
        return None

    maj = [dict(m) for m in messages[: idx + 1]]
    maj[idx] = dict(maj[idx])
    maj[idx]["content"] = contenu
    # Conserver quota_decompte si déjà consommé : une régénération après Edit
    # ne doit pas recompter une requête déjà débitée pour ce tour.
    return maj, resync_historique_llm(maj)


def edition_autorisee(etat: MutableMapping[str, Any], *, figee: bool) -> bool:
    return (not figee) and (not bool(etat.get("en_cours")))
