from __future__ import annotations

import importlib
from pathlib import Path

from fastapi.testclient import TestClient

from src.application.sample_data import seed_sample_data
from src.application.container import get_container
from src.core.runtime import load_runtime_config
from src.platform.db.base import resolve_db_url
from src.platform.storage import StorageService


def test_local_api__seeded_sample_path_supports_listings_and_valuation(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "api-smoke.db"
    monkeypatch.setenv("PROPERTY_SCANNER_DB_PATH", str(db_path))
    get_container.cache_clear()
    load_runtime_config.cache_clear()

    storage = StorageService(db_url=resolve_db_url(db_path=str(db_path)))
    seed_sample_data(storage=storage)

    module = importlib.import_module("src.adapters.http.app")
    module = importlib.reload(module)
    client = TestClient(module.app)

    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    listings = client.get("/api/v1/listings")
    assert listings.status_code == 200
    listings_payload = listings.json()
    assert listings_payload["total"] >= 4

    valuation = client.post(
        "/api/v1/valuations",
        json={"listing_id": "sample-pisos-target", "persist": False},
    )
    assert valuation.status_code == 200
    valuation_payload = valuation.json()
    assert valuation_payload["listing_id"] == "sample-pisos-target"
    assert float(valuation_payload["fair_value_estimate"]) > 0
