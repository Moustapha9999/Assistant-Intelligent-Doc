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

# Évite le cache Python/Streamlit d'une ancienne version du module auth
importlib.reload(_auth_basique)

assurer_session_invite = _auth_basique.assurer_session_invite
est_admin_session = _auth_basique.est_admin_session

# Session invité (ou compte déjà connecté) avant de construire les menus
assurer_session_invite()

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

# Pop-ups (st.dialog et st.toast) centrés à l'écran
st.markdown(
    """
<style>
div[data-testid="stDialog"] div:has(> div[role="dialog"]) {
    align-items: flex-start !important;
    padding: 1rem 0 !important;
}
div[data-testid="stDialog"] div[role="dialog"] {
    margin: auto !important;
}
div[data-testid="stToastContainer"] {
    top: 50% !important;
    bottom: auto !important;
    left: 50% !important;
    right: auto !important;
    transform: translate(-50%, -50%) !important;
    align-items: center !important;
}
</style>
""",
    unsafe_allow_html=True,
)

pg.run()
