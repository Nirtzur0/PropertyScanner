import json

from src.valuation.services.conformal_calibrator import StratifiedCalibratorRegistry
from src.valuation.workflows.calibration import update_calibrators


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


def test_segmented_coverage_report__includes_required_segments_and_threshold_status():
    registry = StratifiedCalibratorRegistry(alpha=0.1, window_size=50)

    pass_key = registry.bucket_key("madrid", "sale", 220000.0)
    fail_key = registry.bucket_key("barcelona", "rent", 900000.0)

    for _ in range(25):
        # Covered interval -> high coverage
        registry.update(pass_key, 0, actual=100.0, pred_q10=90.0, pred_q50=100.0, pred_q90=110.0)
        # Missed interval -> low coverage
        registry.update(fail_key, 0, actual=130.0, pred_q10=90.0, pred_q50=100.0, pred_q90=110.0)

    report = registry.segmented_coverage_report(min_samples=20, coverage_floor=0.8)

    pass_segment = _find_segment(report, region_id="madrid", listing_type="sale", horizon_months=0)
    fail_segment = _find_segment(report, region_id="barcelona", listing_type="rent", horizon_months=0)

    assert pass_segment["price_band"] == "<= 300000"
    assert pass_segment["meets_sample_threshold"] is True
    assert pass_segment["meets_coverage_threshold"] is True
    assert pass_segment["status"] == "pass"

    assert fail_segment["price_band"] == "<= 1000000"
    assert fail_segment["meets_sample_threshold"] is True
    assert fail_segment["meets_coverage_threshold"] is False
    assert fail_segment["status"] == "fail"

    assert report["summary"]["evaluated_segments"] >= 2
    assert report["summary"]["passing_segments"] >= 1
    assert report["summary"]["failing_segments"] >= 1


def test_update_calibrators__writes_segmented_coverage_report(tmp_path):
    input_path = tmp_path / "calibration_samples.jsonl"
    output_path = tmp_path / "calibration_registry.json"
    coverage_path = tmp_path / "calibration_coverage.json"

    samples = []
    for i in range(25):
        actual = 230000.0 + float(i)
        samples.append(
            {
                "region_id": "madrid",
                "property_type": "sale",
                "horizon_months": 0,
                "actual": actual,
                "pred_q10": actual - 5000.0,
                "pred_q50": actual,
                "pred_q90": actual + 5000.0,
            }
        )

    with open(input_path, "w") as f:
        for sample in samples:
            f.write(json.dumps(sample) + "\n")

    count = update_calibrators(
        input_path=str(input_path),
        output_path=str(output_path),
        coverage_output_path=str(coverage_path),
        alpha=0.1,
        window_size=50,
        coverage_min_samples=20,
        coverage_floor=0.8,
    )

    assert count == 25
    assert output_path.exists()
    assert coverage_path.exists()

    report = json.loads(coverage_path.read_text())
    assert report["segment_count"] >= 1
    assert report["summary"]["evaluated_segments"] >= 1
    segment = _find_segment(report, region_id="madrid", listing_type="sale", horizon_months=0)
    assert segment["price_band"] == "<= 300000"


def test_interval_policy__returns_bootstrap_for_unseen_segment():
    registry = StratifiedCalibratorRegistry(alpha=0.1, window_size=50)

    decision = registry.interval_policy("unknown|sale|<= 300000", horizon_months=0)

    assert decision["mode"] == "bootstrap"
    assert decision["reason"] == "unseen_segment"
    assert decision["n_samples"] == 0


def test_interval_policy__returns_bootstrap_for_insufficient_samples():
    registry = StratifiedCalibratorRegistry(alpha=0.1, window_size=50)
    key = registry.bucket_key("madrid", "sale", 250000.0)

    for _ in range(5):
        registry.update(key, 0, actual=100.0, pred_q10=90.0, pred_q50=100.0, pred_q90=110.0)

    decision = registry.interval_policy(key, horizon_months=0, min_samples=20, coverage_floor=0.8)

    assert decision["mode"] == "bootstrap"
    assert decision["reason"] == "insufficient_samples"
    assert decision["n_samples"] == 5


def test_interval_policy__returns_bootstrap_for_coverage_below_floor():
    registry = StratifiedCalibratorRegistry(alpha=0.1, window_size=50)
    key = registry.bucket_key("barcelona", "sale", 250000.0)

    for _ in range(25):
        registry.update(key, 0, actual=130.0, pred_q10=90.0, pred_q50=100.0, pred_q90=110.0)

    decision = registry.interval_policy(key, horizon_months=0, min_samples=20, coverage_floor=0.8)

    assert decision["mode"] == "bootstrap"
    assert decision["reason"] == "coverage_below_floor"
    assert decision["coverage_rate"] < decision["coverage_floor"]


def test_interval_policy__returns_calibrated_when_segment_meets_thresholds():
    registry = StratifiedCalibratorRegistry(alpha=0.1, window_size=50)
    key = registry.bucket_key("madrid", "sale", 250000.0)

    for _ in range(25):
        registry.update(key, 0, actual=100.0, pred_q10=90.0, pred_q50=100.0, pred_q90=110.0)

    decision = registry.interval_policy(key, horizon_months=0, min_samples=20, coverage_floor=0.8)

    assert decision["mode"] == "calibrated"
    assert decision["reason"] == "coverage_ok"
    assert decision["coverage_rate"] >= decision["coverage_floor"]
