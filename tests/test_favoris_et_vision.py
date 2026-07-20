import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.favoris_sqlite import FavorisSQLite
from app.gestionnaire_fichiers import formater_pour_prompt
from app.admin_corpus import stats_corpus, lister_repos_indexes


def test_favoris_collections_et_docs(tmp_path):
    fav = FavorisSQLite(tmp_path / "favoris.db")
    cid = fav.creer_collection("API")
    fid = fav.ajouter_favori(
        {
            "nom_complet": "tiangolo/fastapi",
            "source_file": "docs/tutorial.md",
            "section_titre": "First steps",
            "url": "https://github.com/tiangolo/fastapi",
            "citation_courte": "[docs/tutorial.md § First steps]",
            "texte": "Create an API with FastAPI",
            "score_confiance": 0.9,
        },
        collection_id=cid,
    )
    assert fid
    assert fav.est_deja_favori("tiangolo/fastapi", "docs/tutorial.md", "First steps")
    liste = fav.lister_favoris(cid)
    assert len(liste) == 1
    assert liste[0]["nom_complet"] == "tiangolo/fastapi"
    assert fav.supprimer_favori(fid) is True
    assert fav.lister_favoris(cid) == []


def test_formater_image_avec_vision():
    fichiers = [
        {
            "nom": "err.png",
            "type": "image",
            "langage": "texte",
            "contenu": "Traceback visible dans une console Python",
            "vision_ok": True,
            "image_b64": "abc",
        }
    ]
    txt = formater_pour_prompt(fichiers)
    assert "Image analysée" in txt
    assert "Traceback" in txt


def test_formater_image_placeholder():
    fichiers = [
        {
            "nom": "shot.png",
            "type": "image",
            "langage": "texte",
            "contenu": "[Image : shot.png]",
            "vision_ok": False,
        }
    ]
    txt = formater_pour_prompt(fichiers)
    assert "analyse visuelle en attente" in txt


def test_stats_corpus_ne_plante_pas():
    # Peut renvoyer 0 chunks si data absente — ne doit pas lever
    stats = stats_corpus()
    assert "nombre_chunks" in stats
    assert isinstance(lister_repos_indexes(), list)


def test_est_admin_reserve():
    from securite.identifiants import est_admin

    assert est_admin("admin") is True
    assert est_admin("alice") is False
    assert est_admin("") is False
    assert est_admin(None) is False
