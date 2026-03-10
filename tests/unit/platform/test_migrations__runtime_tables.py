from __future__ import annotations

import sqlite3

from src.platform.migrations import run_migrations


def test_run_migrations__creates_runtime_refactor_tables(tmp_path) -> None:
    db_path = tmp_path / "migrations.db"
    run_migrations(str(db_path))

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    finally:
        conn.close()

    assert "job_runs" in tables
    assert "source_contract_runs" in tables
    assert "data_quality_events" in tables
    assert "listing_observations" in tables
    assert "listing_entities" in tables
    assert "benchmark_runs" in tables
    assert "coverage_reports" in tables
