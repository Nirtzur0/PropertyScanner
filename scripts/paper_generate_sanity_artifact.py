#!/usr/bin/env python3
"""Generate deterministic sanity artifact for paper regression tests."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from datetime import datetime

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))

from src.market.services.hedonic_index import HedonicIndexService
from src.valuation.services.conformal_calibrator import ConformalCalibrator, enforce_monotonicity

ARTIFACT_PATH = ROOT / "paper" / "artifacts" / "sanity_case.json"


def _make_temp_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE market_fundamentals (
            id TEXT PRIMARY KEY,
            region_id TEXT NOT NULL,
            month_date DATE NOT NULL,
            source TEXT NOT NULL,
            price_index_sqm FLOAT,
            rent_index_sqm FLOAT,
            inventory_count INT,
            new_listings_count INT,
            sold_count INT,
            absorption_rate FLOAT,
            median_dom INT,
            price_cut_share FLOAT,
            volatility_3m FLOAT,
            hedonic_index_sqm FLOAT,
            raw_median_sqm FLOAT,
            r_squared FLOAT,
            n_observations INT,
            n_neighborhoods INT,
            coefficients TEXT,
            updated_at DATETIME
        )
        """
    )
    rows = [
        ("hedonic|all|2024-01", "all", "2024-01", "hedonic", None, None, None, None, None, None, None, None, None, 3000.0, 2900.0, 0.85, 20, 2, "{}", "2024-06-01"),
        ("hedonic|all|2024-06", "all", "2024-06", "hedonic", None, None, None, None, None, None, None, None, None, 3300.0, 3200.0, 0.88, 20, 2, "{}", "2024-06-01"),
    ]
    cur.executemany(
        """
        INSERT INTO market_fundamentals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def main() -> int:
    tmp_db = ROOT / "paper" / "artifacts" / "_temp_hedonic.db"
    if tmp_db.exists():
        tmp_db.unlink()
    _make_temp_db(tmp_db)

    svc = HedonicIndexService(db_path=str(tmp_db))
    factor, meta = svc.compute_adjustment_factor(
        region_id="all",
        comp_timestamp=datetime(2024, 1, 15),
        target_timestamp=datetime(2024, 6, 15),
    )

    calibrator = ConformalCalibrator(alpha=0.1, window_size=50)
    np.random.seed(7)
    for i in range(50):
        actual = 300000 + (i % 5) * 1000
        pred_q10 = actual - 45000
        pred_q50 = actual
        pred_q90 = actual + 45000
        calibrator.update(actual, pred_q10, pred_q50, pred_q90)

    raw = (255000.0, 300000.0, 345000.0)
    cal_q10, cal_q50, cal_q90 = calibrator.calibrate(*raw)
    mono = enforce_monotonicity(100.0, 90.0, 80.0)

    payload = {
        "hedonic_adjustment": {
            "factor": factor,
            "raw_factor": meta.get("raw_factor"),
            "clamped": meta.get("clamped"),
        },
        "conformal_calibration": {
            "raw": raw,
            "calibrated": [cal_q10, cal_q50, cal_q90],
        },
        "monotonicity_example": {
            "input": [100.0, 90.0, 80.0],
            "output": list(mono),
        },
    }

    ARTIFACT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if tmp_db.exists():
        tmp_db.unlink()
    print(f"wrote {ARTIFACT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
