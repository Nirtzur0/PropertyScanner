from __future__ import annotations

import sqlite3

from src.platform.migrations import CURRENT_SCHEMA_VERSION, run_migrations


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
    assert "ui_events" in tables
    assert "listing_observations" in tables
    assert "listing_entities" in tables
    assert "benchmark_runs" in tables
    assert "coverage_reports" in tables


def test_run_migrations__canonicalizes_legacy_source_ids(tmp_path) -> None:
    db_path = tmp_path / "aliases.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE listings (source_id TEXT)")
        conn.execute("CREATE TABLE source_contract_runs (source_id TEXT, created_at DATETIME)")
        conn.execute("INSERT INTO listings (source_id) VALUES ('imovirtual')")
        conn.execute("INSERT INTO source_contract_runs (source_id) VALUES ('rightmove')")
        conn.commit()
    finally:
        conn.close()

    run_migrations(str(db_path))

    conn = sqlite3.connect(db_path)
    try:
        listing_source_id = conn.execute("SELECT source_id FROM listings").fetchone()[0]
        contract_source_id = conn.execute("SELECT source_id FROM source_contract_runs").fetchone()[0]
    finally:
        conn.close()

    assert listing_source_id == "imovirtual_pt"
    assert contract_source_id == "rightmove_uk"


def test_run_migrations__records_schema_version(tmp_path) -> None:
    db_path = tmp_path / "versioned.db"

    run_migrations(str(db_path))

    conn = sqlite3.connect(db_path)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()

    assert int(version) == CURRENT_SCHEMA_VERSION
