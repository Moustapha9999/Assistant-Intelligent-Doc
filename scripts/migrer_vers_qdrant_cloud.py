"""
Copie la collection Qdrant locale vers Qdrant Cloud (vecteurs + payloads + index de payload).

La base locale n'est jamais modifiée (lecture seule : scroll).
Les identifiants cible se lisent dans .env (jamais affichés) :
    QDRANT_CLOUD_URL=https://xxxx.cloud.qdrant.io:6333
    QDRANT_CLOUD_API_KEY=...

Usage :
    python scripts/migrer_vers_qdrant_cloud.py --dry-run     # vérifie source + cible, ne copie rien
    python scripts/migrer_vers_qdrant_cloud.py               # copie (reprend là où elle s'est arrêtée)
    python scripts/migrer_vers_qdrant_cloud.py --recreer     # supprime puis recrée la collection CIBLE
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from qdrant_client import QdrantClient, models  # noqa: E402

POINT_CONTROLE = ROOT / "logs" / "migration_qdrant_cloud.json"


def _client_source(args) -> QdrantClient:
    return QdrantClient(host=args.source_host, port=args.source_port, timeout=60)


def _client_cible() -> QdrantClient:
    url = os.getenv("QDRANT_CLOUD_URL", "").strip()
    cle = os.getenv("QDRANT_CLOUD_API_KEY", "").strip()
    if not url or not cle:
        sys.exit("QDRANT_CLOUD_URL et QDRANT_CLOUD_API_KEY doivent être définis dans .env")
    if "localhost" in url or "127.0.0.1" in url:
        sys.exit("QDRANT_CLOUD_URL pointe vers la machine locale : refusé")
    return QdrantClient(url=url, api_key=cle, timeout=120)


def _schema_vers_type(info) -> models.PayloadSchemaType:
    return models.PayloadSchemaType(info.data_type.value if hasattr(info.data_type, "value") else info.data_type)


def _creer_collection(cible: QdrantClient, nom: str, info_source) -> None:
    params = info_source.config.params
    cible.create_collection(
        collection_name=nom,
        vectors_config=params.vectors,
        on_disk_payload=True,
        optimizers_config=models.OptimizersConfigDiff(indexing_threshold=0),
    )
    for champ, schema in (info_source.payload_schema or {}).items():
        cible.create_payload_index(nom, field_name=champ, field_schema=_schema_vers_type(schema))
    print(f"[+] Collection cible '{nom}' créée ({len(info_source.payload_schema or {})} index de payload)")


def _lire_point_controle(nom: str):
    if POINT_CONTROLE.exists():
        data = json.loads(POINT_CONTROLE.read_text(encoding="utf-8"))
        if data.get("collection") == nom:
            return data.get("offset"), int(data.get("copies", 0))
    return None, 0


def _ecrire_point_controle(nom: str, offset, copies: int) -> None:
    POINT_CONTROLE.parent.mkdir(exist_ok=True)
    POINT_CONTROLE.write_text(
        json.dumps({"collection": nom, "offset": offset, "copies": copies}), encoding="utf-8"
    )


def _upsert_avec_reprise(cible: QdrantClient, nom: str, points, essais: int = 5) -> None:
    for i in range(essais):
        try:
            cible.upsert(collection_name=nom, points=points, wait=True)
            return
        except Exception as e:  # réseau / 5xx : on réessaie avec back-off
            if i == essais - 1:
                raise
            attente = 2 ** i
            print(f"   ! upsert échoué ({type(e).__name__}), nouvel essai dans {attente}s")
            time.sleep(attente)


def _comparer_recherches(source: QdrantClient, cible: QdrantClient, nom: str, n: int = 5) -> bool:
    echantillon, _ = source.scroll(nom, limit=n, with_vectors=True, with_payload=False)
    ok = True
    for p in echantillon:
        a = source.query_points(nom, query=p.vector, limit=5).points
        b = cible.query_points(nom, query=p.vector, limit=5).points
        ids_a, ids_b = [x.id for x in a], [x.id for x in b]
        meme = ids_a[0] == ids_b[0] and len(set(ids_a) & set(ids_b)) >= 4
        ok &= meme
        print(f"   {'OK ' if meme else 'DIFF'} point {p.id} : top-5 commun = {len(set(ids_a) & set(ids_b))}/5")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--collection", default=os.getenv("QDRANT_COLLECTION_NAME", "github_docs"))
    ap.add_argument("--source-host", default="localhost")
    ap.add_argument("--source-port", type=int, default=6333)
    ap.add_argument("--lot", type=int, default=256, help="points par upsert")
    ap.add_argument("--recreer", action="store_true", help="supprime puis recrée la collection CIBLE")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    nom = args.collection

    source = _client_source(args)
    info = source.get_collection(nom)
    total = info.points_count
    print(f"[source] {args.source_host}:{args.source_port}/{nom} — {total} points, vecteurs {info.config.params.vectors}")

    cible = _client_cible()
    existe = cible.collection_exists(nom)
    print(f"[cible ] Qdrant Cloud joignable — collection '{nom}' {'existe' if existe else 'absente'}")

    if args.dry_run:
        print("[dry-run] aucune écriture.")
        return

    if existe and args.recreer:
        cible.delete_collection(nom)
        POINT_CONTROLE.unlink(missing_ok=True)
        existe = False
        print(f"[-] Collection cible '{nom}' supprimée (--recreer)")

    offset, copies = _lire_point_controle(nom)
    if not existe:
        _creer_collection(cible, nom, info)
        offset, copies = None, 0
    elif offset is None and copies == 0:
        sys.exit(f"La collection cible '{nom}' existe déjà sans point de contrôle : relancez avec --recreer")
    else:
        print(f"[~] Reprise après {copies} points")

    debut = time.time()
    while True:
        points, suivant = source.scroll(
            nom, limit=args.lot, offset=offset, with_payload=True, with_vectors=True
        )
        if not points:
            break
        _upsert_avec_reprise(
            cible,
            nom,
            [models.PointStruct(id=p.id, vector=p.vector, payload=p.payload) for p in points],
        )
        copies += len(points)
        offset = suivant
        _ecrire_point_controle(nom, offset, copies)
        debit = copies / max(time.time() - debut, 1e-6)
        print(f"\r   {copies}/{total} points ({debit:.0f} pts/s)", end="", flush=True)
        if suivant is None:
            break
    print()

    cible.update_collection(nom, optimizers_config=models.OptimizersConfigDiff(indexing_threshold=20000))
    print("[*] Indexation HNSW réactivée — attente de la fin de l'optimisation…")
    for _ in range(120):
        etat = cible.get_collection(nom)
        if etat.status == models.CollectionStatus.GREEN:
            break
        time.sleep(5)

    n_cible = cible.count(nom, exact=True).count
    print(f"[vérif] source={total}  cible={n_cible}  statut={cible.get_collection(nom).status}")
    recherches_ok = _comparer_recherches(source, cible, nom)
    if n_cible == total and recherches_ok:
        POINT_CONTROLE.unlink(missing_ok=True)
        print("[OK] Migration terminée. Dans les secrets : QDRANT_URL / QDRANT_API_KEY = valeurs Cloud.")
    else:
        sys.exit("[!] Écart détecté : relancez le script (reprise) ou --recreer")


if __name__ == "__main__":
    main()
