"""
Prépare l'archive du corpus pour le déploiement cloud (Streamlit Community Cloud).

tous_chunks.json (≈ 186 Mo) dépasse la limite de 100 Mo par fichier de GitHub : on le publie
comme asset de release, avec le cache BM25 pré-calculé (évite ~30 s et un pic de RAM au démarrage).
L'application le télécharge via CORPUS_URL (voir config.assurer_corpus).

Usage :
    python scripts/preparer_corpus_deploiement.py
    → deploy/corpus_assistdoc.zip + empreinte SHA-256 à copier dans CORPUS_SHA256
"""

from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import config  # noqa: E402
from retrieval.bm25 import construire_index_bm25  # noqa: E402


def main() -> None:
    chunks = Path(config.CHUNKS_FILE)
    if not chunks.exists():
        sys.exit(f"Introuvable : {chunks}")

    print("[*] Vérification / construction du cache BM25…")
    docs, index = construire_index_bm25(str(chunks))
    if index is None or index.corpus_size != len(docs):
        sys.exit("Cache BM25 invalide")

    sortie = ROOT / "deploy" / "corpus_assistdoc.zip"
    sortie.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(sortie, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for membre in config.CORPUS_MEMBRES:
            source = config.CHUNKS_DIR / membre
            if not source.exists():
                sys.exit(f"Fichier manquant : {source}")
            archive.write(source, arcname=membre)
            print(f"   + {membre} ({source.stat().st_size / 1e6:.1f} Mo)")

    h = hashlib.sha256(sortie.read_bytes()).hexdigest()
    print(f"\n[OK] {sortie} — {sortie.stat().st_size / 1e6:.1f} Mo")
    print(f"CORPUS_SHA256 = {h}")
    print(f"Chunks : {len(docs)}")


if __name__ == "__main__":
    main()
