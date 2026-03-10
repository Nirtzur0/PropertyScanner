import json

from src.valuation.workflows.calibration import (
    build_spatial_residual_diagnostics,
    update_calibrators,
)


def _find_segment(report, *, region_id: str, listing_type: str, horizon_months: int):
    for segment in report["segments"]:
        if (
            segment["region_id"] == region_id
            and segment["listing_type"] == listing_type
            and segment["horizon_months"] == horizon_months
        ):
            return segment
    raise AssertionError(
        f"Missing segment for region={region_id}, listing_type={listing_type}, horizon={horizon_months}"
    )


def test_build_spatial_residual_diagnostics__flags_drift_and_outliers():
    rows = []

    for _ in range(25):
        rows.append(
            {
                "region_id": "madrid",
                "listing_type": "sale",
                "price_band": "<= 300000",
                "horizon_months": 0,
                "actual": 201000.0,
                "pred_q50": 200000.0,
                "residual": 1000.0,
                "pct_residual": 0.005,
            }
        )

    for _ in range(25):
        rows.append(
            {
                "region_id": "barcelona",
                "listing_type": "rent",
                "price_band": "<= 300000",
                "horizon_months": 0,
                "actual": 230000.0,
                "pred_q50": 200000.0,
                "residual": 30000.0,
                "pct_residual": 0.15,
            }
        )

    for idx in range(25):
        residual = 50000.0 if idx < 3 else 0.0
        rows.append(
            {
                "region_id": "valencia",
                "listing_type": "sale",
                "price_band": "<= 300000",
                "horizon_months": 0,
                "actual": 200000.0 + residual,
                "pred_q50": 200000.0,
                "residual": residual,
                "pct_residual": residual / 200000.0,
            }
        )

    report = build_spatial_residual_diagnostics(
        rows,
        min_samples=20,
        drift_threshold_pct=0.08,
        outlier_rate_threshold=0.10,
        outlier_zscore=2.0,
    )

    madrid = _find_segment(report, region_id="madrid", listing_type="sale", horizon_months=0)
    barcelona = _find_segment(report, region_id="barcelona", listing_type="rent", horizon_months=0)
    valencia = _find_segment(report, region_id="valencia", listing_type="sale", horizon_months=0)

    assert madrid["status"] == "pass"
    assert madrid["drift_flag"] is False
    assert madrid["outlier_flag"] is False

    assert barcelona["status"] in {"warn_drift", "warn_drift_outlier"}
    assert barcelona["drift_flag"] is True

    assert valencia["status"] in {"warn_outlier", "warn_drift_outlier"}
    assert valencia["outlier_flag"] is True

    assert report["summary"]["warn_segments"] >= 2


def test_update_calibrators__writes_spatial_diagnostics_report(tmp_path):
    input_path = tmp_path / "calibration_samples.jsonl"
    output_path = tmp_path / "calibration_registry.json"
    coverage_path = tmp_path / "calibration_coverage.json"
    spatial_path = tmp_path / "spatial_diagnostics.json"

    with open(input_path, "w") as f:
        for i in range(30):
            actual = 220000.0 + float(i)
            row = {
                "region_id": "madrid",
                "property_type": "sale",
                "horizon_months": 0,
                "actual": actual,
                "pred_q10": actual - 8000.0,
                "pred_q50": actual - 1000.0,
                "pred_q90": actual + 8000.0,
            }
            f.write(json.dumps(row) + "\n")

    count = update_calibrators(
        input_path=str(input_path),
        output_path=str(output_path),
        coverage_output_path=str(coverage_path),
        spatial_output_path=str(spatial_path),
        alpha=0.1,
        window_size=50,
        coverage_min_samples=20,
        coverage_floor=0.8,
        spatial_min_samples=20,
        spatial_drift_threshold_pct=0.08,
        spatial_outlier_rate_threshold=0.15,
        spatial_outlier_zscore=2.5,
    )

    assert count == 30
    assert output_path.exists()
    assert coverage_path.exists()
    assert spatial_path.exists()

    spatial = json.loads(spatial_path.read_text())
    assert spatial["method"] == "spatial_residual_diagnostics_moran_lisa_proxy"
    assert spatial["summary"]["segment_count"] >= 1

    madrid = _find_segment(spatial, region_id="madrid", listing_type="sale", horizon_months=0)
    assert "lisa_like_hotspot" in madrid
    assert madrid["n_samples"] == 30
