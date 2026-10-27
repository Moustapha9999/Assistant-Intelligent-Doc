"""
Corrige à la source les métadonnées des guides d'enrichissement dans tous_chunks.json.

Ces guides ont été rédigés pour le projet : ils ne viennent pas d'un dépôt GitHub.
Ils portaient des valeurs fictives (etoiles=99999, url=https://github.com/enrichissement/...).

Effets :
  - etoiles -> null, url -> "" ; source_enrichissement=True, provenance="guide_interne"
  - sauvegarde préalable : tous_chunks.avant_provenance.json
  - rapport : nombre de chunks corrigés, contrôle des URL des chunks GitHub

Usage :
    python scripts/corriger_provenance_corpus.py            # applique
    python scripts/corriger_provenance_corpus.py --dry-run  # rapport seul
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import config  # noqa: E402
from retrieval.citations import PROVENANCE_GITHUB, PROVENANCE_GUIDE, determiner_provenance  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    chemin = Path(config.CHUNKS_FILE)
    brut = chemin.read_bytes()
    ensure_ascii = b"\\u00" in brut[:5_000_000]
    chunks = json.loads(brut.decode("utf-8"))

    corriges, provenances = 0, {}
    for c in chunks:
        p = determiner_provenance(c)
        provenances[p] = provenances.get(p, 0) + 1
        if p != PROVENANCE_GUIDE:
            continue
        avant = (c.get("etoiles"), c.get("url"), c.get("source_enrichissement"), c.get("provenance"))
        c["etoiles"] = None
        c["url"] = ""
        c["source_enrichissement"] = True
        c["provenance"] = PROVENANCE_GUIDE
        if avant != (None, "", True, PROVENANCE_GUIDE):
            corriges += 1
            print(f"  corrigé : {c.get('nom_complet')} (avant etoiles={avant[0]}, url={avant[1]!r})")

    print(f"Chunks : {len(chunks)} | provenances : {provenances}")
    print(f"Guides internes corrigés : {corriges}")
    non_github = provenances.get("inconnue", 0)
    if non_github:
        print(f"⚠️  {non_github} chunks de provenance inconnue (URL ≠ github.com/<nom_complet>)")
    print(f"Chunks GitHub vérifiés : {provenances.get(PROVENANCE_GITHUB, 0)}")

    if args.dry_run or not corriges:
        print("Aucune écriture." if not corriges else "Dry-run : aucune écriture.")
        return

    sauvegarde = chemin.with_name("tous_chunks.avant_provenance.json")
    if not sauvegarde.exists():
        shutil.copy2(chemin, sauvegarde)
        print(f"Sauvegarde : {sauvegarde}")
    tmp = chemin.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(chunks, ensure_ascii=ensure_ascii), encoding="utf-8")
    tmp.replace(chemin)
    print(f"Écrit : {chemin}")


if __name__ == "__main__":
    main()
