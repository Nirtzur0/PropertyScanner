from __future__ import annotations

import sqlite3
from pathlib import Path

from src.platform.storage import StorageService


def _table_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()


def test_storage_service__can_skip_schema_bootstrap(tmp_path: Path) -> None:
    db_path = tmp_path / "no-bootstrap.db"
    storage = StorageService(db_url=f"sqlite:///{db_path}", bootstrap_schema=False)

    with storage.engine.connect():
        pass

    assert "listings" not in _table_names(db_path)


def test_storage_service__bootstraps_runtime_schema_by_default(tmp_path: Path) -> None:
    db_path = tmp_path / "bootstrap.db"
    StorageService(db_url=f"sqlite:///{db_path}")

    tables = _table_names(db_path)
    assert "listings" in tables
    assert "job_runs" in tables
