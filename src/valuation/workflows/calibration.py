import argparse
import json
import math
from collections import defaultdict
from typing import Dict, Any, Iterable, Optional

import structlog

from src.application.reporting import ReportingService
from src.platform.db.base import resolve_db_url
from src.platform.settings import AppConfig
from src.platform.storage import StorageService
from src.valuation.services.conformal_calibrator import StratifiedCalibratorRegistry
from src.platform.utils.config import load_app_config_safe

logger = structlog.get_logger(__name__)


def persist_segmented_coverage_report(
    report: Dict[str, Any],
    *,
    app_config: AppConfig,
) -> int:
    db_url = resolve_db_url(
        db_url=app_config.pipeline.db_url,
        db_path=app_config.pipeline.db_path,
    )
    storage = StorageService(db_url=db_url)
    return len(ReportingService(storage=storage).persist_segmented_coverage_report(report))


def _iter_samples(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def _median(values: Iterable[float]) -> float:
    values = sorted(list(values))
    if not values:
        return 0.0
    n = len(values)
    mid = n // 2
    if n % 2 == 1:
        return float(values[mid])
    return float((values[mid - 1] + values[mid]) / 2.0)


def _std(values: Iterable[float], mean_value: Optional[float] = None) -> float:
    values = list(values)
    if not values:
        return 0.0
    mu = _mean(values) if mean_value is None else float(mean_value)
    variance = _mean((v - mu) ** 2 for v in values)
    return float(math.sqrt(max(0.0, variance)))


def build_spatial_residual_diagnostics(
    samples: Iterable[Dict[str, Any]],
    *,
    min_samples: int = 20,
    drift_threshold_pct: float = 0.08,
    outlier_rate_threshold: float = 0.15,
    outlier_zscore: float = 2.5,
) -> Dict[str, Any]:
    """
    Build spatial residual diagnostics from calibration samples.

    This emits regional drift/outlier warnings and includes Moran/LISA proxy fields.
    """
    rows = list(samples)
    grouped: Dict[str, list] = defaultdict(list)
    for row in rows:
        key = (
            f"{row['region_id']}|{row['listing_type']}|"
            f"{row['price_band']}|{int(row['horizon_months'])}"
        )
        grouped[key].append(row)

    global_residuals = [float(r["residual"]) for r in rows]
    global_mean_residual = _mean(global_residuals)
    global_std_residual = _std(global_residuals, global_mean_residual)

    segments = []
    for key in sorted(grouped.keys()):
        segment_rows = grouped[key]
        residuals = [float(r["residual"]) for r in segment_rows]
        pct_residuals = [float(r["pct_residual"]) for r in segment_rows]

        mean_residual = _mean(residuals)
        median_residual = _median(residuals)
        residual_std = _std(residuals, mean_residual)
        mae = _mean(abs(r) for r in residuals)
        rmse = math.sqrt(_mean((r * r) for r in residuals)) if residuals else 0.0
        mean_pct_error = _mean(pct_residuals)

        if residual_std > 0:
            outlier_hits = [
                1
                for residual in residuals
                if abs((residual - mean_residual) / residual_std) >= outlier_zscore
            ]
            outlier_rate = len(outlier_hits) / len(residuals)
        else:
            outlier_rate = 0.0

        n_samples = len(segment_rows)
        meets_sample_threshold = n_samples >= int(min_samples)
        drift_flag = meets_sample_threshold and abs(mean_pct_error) >= float(drift_threshold_pct)
        outlier_flag = meets_sample_threshold and outlier_rate >= float(outlier_rate_threshold)
        lisa_like_hotspot = (
            meets_sample_threshold
            and global_std_residual > 0
            and abs(mean_residual - global_mean_residual) >= (1.5 * global_std_residual)
        )

        if not meets_sample_threshold:
            status = "insufficient_samples"
        elif drift_flag and outlier_flag:
            status = "warn_drift_outlier"
        elif drift_flag:
            status = "warn_drift"
        elif outlier_flag:
            status = "warn_outlier"
        else:
            status = "pass"

        first = segment_rows[0]
        segments.append(
            {
                "region_id": first["region_id"],
                "listing_type": first["listing_type"],
                "price_band": first["price_band"],
                "horizon_months": int(first["horizon_months"]),
                "n_samples": n_samples,
                "mean_residual": round(mean_residual, 4),
                "median_residual": round(median_residual, 4),
                "residual_std": round(residual_std, 4),
                "mae": round(mae, 4),
                "rmse": round(rmse, 4),
                "mean_pct_error": round(mean_pct_error, 6),
                "outlier_rate": round(outlier_rate, 6),
                "drift_flag": bool(drift_flag),
                "outlier_flag": bool(outlier_flag),
                "lisa_like_hotspot": bool(lisa_like_hotspot),
                "status": status,
            }
        )

    warn_segments = [s for s in segments if str(s["status"]).startswith("warn_")]
    pass_segments = [s for s in segments if s["status"] == "pass"]
    insufficient_segments = [s for s in segments if s["status"] == "insufficient_samples"]

    return {
        "method": "spatial_residual_diagnostics_moran_lisa_proxy",
        "notes": (
            "Region/listing_type/price_band/horizon diagnostics with drift/outlier signals; "
            "Moran/LISA proxy fields are descriptive and not full adjacency-matrix statistics."
        ),
        "thresholds": {
            "min_samples": int(min_samples),
            "drift_threshold_pct": float(drift_threshold_pct),
            "outlier_rate_threshold": float(outlier_rate_threshold),
            "outlier_zscore": float(outlier_zscore),
        },
        "global": {
            "sample_count": len(rows),
            "mean_residual": round(global_mean_residual, 4),
            "residual_std": round(global_std_residual, 4),
        },
        "summary": {
            "segment_count": len(segments),
            "pass_segments": len(pass_segments),
            "warn_segments": len(warn_segments),
            "insufficient_segments": len(insufficient_segments),
        },
        "segments": segments,
    }


def update_calibrators(
    *,
    input_path: str,
    output_path: Optional[str] = None,
    coverage_output_path: Optional[str] = None,
    spatial_output_path: Optional[str] = None,
    alpha: float = 0.1,
    window_size: int = 50,
    coverage_min_samples: int = 20,
    coverage_floor: Optional[float] = None,
    spatial_min_samples: int = 20,
    spatial_drift_threshold_pct: float = 0.08,
    spatial_outlier_rate_threshold: float = 0.15,
    spatial_outlier_zscore: float = 2.5,
    app_config: Optional[AppConfig] = None,
) -> int:
    app_config = app_config or load_app_config_safe()
    if output_path is None:
        output_path = str(app_config.paths.calibration_path)
    registry = StratifiedCalibratorRegistry(alpha=alpha, window_size=window_size)

    count = 0
    diagnostics_rows = []
    for sample in _iter_samples(input_path):
        region_id = sample.get("region_id")
        property_type = sample.get("property_type")
        horizon = int(sample.get("horizon_months", 0))
        actual = float(sample["actual"])
        pred_q10 = float(sample["pred_q10"])
        pred_q50 = float(sample["pred_q50"])
        pred_q90 = float(sample["pred_q90"])

        key = registry.bucket_key(region_id, property_type, actual)
        registry.update(key, horizon, actual, pred_q10, pred_q50, pred_q90)
        parsed_region, parsed_listing_type, price_band = registry._parse_bucket_key(key)
        residual = actual - pred_q50
        pct_residual = (residual / pred_q50) if pred_q50 else 0.0
        diagnostics_rows.append(
            {
                "region_id": parsed_region,
                "listing_type": parsed_listing_type,
                "price_band": price_band,
                "horizon_months": horizon,
                "actual": actual,
                "pred_q50": pred_q50,
                "residual": residual,
                "pct_residual": pct_residual,
            }
        )
        count += 1

    registry.save(output_path)
    logger.info("calibration_updated", samples=count, output=output_path)

    if coverage_output_path:
        report = registry.segmented_coverage_report(
            min_samples=coverage_min_samples,
            coverage_floor=coverage_floor,
        )
        with open(coverage_output_path, "w") as f:
            json.dump(report, f, indent=2, sort_keys=True)
        logger.info(
            "calibration_coverage_report_written",
            output=coverage_output_path,
            segment_count=report.get("segment_count", 0),
            evaluated_segments=report.get("summary", {}).get("evaluated_segments", 0),
            failing_segments=report.get("summary", {}).get("failing_segments", 0),
        )
        inserted = persist_segmented_coverage_report(report, app_config=app_config)
        logger.info(
            "calibration_coverage_report_persisted",
            inserted_rows=inserted,
        )

    if spatial_output_path:
        diagnostics = build_spatial_residual_diagnostics(
            diagnostics_rows,
            min_samples=spatial_min_samples,
            drift_threshold_pct=spatial_drift_threshold_pct,
            outlier_rate_threshold=spatial_outlier_rate_threshold,
            outlier_zscore=spatial_outlier_zscore,
        )
        with open(spatial_output_path, "w") as f:
            json.dump(diagnostics, f, indent=2, sort_keys=True)
        logger.info(
            "spatial_residual_diagnostics_written",
            output=spatial_output_path,
            segment_count=diagnostics.get("summary", {}).get("segment_count", 0),
            warn_segments=diagnostics.get("summary", {}).get("warn_segments", 0),
        )

    return count


def main(argv: Iterable[str] = None) -> int:
    parser = argparse.ArgumentParser(description="Update stratified conformal calibrators from JSONL samples.")
    defaults = load_app_config_safe()
    parser.add_argument("--input", required=True, help="Path to JSONL calibration samples")
    parser.add_argument(
        "--output",
        default=str(defaults.paths.calibration_path),
        help="Output calibration registry path",
    )
    parser.add_argument(
        "--coverage-report-output",
        default=None,
        help="Optional JSON output path for segmented coverage report",
    )
    parser.add_argument(
        "--spatial-diagnostics-output",
        default=None,
        help="Optional JSON output path for spatial residual drift/outlier diagnostics",
    )
    parser.add_argument("--alpha", type=float, default=defaults.valuation.conformal_alpha)
    parser.add_argument("--window-size", type=int, default=defaults.valuation.conformal_window)
    parser.add_argument(
        "--coverage-min-samples",
        type=int,
        default=20,
        help="Minimum samples per segment+horizon before coverage pass/fail evaluation",
    )
    parser.add_argument(
        "--coverage-floor",
        type=float,
        default=None,
        help="Coverage pass threshold (default: target_coverage - 0.05)",
    )
    parser.add_argument(
        "--spatial-min-samples",
        type=int,
        default=20,
        help="Minimum samples per spatial segment before drift/outlier flags are evaluated",
    )
    parser.add_argument(
        "--spatial-drift-threshold-pct",
        type=float,
        default=0.08,
        help="Absolute mean percentage residual threshold for spatial drift warning",
    )
    parser.add_argument(
        "--spatial-outlier-rate-threshold",
        type=float,
        default=0.15,
        help="Outlier-rate threshold for spatial outlier warning",
    )
    parser.add_argument(
        "--spatial-outlier-zscore",
        type=float,
        default=2.5,
        help="Residual z-score threshold used to count outliers",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    update_calibrators(
        input_path=args.input,
        output_path=args.output,
        coverage_output_path=args.coverage_report_output,
        spatial_output_path=args.spatial_diagnostics_output,
        alpha=args.alpha,
        window_size=args.window_size,
        coverage_min_samples=args.coverage_min_samples,
        coverage_floor=args.coverage_floor,
        spatial_min_samples=args.spatial_min_samples,
        spatial_drift_threshold_pct=args.spatial_drift_threshold_pct,
        spatial_outlier_rate_threshold=args.spatial_outlier_rate_threshold,
        spatial_outlier_zscore=args.spatial_outlier_zscore,
        app_config=defaults,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
