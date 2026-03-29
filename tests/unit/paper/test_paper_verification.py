import json
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from src.market.services.hedonic_index import HedonicIndexService
from src.platform.domain.schema import CanonicalListing, PropertyType
from src.platform.settings import ValuationConfig
from src.valuation.services.conformal_calibrator import ConformalCalibrator, enforce_monotonicity
from src.valuation.services.valuation import ValuationService


ROOT = Path(__file__).resolve().parents[3]


def _make_listing(*, listing_type: str = "sale", price: float = 300000.0) -> CanonicalListing:
    return CanonicalListing(
        id="listing-1",
        source_id="source",
        external_id="ext",
        url="https://example.com/listing",
        title="Test Listing",
        price=price,
        listing_type=listing_type,
        property_type=PropertyType.APARTMENT,
    )


def _make_temp_hedonic_db(path: Path, rows) -> None:
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
    # Convert old hedonic_indices rows (id, region_id, month_date, hedonic_index_sqm,
    # raw_median_sqm, r_squared, n_observations, n_neighborhoods, coefficients, updated_at)
    # to market_fundamentals with source='hedonic' and hedonic| id prefix
    new_rows = []
    for r in rows:
        rid = r[0] if r[0].startswith("hedonic|") else f"hedonic|{r[0]}"
        new_rows.append((rid, r[1], r[2], "hedonic", None, None, None, None, None, None, None, None, None, r[3], r[4], r[5], r[6], r[7], r[8], r[9]))
    cur.executemany(
        """
        INSERT INTO market_fundamentals (
            id, region_id, month_date, source, price_index_sqm, rent_index_sqm,
            inventory_count, new_listings_count, sold_count, absorption_rate,
            median_dom, price_cut_share, volatility_3m, hedonic_index_sqm,
            raw_median_sqm, r_squared, n_observations, n_neighborhoods,
            coefficients, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        new_rows,
    )
    conn.commit()
    conn.close()


def _service_with_config(config: ValuationConfig) -> ValuationService:
    svc = ValuationService.__new__(ValuationService)
    svc.config = config
    return svc


def test_time_adjustment_factor_exact(tmp_path: Path) -> None:
    db_path = tmp_path / "hedonic.db"
    rows = [
        ("all|2024-01", "all", "2024-01-01", 3000.0, 2900.0, 0.85, 20, 2, "{}", "2024-06-01"),
        ("all|2024-06", "all", "2024-06-01", 3300.0, 3200.0, 0.88, 20, 2, "{}", "2024-06-01"),
    ]
    _make_temp_hedonic_db(db_path, rows)

    svc = HedonicIndexService(db_path=str(db_path))
    factor, meta = svc.compute_adjustment_factor(
        region_id="all",
        comp_timestamp=datetime(2024, 1, 15),
        target_timestamp=datetime(2024, 6, 15),
    )

    assert pytest.approx(1.1, rel=1e-6) == factor
    assert meta["raw_factor"] == pytest.approx(1.1, rel=1e-6)
    assert meta["clamped"] is False


def test_time_adjustment_factor_clamped(tmp_path: Path) -> None:
    db_path = tmp_path / "hedonic.db"
    rows = [
        ("all|2024-01", "all", "2024-01-01", 1000.0, 950.0, 0.8, 20, 2, "{}", "2024-06-01"),
        ("all|2024-06", "all", "2024-06-01", 10000.0, 9800.0, 0.8, 20, 2, "{}", "2024-06-01"),
    ]
    _make_temp_hedonic_db(db_path, rows)

    svc = HedonicIndexService(db_path=str(db_path))
    factor, meta = svc.compute_adjustment_factor(
        region_id="all",
        comp_timestamp=datetime(2024, 1, 15),
        target_timestamp=datetime(2024, 6, 15),
    )

    assert factor == pytest.approx(2.0, rel=1e-6)
    assert meta["clamped"] is True


def test_enforce_monotonicity_sorted() -> None:
    assert enforce_monotonicity(100.0, 90.0, 80.0) == (80.0, 90.0, 100.0)


def test_conformal_monotonicity_small_sample() -> None:
    calibrator = ConformalCalibrator(alpha=0.1, window_size=50)
    q10, q50, q90 = calibrator.calibrate(120.0, 100.0, 80.0)
    assert q10 <= q50 <= q90
    assert q10 == pytest.approx(99.0, rel=1e-6)


def test_robust_baseline_filters_outliers() -> None:
    config = ValuationConfig(min_comps_for_baseline=3)
    svc = _service_with_config(config)
    baseline = svc._robust_comp_baseline([98.0, 100.0, 102.0, 10000.0])
    assert baseline == pytest.approx(100.0, rel=1e-6)


def test_log_residual_quantile_reconstruction() -> None:
    baseline_log = np.log(200000.0)
    r10 = -0.1
    q10 = float(np.exp(baseline_log + r10))
    assert q10 == pytest.approx(200000.0 * np.exp(-0.1), rel=1e-6)


def test_uncertainty_half_width() -> None:
    q10, q50, q90 = 90.0, 100.0, 110.0
    uncertainty = (q90 - q10) / (2 * q50)
    assert uncertainty == pytest.approx(0.1, rel=1e-6)


def test_income_value_bounds() -> None:
    config = ValuationConfig(
        income_value_weight_max=0.5,
        income_value_weight_min=0.0,
        income_value_max_adjustment_pct=0.35,
        area_sentiment_weight=0.0,
        area_development_weight=0.0,
        area_adjustment_cap=0.08,
    )
    svc = _service_with_config(config)
    listing = _make_listing()
    rent_comps = [_make_listing(price=2000.0) for _ in range(5)]

    adjusted_value, _, adjustments = svc._apply_income_and_area_adjustments(
        listing=listing,
        fair_value=300000.0,
        uncertainty=0.1,
        rent_est=1500.0,
        rent_uncertainty=0.1,
        rent_comps=rent_comps,
        market_signals={"market_yield": 4.0, "area_sentiment": 0.5, "area_development": 0.5},
    )

    assert adjustments["income_value"] == pytest.approx(405000.0, rel=1e-6)
    assert 300000.0 < adjusted_value <= 405000.0


def test_area_adjustment_cap() -> None:
    config = ValuationConfig(
        area_sentiment_weight=0.06,
        area_development_weight=0.04,
        area_adjustment_cap=0.02,
    )
    svc = _service_with_config(config)
    listing = _make_listing()

    _, _, adjustments = svc._apply_income_and_area_adjustments(
        listing=listing,
        fair_value=300000.0,
        uncertainty=0.1,
        rent_est=0.0,
        rent_uncertainty=0.0,
        rent_comps=[],
        market_signals={
            "area_sentiment": 1.0,
            "area_development": 1.0,
            "area_confidence": 1.0,
        },
    )

    assert adjustments["area_adjustment"] == pytest.approx(0.02, rel=1e-6)


def test_contract_labels_present() -> None:
    paper_tex = (ROOT / "paper" / "main.tex").read_text(encoding="utf-8")
    for label in [
        "eq:time_adjust",
        "eq:baseline_mad",
        "eq:residual",
        "eq:price_quantile",
        "eq:income_value",
        "eq:area_adjust",
        "eq:uncertainty",
        "sec:assumptions",
        "sec:method",
        "sec:implementation",
        "sec:verification",
        "sec:repro",
    ]:
        assert f"\\label{{{label}}}" in paper_tex

    verification_log = (ROOT / "paper" / "verification_log.md").read_text(encoding="utf-8")
    assert "## 1. Scope, regimes, and constraints" in verification_log


def test_regression_sanity_case() -> None:
    payload = json.loads((ROOT / "paper" / "artifacts" / "sanity_case.json").read_text(encoding="utf-8"))

    hedge = payload["hedonic_adjustment"]
    assert hedge["factor"] == pytest.approx(1.1, rel=1e-6)
    assert hedge["clamped"] is False

    calibration = payload["conformal_calibration"]
    assert calibration["raw"] == [255000.0, 300000.0, 345000.0]
    cal_q10, cal_q50, cal_q90 = calibration["calibrated"]
    assert cal_q10 <= cal_q50 <= cal_q90

    mono = payload["monotonicity_example"]
    assert mono["input"] == [100.0, 90.0, 80.0]
    assert mono["output"] == [80.0, 90.0, 100.0]


def test_contract_script_runs() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/verify_paper_contract.py"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
