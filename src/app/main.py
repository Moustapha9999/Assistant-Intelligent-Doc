"""
Point d'entrée Streamlit AssistDoc — navigation selon le rôle.

  streamlit run src/app/main.py

Menus :
  - Accueil : tous (invité, utilisateur, admin)
  - Admin  : uniquement si tier=admin
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

# Windows cp1252 ne gère pas les emojis des logs (🔌, ✅…)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_APP_DIR = Path(__file__).resolve().parent
_SRC = _APP_DIR.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st

import app.auth_basique as _auth_basique
from app import identite as _identite
from app import ui_composants as _ui_composants
from app import ui_theme as _ui_theme

# Évite le cache Python/Streamlit d'une ancienne version
importlib.reload(_auth_basique)
importlib.reload(_ui_theme)
importlib.reload(_ui_composants)

injecter_theme = _ui_theme.injecter_theme
afficher_notifications = _ui_composants.afficher_notifications

est_admin_session = _auth_basique.est_admin_session

# Identité validée côté serveur (session ou cookie, sinon invité unique) avant les menus,
# puis retour OAuth éventuel (rotation de session vers le compte).
_auth_basique.exiger_auth()
_identite.synchroniser_cookie()

_pages = [
    st.Page(
        str(_APP_DIR / "accueil.py"),
        title="Accueil",
        icon=":material/home:",
        default=True,
    ),
]

if est_admin_session():
    _pages.append(
        st.Page(
            str(_APP_DIR / "admin_page.py"),
            title="Admin",
            icon=":material/shield:",
        )
    )

pg = st.navigation(_pages, position="sidebar")

# Système de design commun (boutons, fenêtres, champs, notifications) puis
# notifications mises en file par l'action du run précédent.
injecter_theme()
afficher_notifications()

pg.run()
