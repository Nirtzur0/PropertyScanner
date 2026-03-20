from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

from src.platform.storage import StorageService


def _base_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return env


def test_cli_help__stays_quiet_and_avoids_training_warnings() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "src.interfaces.cli", "--help"],
        check=False,
        capture_output=True,
        text=True,
        env=_base_env(),
    )

    assert result.returncode == 0
    assert "Property Scanner CLI" in result.stdout
    assert "keras" not in result.stderr.lower()
    assert "tensorflow" not in result.stderr.lower()


def test_seed_sample_data_command__creates_seeded_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "seeded.db"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.interfaces.cli",
            "seed-sample-data",
            "--db",
            str(db_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=_base_env(),
    )

    assert result.returncode == 0
    start = result.stdout.find("{")
    end = result.stdout.rfind("}")
    assert start != -1 and end != -1
    payload = json.loads(result.stdout[start : end + 1])
    assert payload["status"] == "ok"
    assert payload["source_id"] == "pisos"

    storage = StorageService(db_url=f"sqlite:///{db_path}")
    session = storage.get_session()
    try:
        total_rows = session.execute(text("SELECT COUNT(1) FROM listings")).scalar_one()
    finally:
        session.close()

    assert int(total_rows) >= 4
