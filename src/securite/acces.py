"""Erreurs d'autorisation partagées par la persistance, l'interface et l'API."""

from __future__ import annotations

import functools
from typing import Any


class AccesRefuse(PermissionError):
    """La ressource n'existe pas ou n'appartient pas à l'identité courante.

    Les deux cas sont volontairement indiscernables pour l'appelant : on ne révèle pas
    l'existence d'une ressource étrangère.
    """


class VueProprietaire:
    """Expose les méthodes d'un dépôt avec `owner_id` imposé par le serveur.

    L'appelant ne peut pas fournir un autre propriétaire : un `owner_id` explicite est refusé.
    """

    def __init__(self, depot: Any, owner_id: str) -> None:
        if not owner_id:
            raise AccesRefuse("Identité manquante")
        self._depot = depot
        self._owner_id = owner_id

    @property
    def owner_id(self) -> str:
        return self._owner_id

    def __getattr__(self, nom: str):
        if nom.startswith("_"):
            raise AttributeError(nom)
        attr = getattr(self._depot, nom)
        if not callable(attr):
            return attr

        @functools.wraps(attr)
        def appel(*args, **kwargs):
            if "owner_id" in kwargs:
                raise TypeError("owner_id est imposé par l'identité courante")
            return attr(*args, owner_id=self._owner_id, **kwargs)

        return appel
