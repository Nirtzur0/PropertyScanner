import argparse
import json
from typing import Dict, Any, Iterable, Optional

import structlog

from src.platform.settings import AppConfig
from src.valuation.services.conformal_calibrator import StratifiedCalibratorRegistry
from src.platform.utils.config import load_app_config_safe

logger = structlog.get_logger(__name__)


def _iter_samples(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def update_calibrators(
    *,
    input_path: str,
    output_path: Optional[str] = None,
    alpha: float = 0.1,
    window_size: int = 50,
    app_config: Optional[AppConfig] = None,
) -> int:
    app_config = app_config or load_app_config_safe()
    if output_path is None:
        output_path = str(app_config.paths.calibration_path)
    registry = StratifiedCalibratorRegistry(alpha=alpha, window_size=window_size)

    count = 0
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
        count += 1

    registry.save(output_path)
    logger.info("calibration_updated", samples=count, output=output_path)
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
    parser.add_argument("--alpha", type=float, default=defaults.valuation.conformal_alpha)
    parser.add_argument("--window-size", type=int, default=defaults.valuation.conformal_window)
    args = parser.parse_args(list(argv) if argv is not None else None)

    update_calibrators(
        input_path=args.input,
        output_path=args.output,
        alpha=args.alpha,
        window_size=args.window_size,
        app_config=defaults,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
