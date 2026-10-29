import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture(autouse=True)
def _isoler_etat_partage(tmp_path, monkeypatch):
    """Aucun test n'écrit dans data/app : paramètres Admin et journal de l'API en dossier temporaire."""
    from app import runtime_config

    monkeypatch.setattr(runtime_config, "RUNTIME_FILE", tmp_path / "runtime_ia.json")
    try:
        import api.auth as api_auth
    except ImportError:
        return
    from app.utilisateurs_sqlite import UtilisateursSQLite

    journal = []

    def _journal():
        if not journal:
            journal.append(UtilisateursSQLite(tmp_path / "journal_api.db"))
        return journal[0]

    monkeypatch.setattr(api_auth, "_journal", _journal)
    api_auth.LIMITEUR._appels.clear()
