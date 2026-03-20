from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application.sample_data import seed_sample_data
from src.platform.db.base import resolve_db_url
from src.platform.storage import StorageService


def _wait_for_health(base_url: str, *, timeout_seconds: float) -> dict:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = requests.get(f"{base_url}/api/v1/health", timeout=1.5)
            if response.ok:
                return response.json()
        except Exception as exc:  # pragma: no cover - exercised in subprocess retry loop
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"api_health_timeout: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed sample data and smoke-test the local API.")
    parser.add_argument("--db-path", default=".tmp/smoke-api.db")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--startup-timeout", type=float, default=20.0)
    args = parser.parse_args()

    db_path = Path(args.db_path).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    storage = StorageService(db_url=resolve_db_url(db_path=str(db_path)))
    seed_result = seed_sample_data(storage=storage)

    env = dict(os.environ)
    env["PROPERTY_SCANNER_DB_PATH"] = str(db_path)
    env.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    base_url = f"http://{args.host}:{args.port}"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "src.interfaces.cli",
            "api",
            "--host",
            args.host,
            "--port",
            str(args.port),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        health = _wait_for_health(base_url, timeout_seconds=args.startup_timeout)
        listings_response = requests.get(f"{base_url}/api/v1/listings", timeout=2.0)
        listings_response.raise_for_status()
        listings_payload = listings_response.json()
        if int(listings_payload.get("total", 0) or 0) < 4:
            raise RuntimeError(f"seeded_listings_missing: {listings_payload}")

        valuation_response = requests.post(
            f"{base_url}/api/v1/valuations",
            json={"listing_id": "sample-pisos-target", "persist": False},
            timeout=4.0,
        )
        valuation_response.raise_for_status()
        valuation_payload = valuation_response.json()
        if float(valuation_payload.get("fair_value_estimate", 0.0) or 0.0) <= 0:
            raise RuntimeError(f"valuation_missing: {valuation_payload}")

        print(
            json.dumps(
                {
                "status": "ok",
                "health": health,
                "seed_result": seed_result,
                "listing_total": listings_payload.get("total"),
                "valuation_listing_id": valuation_payload.get("listing_id"),
                }
            )
        )
        return 0
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
