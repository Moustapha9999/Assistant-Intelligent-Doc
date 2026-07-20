"""Administration du corpus : stats, ajout, suppression, ré-indexation."""

from __future__ import annotations

import json
import uuid
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config


def _charger_chunks(chunks_path: str | Path) -> list[dict[str, Any]]:
    chemin = Path(chunks_path)
    if not chemin.exists():
        return []
    try:
        data = json.loads(chemin.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def stats_corpus(chunks_path: str | Path | None = None) -> dict[str, Any]:
    """Retourne le nombre de chunks, dépôts et chunks par langage."""
    chunks = _charger_chunks(chunks_path or config.CHUNKS_FILE)
    par_langage = Counter((c.get("langage") or "Inconnu") for c in chunks)
    repos = {c.get("nom_complet") for c in chunks if c.get("nom_complet")}
    qdrant_info: Dict[str, Any] = {}
    try:
        from indexing.gestionnaire_qdrant import GestionnaireQdrant

        g = GestionnaireQdrant()
        info = g.client.get_collection(g.collection_name)
        qdrant_info = {
            "collection": g.collection_name,
            "points": getattr(info, "points_count", None)
            or getattr(getattr(info, "points_count", None), "count", None),
        }
        # Compat versions client
        if qdrant_info["points"] is None:
            qdrant_info["points"] = getattr(info, "points_count", "?")
    except Exception as exc:
        qdrant_info = {"erreur": str(exc)}
    return {
        "nombre_chunks": len(chunks),
        "nombre_repos": len(repos),
        "par_langage": dict(sorted(par_langage.items())),
        "qdrant": qdrant_info,
    }


def lister_repos_indexes(chunks_path: str | Path | None = None) -> list[str]:
    """Liste les dépôts présents dans le fichier de chunks."""
    return sorted(
        {
            c["nom_complet"]
            for c in _charger_chunks(chunks_path or config.CHUNKS_FILE)
            if c.get("nom_complet")
        }
    )


def lister_repos_qdrant(limite: int = 200) -> List[Dict[str, Any]]:
    """Agrège les dépôts présents dans Qdrant (scroll)."""
    from indexing.gestionnaire_qdrant import GestionnaireQdrant

    g = GestionnaireQdrant()
    compteur: Counter = Counter()
    offset = None
    scanned = 0
    while scanned < 50_000:
        points, offset = g.client.scroll(
            collection_name=g.collection_name,
            limit=256,
            offset=offset,
            with_payload=["nom_complet"],
            with_vectors=False,
        )
        if not points:
            break
        for p in points:
            scanned += 1
            repo = (p.payload or {}).get("nom_complet") or "?"
            compteur[repo] += 1
        if offset is None:
            break
    items = [
        {"nom_complet": repo, "nb_points": n}
        for repo, n in compteur.most_common(limite)
    ]
    return items


def supprimer_repo(nom_complet: str) -> Tuple[bool, str]:
    """Supprime tous les points Qdrant d'un dépôt (+ retire des chunks locaux si présents)."""
    if not nom_complet or "/" not in nom_complet:
        return False, "Nom de dépôt invalide (attendu owner/repo)."
    try:
        from indexing.gestionnaire_qdrant import GestionnaireQdrant
        from qdrant_client.http import models as qmodels

        g = GestionnaireQdrant()
        g.client.delete(
            collection_name=g.collection_name,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="nom_complet",
                            match=qmodels.MatchValue(value=nom_complet),
                        )
                    ]
                )
            ),
        )
    except Exception as exc:
        return False, f"Erreur Qdrant : {exc}"

    # Nettoyage optionnel du fichier chunks
    chunks_path = Path(config.CHUNKS_FILE)
    retires = 0
    if chunks_path.exists():
        chunks = _charger_chunks(chunks_path)
        avant = len(chunks)
        chunks = [c for c in chunks if c.get("nom_complet") != nom_complet]
        retires = avant - len(chunks)
        if retires:
            chunks_path.write_text(
                json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    return True, f"Dépôt « {nom_complet} » supprimé de Qdrant" + (
        f" ({retires} chunks locaux retirés)." if retires else "."
    )


def ajouter_document_texte(
    texte: str,
    nom_complet: str = "manuel/upload",
    source_file: str = "upload.md",
    langage: str = "Markdown",
    section_titre: str = "Document ajouté",
) -> Tuple[bool, str]:
    """Chunk + embed + upsert immédiat d'un document texte dans Qdrant."""
    texte = (texte or "").strip()
    if len(texte) < 40:
        return False, "Texte trop court (min. 40 caractères)."
    try:
        from data_preprocessing.decoupeur import chunker_markdown
        from indexing.gestionnaire_qdrant import GestionnaireQdrant
        from sentence_transformers import SentenceTransformer
        from qdrant_client.models import PointStruct

        meta = {
            "nom_complet": nom_complet,
            "chemin_fichier": source_file,
            "langage": langage,
            "url": "",
        }
        # chunker_markdown attend (texte, meta) selon le découpeur
        try:
            chunks = chunker_markdown(texte, meta)
        except TypeError:
            # Fallback découpage simple
            mots = texte.split()
            chunks = []
            for i in range(0, max(1, len(mots)), 400):
                bloc = " ".join(mots[i : i + 450])
                if len(bloc.split()) < 20:
                    continue
                chunks.append(
                    {
                        "texte": bloc,
                        "section_titre": section_titre,
                        "type_chunk": "markdown",
                        **meta,
                    }
                )
        if not chunks:
            chunks = [
                {
                    "texte": texte[:4000],
                    "section_titre": section_titre,
                    "type_chunk": "markdown",
                    **meta,
                }
            ]

        config.configurer_ssl()
        model = SentenceTransformer(
            config.MODELE_EMBEDDINGS, cache_folder=str(config.MODELS_CACHE_DIR)
        )
        vecteurs = model.encode(
            [c["texte"] for c in chunks], convert_to_numpy=True, show_progress_bar=False
        )
        g = GestionnaireQdrant()
        g.creer_collection(dimension=int(vecteurs.shape[1]), recreer=False)
        points = []
        for chunk, vec in zip(chunks, vecteurs):
            points.append(
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vec.tolist(),
                    payload=g._extraire_payload(chunk),
                )
            )
        g.client.upsert(collection_name=g.collection_name, points=points)

        # Append chunks locaux
        chunks_path = Path(config.CHUNKS_FILE)
        existants = _charger_chunks(chunks_path)
        existants.extend(chunks)
        chunks_path.parent.mkdir(parents=True, exist_ok=True)
        chunks_path.write_text(
            json.dumps(existants, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True, f"{len(points)} chunk(s) indexé(s) pour « {nom_complet} »."
    except Exception as exc:
        return False, f"Échec indexation : {exc}"


def reindexer_collection(recreer: bool = False) -> Tuple[bool, str]:
    """Relance l'indexation depuis le fichier d'embeddings existant."""
    emb = Path(config.EMBEDDINGS_FILE)
    if not emb.exists():
        return (
            False,
            f"Fichier embeddings introuvable ({emb}). "
            "Lancez d'abord : python scripts/indexer_corpus.py",
        )
    try:
        from indexing.gestionnaire_qdrant import GestionnaireQdrant

        g = GestionnaireQdrant()
        g.indexer_chunks(fichier_embeddings=emb, recreer=recreer)
        return True, f"Ré-indexation terminée (recreer={recreer})."
    except Exception as exc:
        return False, f"Échec ré-indexation : {exc}"
