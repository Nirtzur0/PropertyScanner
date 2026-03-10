from src.platform.settings import ValuationConfig
from src.valuation.services.conformal_calibrator import StratifiedCalibratorRegistry
from src.valuation.services.valuation import ValuationService


def _build_service_with_registry(registry: StratifiedCalibratorRegistry) -> ValuationService:
    service = ValuationService.__new__(ValuationService)
    service.calibrators = registry
    service.config = ValuationConfig()
    return service


def test_apply_interval_policy__uses_bootstrap_when_segment_coverage_is_below_floor():
    registry = StratifiedCalibratorRegistry(alpha=0.1, window_size=50)
    key = registry.bucket_key("barcelona", "sale", 250000.0)

    for _ in range(25):
        registry.update(key, 0, actual=130.0, pred_q10=90.0, pred_q50=100.0, pred_q90=110.0)

    service = _build_service_with_registry(registry)
    cal_q10, cal_q50, cal_q90, decision, diagnostics = service._apply_interval_policy(
        bucket_key=key,
        pred_q10=90.0,
        pred_q50=100.0,
        pred_q90=110.0,
        horizon_months=0,
    )

    assert decision["mode"] == "bootstrap"
    assert decision["reason"] == "coverage_below_floor"
    assert diagnostics["n_samples"] == 25.0
    assert cal_q10 < 90.0
    assert cal_q50 == 100.0
    assert cal_q90 > 110.0


def test_apply_interval_policy__uses_same_decision_surface_for_projection_horizons():
    registry = StratifiedCalibratorRegistry(alpha=0.1, window_size=50)
    key = registry.bucket_key("madrid", "sale", 250000.0)

    for _ in range(25):
        registry.update(key, 12, actual=100.0, pred_q10=90.0, pred_q50=100.0, pred_q90=110.0)

    service = _build_service_with_registry(registry)
    cal_q10, cal_q50, cal_q90, decision, diagnostics = service._apply_interval_policy(
        bucket_key=key,
        pred_q10=90.0,
        pred_q50=100.0,
        pred_q90=110.0,
        horizon_months=12,
    )

    assert decision["mode"] == "calibrated"
    assert decision["reason"] == "coverage_ok"
    assert diagnostics["horizon_months"] == 12.0
    assert cal_q50 == 100.0
