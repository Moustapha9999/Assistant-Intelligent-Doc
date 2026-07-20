"""
Mise à jour Qdrant rapide (sans ré-encoder 144k chunks) :
  1. (optionnel) Supprime les points DE/ES/PT/IT
  2. Ajoute les guides d'enrichissement (informatique générale)

Usage :
    python scripts/maj_qdrant_cible.py              # enrichissement seul (rapide)
    python scripts/maj_qdrant_cible.py --purge       # + purge langues
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import config  # noqa: E402
from donnees_enrichissement import ENRICHISSEMENTS  # noqa: E402

load_dotenv(ROOT / ".env")

MARKERS_DROP = re.compile(
    r"\b(und|der|die|das|mit|für|nicht|auch|werden|hierbei|"
    r"erstellen|verwenden|verzeichnis|también|aplicación|também|"
    r"aplicação|anche|applicazione)\b",
    re.I,
)


def purger_langues(client: QdrantClient, collection: str) -> None:
    print("\n→ Scan & suppression des docs DE/ES/PT/IT...")
    offset = None
    a_supprimer = []
    scanned = 0
    while True:
        points, offset = client.scroll(
            collection_name=collection,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            break
        for p in points:
            scanned += 1
            texte = (p.payload or {}).get("texte") or ""
            if MARKERS_DROP.search(texte[:1000]) and len(MARKERS_DROP.findall(texte[:1000])) >= 3:
                if texte.count("def ") + texte.count("class ") + texte.count("import ") < 2:
                    a_supprimer.append(p.id)
        if offset is None:
            break

    print(f"  Scannés: {scanned} | À supprimer: {len(a_supprimer)}")
    for i in range(0, len(a_supprimer), 100):
        client.delete(collection_name=collection, points_selector=a_supprimer[i : i + 100])
    print("  Suppression OK")


def upsert_enrichissements(client: QdrantClient, collection: str) -> None:
    print(f"\n→ Encodage de {len(ENRICHISSEMENTS)} guides d'enrichissement...")
    config.configurer_ssl()
    model = SentenceTransformer(
        config.MODELE_EMBEDDINGS,
        cache_folder=str(config.MODELS_CACHE_DIR),
    )
    textes = [e["texte"] for e in ENRICHISSEMENTS]
    vectors = model.encode(textes, convert_to_numpy=True, show_progress_bar=True)

    points = []
    for e, vec in zip(ENRICHISSEMENTS, vectors):
        # ID stable pour éviter les doublons à chaque relance
        stable_id = str(uuid.uuid5(uuid.NAMESPACE_URL, e["nom_complet"]))
        points.append(
            PointStruct(
                id=stable_id,
                vector=vec.tolist(),
                payload={
                    "texte": e["texte"],
                    "nom_complet": e["nom_complet"],
                    "langage": e["langage"],
                    "url": e["url"],
                    "section_titre": e["section_titre"],
                    "source_file": e["source_file"],
                    "source_enrichissement": True,
                },
            )
        )

    for i in range(0, len(points), 32):
        client.upsert(collection_name=collection, points=points[i : i + 32])
    print(f"  +{len(points)} enrichissements upsertés (IDs stables)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--purge",
        action="store_true",
        help="Scanner et supprimer les docs DE/ES/PT/IT (lent)",
    )
    args = parser.parse_args()

    host = os.getenv("QDRANT_HOST", "localhost")
    port = int(os.getenv("QDRANT_PORT", 6333))
    collection = os.getenv("QDRANT_COLLECTION_NAME", "github_docs")

    print("=" * 60)
    print("MAJ QDRANT — ENRICHISSEMENT INFORMATIQUE GÉNÉRALE")
    print("=" * 60)
    print(f"Guides à injecter : {len(ENRICHISSEMENTS)}")

    client = QdrantClient(host=host, port=port)
    info = client.get_collection(collection)
    print(f"Collection {collection}: {info.points_count} points")

    if args.purge:
        purger_langues(client, collection)

    upsert_enrichissements(client, collection)

    info2 = client.get_collection(collection)
    print(f"\n✅ Terminé — points dans Qdrant: {info2.points_count}")
    print("👉 Relance Streamlit pour profiter du nouveau corpus.")


if __name__ == "__main__":
    main()
