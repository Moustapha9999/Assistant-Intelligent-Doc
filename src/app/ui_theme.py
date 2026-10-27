"""
Système de design AssistDoc : jetons et styles communs à toutes les pages Streamlit.

Injecté une fois par run depuis `main.py` (avant la page). Les pages ne redéfinissent pas
les boutons, fenêtres, champs, alertes ni notifications : elles ne stylent que leur mise en page.

Variantes de boutons :
- principal   : `type="primary"`
- secondaire  : type par défaut
- discret     : `type="tertiary"`
- danger      : clé préfixée par `danger_` (action destructive) ; plein si `type="primary"`
                (confirmation finale), contour sinon, texte rouge si `type="tertiary"`
- icône       : clé préfixée par `icone_` (carré compact)

Les sélecteurs s'appuient sur les attributs publics de Streamlit (`data-testid="stBaseButton-*"`,
classes `st-key-<clé>`), pas sur la structure interne des balises.
"""

from __future__ import annotations

JETONS = {
    # Couleurs
    "--ui-accent": "#5b9fd4",
    "--ui-accent-hover": "#74b1e0",
    "--ui-on-accent": "#0e1620",
    "--ui-danger": "#c94a4a",
    "--ui-danger-hover": "#d65c5c",
    "--ui-success": "#4fae7f",
    "--ui-warning": "#d6a243",
    "--ui-surface": "#2a2a28",
    "--ui-surface-2": "#323230",
    "--ui-control": "rgba(255,255,255,0.06)",
    "--ui-control-hover": "rgba(255,255,255,0.10)",
    "--ui-border": "rgba(255,255,255,0.12)",
    "--ui-border-strong": "rgba(255,255,255,0.22)",
    "--ui-text": "#f5f4ef",
    "--ui-text-muted": "#b8b6ad",
    "--ui-focus": "#8cc4ee",
    # Typographie
    "--ui-font": "'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif",
    "--ui-fs-sm": "13px",
    "--ui-fs": "14px",
    "--ui-fs-body": "15px",
    "--ui-fs-title": "18px",
    # Espacements
    "--ui-space-1": "4px",
    "--ui-space-2": "8px",
    "--ui-space-3": "12px",
    "--ui-space-4": "16px",
    "--ui-space-5": "24px",
    # Dimensions
    "--ui-btn-h": "40px",
    "--ui-btn-h-sm": "34px",
    "--ui-icon-btn": "32px",
    "--ui-radius-sm": "8px",
    "--ui-radius": "10px",
    "--ui-radius-lg": "16px",
}

_RACINE = ":root {\n" + "\n".join(f"    {k}: {v};" for k, v in JETONS.items()) + "\n}"

CSS_COMPOSANTS = """
/* ── Boutons : base commune ───────────────────────────────────────────── */
.stButton button,
.stFormSubmitButton button,
.stDownloadButton button,
.stLinkButton > a {
    min-height: var(--ui-btn-h);
    padding: 0 var(--ui-space-4);
    border-radius: var(--ui-radius);
    font-family: var(--ui-font);
    font-size: var(--ui-fs);
    font-weight: 500;
    line-height: 1.2;
    justify-content: center;
    text-align: center;
    gap: var(--ui-space-2);
    transition: background-color .12s ease, border-color .12s ease, color .12s ease;
}
.stButton button p,
.stFormSubmitButton button p,
.stDownloadButton button p { font-size: inherit; }

/* Principal */
button[data-testid="stBaseButton-primary"],
button[data-testid="stBaseButton-primaryFormSubmit"],
a[data-testid="stBaseLinkButton-primary"] {
    background: var(--ui-accent);
    border: 1px solid var(--ui-accent);
    color: var(--ui-on-accent);
    font-weight: 600;
}
button[data-testid="stBaseButton-primary"]:hover,
button[data-testid="stBaseButton-primaryFormSubmit"]:hover,
a[data-testid="stBaseLinkButton-primary"]:hover {
    background: var(--ui-accent-hover);
    border-color: var(--ui-accent-hover);
    color: var(--ui-on-accent);
}

/* Secondaire */
button[data-testid="stBaseButton-secondary"],
button[data-testid="stBaseButton-secondaryFormSubmit"],
a[data-testid="stBaseLinkButton-secondary"] {
    background: var(--ui-control);
    border: 1px solid var(--ui-border);
    color: var(--ui-text);
}
button[data-testid="stBaseButton-secondary"]:hover,
button[data-testid="stBaseButton-secondaryFormSubmit"]:hover,
a[data-testid="stBaseLinkButton-secondary"]:hover {
    background: var(--ui-control-hover);
    border-color: var(--ui-border-strong);
    color: var(--ui-text);
}

/* Discret */
button[data-testid="stBaseButton-tertiary"] {
    background: transparent;
    border: 1px solid transparent;
    color: var(--ui-text-muted);
    min-height: var(--ui-btn-h-sm);
    padding: 0 var(--ui-space-2);
}
button[data-testid="stBaseButton-tertiary"]:hover {
    background: var(--ui-control);
    color: var(--ui-text);
}

/* Danger (clé « danger_… ») */
div[class*="st-key-danger_"] button {
    background: var(--ui-danger);
    border: 1px solid var(--ui-danger);
    color: #fff;
    font-weight: 600;
}
div[class*="st-key-danger_"] button:hover {
    background: var(--ui-danger-hover);
    border-color: var(--ui-danger-hover);
    color: #fff;
}
div[class*="st-key-danger_"] button[data-testid="stBaseButton-secondary"] {
    background: transparent;
    border-color: rgba(201,74,74,0.55);
    color: #ec8b8b;
    font-weight: 500;
}
div[class*="st-key-danger_"] button[data-testid="stBaseButton-secondary"]:hover {
    background: rgba(201,74,74,0.14);
    border-color: var(--ui-danger);
    color: #f3a3a3;
}
div[class*="st-key-danger_"] button[data-testid="stBaseButton-tertiary"] {
    background: transparent;
    border-color: transparent;
    color: #ec8b8b;
}
div[class*="st-key-danger_"] button[data-testid="stBaseButton-tertiary"]:hover {
    background: rgba(201,74,74,0.14);
    color: #f3a3a3;
}

/* Icône (clé « icone_… ») */
div[class*="st-key-icone_"] button {
    width: var(--ui-icon-btn);
    min-width: var(--ui-icon-btn);
    height: var(--ui-icon-btn);
    min-height: var(--ui-icon-btn);
    padding: 0;
    border-radius: var(--ui-radius-sm);
}

/* États communs */
.stButton button:focus-visible,
.stFormSubmitButton button:focus-visible,
.stDownloadButton button:focus-visible,
.stLinkButton > a:focus-visible,
[data-testid="stPopover"] button:focus-visible {
    outline: 2px solid var(--ui-focus);
    outline-offset: 2px;
    box-shadow: none;
}
.stButton button:active:not(:disabled),
.stFormSubmitButton button:active:not(:disabled) { transform: translateY(1px); }
.stButton button:disabled,
.stFormSubmitButton button:disabled,
.stDownloadButton button:disabled {
    opacity: .5;
    cursor: not-allowed;
}
.stButton button [data-testid="stIconMaterial"],
.stFormSubmitButton button [data-testid="stIconMaterial"] { font-size: 18px; }

/* ── Fenêtres modales (largeur : paramètre natif small / medium / large) ── */
div[data-testid="stDialog"] div:has(> div[role="dialog"]) {
    align-items: flex-start;
    padding: var(--ui-space-4) 0;
}
div[data-testid="stDialog"] div[role="dialog"] {
    margin: auto;
    background: var(--ui-surface);
    border: 1px solid var(--ui-border);
    border-radius: var(--ui-radius-lg);
    max-width: calc(100vw - 32px);
    max-height: calc(100vh - 32px);
    overflow-y: auto;
    box-shadow: 0 24px 64px rgba(0,0,0,0.5);
}
div[data-testid="stDialog"] div[role="dialog"] h2 {
    font-family: var(--ui-font);
    font-size: var(--ui-fs-title);
    font-weight: 600;
    line-height: 1.35;
    color: var(--ui-text);
    text-align: left;
    margin: 0;
    padding-right: var(--ui-space-5);
}
.ui-dialog-texte { margin: 0 0 var(--ui-space-4); }
.ui-dialog-texte p {
    margin: 0 0 var(--ui-space-2);
    font-size: var(--ui-fs-body);
    line-height: 1.55;
    color: var(--ui-text);
    overflow-wrap: anywhere;
}
.ui-dialog-texte p:last-child { margin-bottom: 0; }
.ui-dialog-texte strong { font-weight: 600; color: #fff; }
.ui-dialog-texte .ui-note {
    font-size: var(--ui-fs-sm);
    color: var(--ui-text-muted);
}

/* ── Champs et formulaires ────────────────────────────────────────────── */
[data-testid="stForm"] {
    border: 1px solid var(--ui-border);
    border-radius: var(--ui-radius-lg);
    padding: var(--ui-space-4);
}
[data-testid="stDialog"] [data-testid="stForm"] { border: none; padding: 0; }
.stTextInput label, .stTextArea label, .stNumberInput label,
.stSelectbox label, .stSlider label {
    font-size: var(--ui-fs-sm);
    font-weight: 500;
    color: var(--ui-text-muted);
}
.stTextInput [data-baseweb="input"],
.stNumberInput [data-baseweb="input"],
.stTextArea [data-baseweb="textarea"] {
    border-radius: var(--ui-radius);
}
.stTextInput input, .stTextArea textarea, .stNumberInput input {
    font-size: var(--ui-fs);
}

/* ── Alertes et notifications ─────────────────────────────────────────── */
div[data-testid="stAlert"] > div {
    border-radius: var(--ui-radius);
    font-size: var(--ui-fs);
    line-height: 1.5;
}
div[data-testid="stToastContainer"] {
    top: 50%;
    bottom: auto;
    left: 50%;
    right: auto;
    transform: translate(-50%, -50%);
    align-items: center;
}
div[data-testid="stToast"] {
    background: var(--ui-surface-2);
    border: 1px solid var(--ui-border);
    border-radius: var(--ui-radius);
    color: var(--ui-text);
    font-size: var(--ui-fs);
    box-shadow: 0 12px 32px rgba(0,0,0,0.45);
}

/* ── Menus contextuels (popovers) ─────────────────────────────────────── */
[data-testid="stPopoverBody"] {
    background: var(--ui-surface-2);
    border: 1px solid var(--ui-border);
    border-radius: var(--ui-radius);
    box-shadow: 0 12px 32px rgba(0,0,0,0.45);
}
"""


# Chrome Streamlit : !important nécessaire pour passer devant les styles Emotion.
# Conservé hors de CSS_COMPOSANTS pour que le thème reste sans surcharge globale.
CSS_CHROME = """
header[data-testid="stHeader"] {
    background: transparent !important;
    height: 0 !important;
    min-height: 0 !important;
    overflow: visible !important;
}
[data-testid="stToolbarActions"],
[data-testid="stAppDeployButton"],
[data-testid="stMainMenu"],
[data-testid="stHeaderLogo"],
[data-testid="stDecoration"],
#MainMenu, footer { display: none !important; }
[data-testid="stExpandSidebarButton"] {
    position: fixed !important;
    top: 10px !important;
    left: 10px !important;
    z-index: 1000000 !important;
    background: var(--ui-surface-2) !important;
    border: 1px solid var(--ui-border) !important;
    border-radius: var(--ui-radius-sm) !important;
    color: var(--ui-text) !important;
}
"""


def css_theme() -> str:
    return "<style>\n" + _RACINE + "\n" + CSS_COMPOSANTS + "\n" + CSS_CHROME + "\n</style>"


def injecter_theme() -> None:
    import streamlit as st

    st.markdown(css_theme(), unsafe_allow_html=True)
