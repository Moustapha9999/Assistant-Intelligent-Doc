"""Connexions SQLite communes : délai de verrouillage, clés étrangères, transactions, sauvegarde."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

DELAI_VERROU_S = 15


def connecter(chemin: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(chemin), timeout=DELAI_VERROU_S, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def lecture(chemin: Path) -> Iterator[sqlite3.Connection]:
    conn = connecter(chemin)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def ecriture(chemin: Path) -> Iterator[sqlite3.Connection]:
    """Transaction atomique (BEGIN IMMEDIATE) : tout est validé, ou rien en cas d'exception."""
    conn = connecter(chemin)
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
    finally:
        conn.close()


def colonnes(conn: sqlite3.Connection, table: str) -> set:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def sauvegarder_avant_migration(chemin: Path, etiquette: str) -> Optional[Path]:
    """Copie cohérente (API backup SQLite) de la base avant une migration de schéma."""
    if not chemin.exists() or chemin.stat().st_size == 0:
        return None
    horodatage = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cible = chemin.with_name(f"{chemin.name}.avant_{etiquette}_{horodatage}.bak")
    src = sqlite3.connect(str(chemin))
    dst = sqlite3.connect(str(cible))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return cible
