import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import config


def test_chunks_file_est_json():
    assert str(config.CHUNKS_FILE).endswith(".json")


def test_config_qdrant_contient_seuil():
    assert "score_threshold" in config.charger_qdrant_config()["search"]


def test_taille_upload_positive():
    assert config.UPLOAD_MAX_BYTES > 0
