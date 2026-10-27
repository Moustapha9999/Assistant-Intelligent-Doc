"""Chargement des chunks et recherche sparse BM25."""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from scipy import sparse

VERSION_CACHE = 1


class BM25Creux:
    """
    BM25 Okapi identique à `rank_bm25.BM25Okapi` (k1, b, plancher epsilon sur l'idf),
    stocké en matrice creuse documents × termes : get_scores est vectorisé au lieu
    de parcourir 144k dictionnaires Python par mot de requête.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75, epsilon: float = 0.25):
        self.k1, self.b, self.epsilon = k1, b, epsilon
        self.vocab: Dict[str, int] = {}
        self.idf = np.zeros(0)
        self.poids: Optional[sparse.csc_matrix] = None
        self.corpus_size = 0
        self.avgdl = 0.0

    @classmethod
    def construire(cls, corpus: Iterable[Sequence[str]], **kwargs) -> "BM25Creux":
        self = cls(**kwargs)
        lignes, colonnes, freqs, doc_len = [], [], [], []
        for i, doc in enumerate(corpus):
            doc_len.append(len(doc))
            for mot, tf in Counter(doc).items():
                col = self.vocab.setdefault(mot, len(self.vocab))
                lignes.append(i)
                colonnes.append(col)
                freqs.append(tf)
        self.corpus_size = len(doc_len)
        lignes_np = np.asarray(lignes, dtype=np.int32)
        cols_np = np.asarray(colonnes, dtype=np.int32)
        tf_np = np.asarray(freqs, dtype=np.float64)
        dl = np.asarray(doc_len, dtype=np.float64)
        self.avgdl = float(dl.sum() / max(1, self.corpus_size))

        nd = np.bincount(cols_np, minlength=len(self.vocab)).astype(np.float64)
        idf = np.log(self.corpus_size - nd + 0.5) - np.log(nd + 0.5)
        moyenne = float(idf.sum() / max(1, len(idf)))
        idf[idf < 0] = self.epsilon * moyenne
        self.idf = idf

        denom = tf_np + self.k1 * (1 - self.b + self.b * dl[lignes_np] / self.avgdl)
        valeurs = tf_np * (self.k1 + 1) / denom
        self.poids = sparse.csc_matrix(
            (valeurs, (lignes_np, cols_np)), shape=(self.corpus_size, len(self.vocab))
        )
        return self

    def get_scores(self, query: Sequence[str]) -> np.ndarray:
        compte = Counter(t for t in query if t in self.vocab)
        if not compte or self.poids is None:
            return np.zeros(self.corpus_size)
        cols = np.fromiter((self.vocab[t] for t in compte), dtype=np.int64)
        coef = self.idf[cols] * np.fromiter(compte.values(), dtype=np.float64)
        return np.asarray(self.poids[:, cols] @ coef).ravel()

    # --- cache disque -------------------------------------------------------
    def sauver(self, dossier: Path, signature: str) -> None:
        dossier.mkdir(parents=True, exist_ok=True)
        sparse.save_npz(dossier / "poids.npz", self.poids)
        np.save(dossier / "idf.npy", self.idf)
        meta = {
            "version": VERSION_CACHE, "signature": signature, "k1": self.k1, "b": self.b,
            "epsilon": self.epsilon, "corpus_size": self.corpus_size, "avgdl": self.avgdl,
        }
        (dossier / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        (dossier / "vocab.json").write_text(json.dumps(list(self.vocab), ensure_ascii=False), encoding="utf-8")

    @classmethod
    def charger(cls, dossier: Path, signature: str) -> Optional["BM25Creux"]:
        try:
            meta = json.loads((dossier / "meta.json").read_text(encoding="utf-8"))
            if meta.get("version") != VERSION_CACHE or meta.get("signature") != signature:
                return None
            self = cls(k1=meta["k1"], b=meta["b"], epsilon=meta["epsilon"])
            self.corpus_size = int(meta["corpus_size"])
            self.avgdl = float(meta["avgdl"])
            mots = json.loads((dossier / "vocab.json").read_text(encoding="utf-8"))
            self.vocab = {m: i for i, m in enumerate(mots)}
            self.idf = np.load(dossier / "idf.npy")
            self.poids = sparse.load_npz(dossier / "poids.npz").tocsc()
            return self
        except (OSError, ValueError, KeyError):
            return None


def tokeniser(texte: str) -> List[str]:
    return texte.lower().split()


def _signature(chunks_file: str) -> str:
    """Empreinte du contenu (pas de la date) : le cache reste valide après copie ou téléchargement."""
    h = hashlib.sha256()
    with open(chunks_file, "rb") as f:
        for bloc in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(bloc)
    return f"{os.path.getsize(chunks_file)}-{h.hexdigest()[:16]}"


def construire_index_bm25(
    chunks_file: str, dossier_cache: Optional[Path] = None
) -> Tuple[List[Dict], Optional[BM25Creux]]:
    if not os.path.exists(chunks_file):
        print(f"   ⚠️  Chunks introuvables : {chunks_file}")
        return [], None
    with open(chunks_file, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    dossier = dossier_cache or Path(chunks_file).with_name("bm25_cache")
    signature = _signature(chunks_file)
    index = BM25Creux.charger(dossier, signature)
    if index is not None and index.corpus_size == len(chunks):
        return chunks, index

    index = BM25Creux.construire(tokeniser(c.get("texte", "")) for c in chunks)
    try:
        index.sauver(dossier, signature)
    except OSError as e:
        print(f"   ⚠️  Cache BM25 non écrit ({e})")
    return chunks, index


def recherche_bm25(
    bm25_index,
    chunks_bruts: List[Dict],
    requete: str,
    top_k: int,
    passe_filtres,
    filtres: Optional[Dict] = None,
) -> List[Dict]:
    if bm25_index is None:
        return []
    tokens = tokeniser(requete)
    scores = bm25_index.get_scores(tokens)
    score_max = scores.max() if scores.max() > 0 else 1.0
    scores_n = scores / score_max
    indices = np.argsort(scores_n)[::-1][: top_k * 3]

    documents = []
    for idx in indices:
        if scores_n[idx] <= 0:
            continue
        chunk = chunks_bruts[idx]
        doc = {
            "texte": chunk.get("texte", ""),
            "nom_complet": chunk.get("nom_complet", ""),
            "langage": chunk.get("langage", ""),
            "url": chunk.get("url", ""),
            "section_titre": chunk.get("section_titre", ""),
            "source_file": chunk.get("chemin_fichier", chunk.get("source_file", "")),
            "etoiles": chunk.get("etoiles", 0) or 0,
            "mis_a_jour_le": chunk.get("mis_a_jour_le", ""),
            "version": chunk.get("version", ""),
            "type_chunk": chunk.get("type_chunk", ""),
            "source_enrichissement": bool(chunk.get("source_enrichissement")),
            "score_dense": 0.0,
            "score_bm25": float(scores_n[idx]),
            "score_final": 0.0,
            "score_confiance": 0.0,
        }
        if passe_filtres(doc, filtres):
            documents.append(doc)
        if len(documents) >= top_k:
            break
    return documents
