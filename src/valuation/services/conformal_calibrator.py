"""
Conformal Calibrator (SOTA V3)

Implements adaptive conformal prediction for calibrated prediction intervals.
Ensures that the prediction intervals have valid coverage over time.

Key Features:
- Per-horizon calibration (spot, 12m, 36m, 60m)
- Asymmetric widening (lower/upper separate)
- Monotonicity enforcement (q10 <= q50 <= q90)
- Coverage diagnostics per horizon

References:
- Conformal Time-Series Forecasting (NeurIPS 2021)
- Adaptive Conformal Inference (ICML 2022)
"""

import numpy as np
from typing import List, Tuple, Optional, Dict, Any
from statistics import NormalDist
from collections import deque
from dataclasses import dataclass, field
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CalibrationDiagnostics:
    """Diagnostics for a single calibrator"""
    coverage_rate: float
    target_coverage: float
    avg_interval_width: float
    n_samples: int
    lower_avg_error: float
    upper_avg_error: float


class ConformalCalibrator:
    """
    Adaptive conformal prediction for a single horizon.
    
    Maintains rolling windows of ASYMMETRIC residuals:
    - Lower errors: max(0, pred_q10 - actual)  # How much q10 was too high
    - Upper errors: max(0, actual - pred_q90)  # How much q90 was too low
    """
    
    def __init__(
        self,
        alpha: float = 0.1,  # Target miscoverage rate (1-alpha = coverage)
        window_size: int = 50,  # Rolling calibration window
        adapt_rate: float = 0.01,  # Learning rate for adaptive threshold
        horizon_name: str = "spot",  # For logging
    ):
        self.alpha = alpha
        self.window_size = window_size
        self.adapt_rate = adapt_rate
        self.horizon_name = horizon_name
        
        # ASYMMETRIC residuals
        self.lower_errors: deque = deque(maxlen=window_size)  # q10 too high
        self.upper_errors: deque = deque(maxlen=window_size)  # q90 too low
        self.median_errors: deque = deque(maxlen=window_size)  # |actual - q50|
        
        # Adaptive thresholds (separate for lower/upper)
        self.lower_threshold = 1.0
        self.upper_threshold = 1.0
    
    def update(
        self,
        actual: float,
        pred_q10: float,
        pred_q50: float,
        pred_q90: float
    ):
        """
        Update calibrator with new observation.
        
        Args:
            actual: Realized value
            pred_q10: Predicted 10th percentile
            pred_q50: Predicted median
            pred_q90: Predicted 90th percentile
        """
        # Compute ASYMMETRIC non-conformity scores
        lower_error = max(0, pred_q10 - actual)  # q10 was too high
        upper_error = max(0, actual - pred_q90)  # q90 was too low
        median_error = abs(actual - pred_q50)
        
        self.lower_errors.append(lower_error)
        self.upper_errors.append(upper_error)
        self.median_errors.append(median_error)
        
        # Check if actual was within interval
        covered = pred_q10 <= actual <= pred_q90
        
        # Adaptive update (online learning) - SEPARATE for lower/upper
        if lower_error > 0:
            # q10 was too high, need to lower it
            self.lower_threshold += self.adapt_rate * (1 - self.alpha)
        else:
            self.lower_threshold -= self.adapt_rate * self.alpha * 0.5
        
        if upper_error > 0:
            # q90 was too low, need to raise it
            self.upper_threshold += self.adapt_rate * (1 - self.alpha)
        else:
            self.upper_threshold -= self.adapt_rate * self.alpha * 0.5
        
        # Clamp thresholds
        self.lower_threshold = max(0.5, min(3.0, self.lower_threshold))
        self.upper_threshold = max(0.5, min(3.0, self.upper_threshold))
    
    def calibrate(
        self,
        pred_q10: float,
        pred_q50: float,
        pred_q90: float
    ) -> Tuple[float, float, float]:
        """
        Calibrate prediction interval with ASYMMETRIC widening.
        
        Args:
            pred_q10: Predicted 10th percentile
            pred_q50: Predicted median
            pred_q90: Predicted 90th percentile
            
        Returns:
            Tuple of (calibrated_q10, calibrated_q50, calibrated_q90)
        """
        if len(self.lower_errors) < 10:
            # Not enough data, return with monotonicity enforcement only
            return self._enforce_monotonicity(pred_q10, pred_q50, pred_q90)
        
        # Compute ASYMMETRIC calibration widths
        lower_errors_arr = np.array(list(self.lower_errors))
        upper_errors_arr = np.array(list(self.upper_errors))
        
        # Get the (1-alpha) quantile of each error distribution
        lower_calibration = np.quantile(lower_errors_arr, 1 - self.alpha)
        upper_calibration = np.quantile(upper_errors_arr, 1 - self.alpha)
        
        # Apply adaptive thresholds
        lower_calibration *= self.lower_threshold
        upper_calibration *= self.upper_threshold
        
        # Widen interval ASYMMETRICALLY
        calibrated_q10 = pred_q10 - lower_calibration
        calibrated_q90 = pred_q90 + upper_calibration
        
        # Enforce monotonicity
        return self._enforce_monotonicity(calibrated_q10, pred_q50, calibrated_q90)
    
    @staticmethod
    def _enforce_monotonicity(
        q10: float,
        q50: float,
        q90: float
    ) -> Tuple[float, float, float]:
        """
        Ensure q10 <= q50 <= q90 after calibration.
        """
        # If q10 > q50, set q10 = q50 - small margin
        if q10 > q50:
            q10 = q50 - abs(q50) * 0.01
        
        # If q90 < q50, set q90 = q50 + small margin
        if q90 < q50:
            q90 = q50 + abs(q50) * 0.01
        
        # Final check
        if q10 > q90:
            center = (q10 + q90) / 2
            half_range = max(abs(q90 - q10) / 2, abs(center) * 0.05)
            q10 = center - half_range
            q90 = center + half_range
        
        return q10, q50, q90
    
    def get_coverage_rate(self) -> float:
        """Compute empirical coverage rate"""
        if len(self.lower_errors) < 5:
            return 0.0
        
        # Coverage is when both lower_error == 0 AND upper_error == 0
        lower = np.array(list(self.lower_errors))
        upper = np.array(list(self.upper_errors))
        
        covered = (lower == 0) & (upper == 0)
        return float(covered.mean())
    
    def get_diagnostics(self) -> CalibrationDiagnostics:
        """Return calibration diagnostics"""
        lower_arr = np.array(list(self.lower_errors)) if self.lower_errors else np.array([0])
        upper_arr = np.array(list(self.upper_errors)) if self.upper_errors else np.array([0])
        median_arr = np.array(list(self.median_errors)) if self.median_errors else np.array([0])
        
        return CalibrationDiagnostics(
            coverage_rate=self.get_coverage_rate(),
            target_coverage=1 - self.alpha,
            avg_interval_width=float(np.mean(lower_arr + upper_arr)),
            n_samples=len(self.lower_errors),
            lower_avg_error=float(np.mean(lower_arr)),
            upper_avg_error=float(np.mean(upper_arr)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alpha": self.alpha,
            "window_size": self.window_size,
            "adapt_rate": self.adapt_rate,
            "horizon_name": self.horizon_name,
            "lower_errors": list(self.lower_errors),
            "upper_errors": list(self.upper_errors),
            "median_errors": list(self.median_errors),
            "lower_threshold": self.lower_threshold,
            "upper_threshold": self.upper_threshold,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ConformalCalibrator":
        cal = cls(
            alpha=payload.get("alpha", 0.1),
            window_size=payload.get("window_size", 50),
            adapt_rate=payload.get("adapt_rate", 0.01),
            horizon_name=payload.get("horizon_name", "spot"),
        )
        cal.lower_errors = deque(payload.get("lower_errors", []), maxlen=cal.window_size)
        cal.upper_errors = deque(payload.get("upper_errors", []), maxlen=cal.window_size)
        cal.median_errors = deque(payload.get("median_errors", []), maxlen=cal.window_size)
        cal.lower_threshold = payload.get("lower_threshold", 1.0)
        cal.upper_threshold = payload.get("upper_threshold", 1.0)
        return cal


class HorizonCalibratorRegistry:
    """
    Registry managing per-horizon conformal calibrators.
    
    Each horizon (spot, 12m, 36m, 60m) has its own calibrator because
    forecast uncertainty typically increases with horizon.
    """
    
    def __init__(
        self,
        horizons: List[int] = [0, 12, 36, 60],  # 0 = spot
        alpha: float = 0.1,
        window_size: int = 50,
    ):
        self.horizons = horizons
        self.alpha = alpha
        self.window_size = window_size
        
        # Create calibrator per horizon
        self._calibrators: Dict[int, ConformalCalibrator] = {}
        for h in horizons:
            horizon_name = "spot" if h == 0 else f"{h}m"
            self._calibrators[h] = ConformalCalibrator(
                alpha=alpha,
                window_size=window_size,
                horizon_name=horizon_name
            )
    
    def get_calibrator(self, horizon_months: int) -> ConformalCalibrator:
        """
        Get calibrator for a specific horizon.
        
        Args:
            horizon_months: Forecast horizon in months (0 = spot/today)
            
        Returns:
            ConformalCalibrator for that horizon
        """
        # Find closest registered horizon
        if horizon_months in self._calibrators:
            return self._calibrators[horizon_months]
        
        # Find nearest
        closest = min(self.horizons, key=lambda h: abs(h - horizon_months))
        return self._calibrators[closest]
    
    def update(
        self,
        horizon_months: int,
        actual: float,
        pred_q10: float,
        pred_q50: float,
        pred_q90: float
    ):
        """Update calibrator for specific horizon with new observation"""
        calibrator = self.get_calibrator(horizon_months)
        calibrator.update(actual, pred_q10, pred_q50, pred_q90)
    
    def calibrate_interval(
        self,
        pred_q10: float,
        pred_q50: float,
        pred_q90: float,
        horizon_months: int = 0,
        region_id: str = None  # For future regional calibration
    ) -> Tuple[float, float, float]:
        """
        Calibrate prediction interval for a specific horizon.
        
        Args:
            pred_q10: Raw predicted 10th percentile
            pred_q50: Raw predicted median
            pred_q90: Raw predicted 90th percentile
            horizon_months: Forecast horizon (0 = spot)
            region_id: Optional region for future regional calibration
            
        Returns:
            Tuple of (calibrated_q10, calibrated_q50, calibrated_q90)
        """
        calibrator = self.get_calibrator(horizon_months)
        return calibrator.calibrate(pred_q10, pred_q50, pred_q90)
    
    def get_all_diagnostics(self) -> Dict[str, CalibrationDiagnostics]:
        """Get diagnostics for all horizons"""
        return {
            f"{'spot' if h == 0 else f'{h}m'}": cal.get_diagnostics()
            for h, cal in self._calibrators.items()
        }
    
    def is_calibrated(self, horizon_months: int = 0, min_samples: int = 20) -> bool:
        """Check if we have enough data for reliable calibration"""
        calibrator = self.get_calibrator(horizon_months)
        return len(calibrator.lower_errors) >= min_samples

    def to_dict(self) -> Dict[str, Any]:
        return {
            "horizons": list(self._calibrators.keys()),
            "alpha": self.alpha,
            "window_size": self.window_size,
            "calibrators": {str(h): cal.to_dict() for h, cal in self._calibrators.items()},
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "HorizonCalibratorRegistry":
        horizons = [int(h) for h in payload.get("horizons", [0, 12, 36, 60])]
        registry = cls(
            horizons=horizons,
            alpha=payload.get("alpha", 0.1),
            window_size=payload.get("window_size", 50),
        )
        calibrators = payload.get("calibrators", {})
        for h_str, cal_payload in calibrators.items():
            try:
                h = int(h_str)
            except ValueError:
                continue
            registry._calibrators[h] = ConformalCalibrator.from_dict(cal_payload)
        return registry


class StratifiedCalibratorRegistry:
    """
    Bucketed calibrator registry for stratified coverage.

    Buckets are keyed by (region_id, property_type, price_tier).
    """
    def __init__(
        self,
        horizons: List[int] = [0, 12, 36, 60],
        alpha: float = 0.1,
        window_size: int = 50,
        price_tiers: Optional[List[float]] = None,
    ):
        self.horizons = horizons
        self.alpha = alpha
        self.window_size = window_size
        self.price_tiers = price_tiers or [150000, 300000, 600000, 1000000]
        self._registries: Dict[str, HorizonCalibratorRegistry] = {}
        self._bootstrap_scale = self._compute_bootstrap_scale()

    def _price_tier(self, price: float) -> str:
        for limit in self.price_tiers:
            if price <= limit:
                return f"<= {int(limit)}"
        return f"> {int(self.price_tiers[-1])}"

    def bucket_key(self, region_id: Optional[str], property_type: Optional[str], price: float) -> str:
        region = (region_id or "unknown").lower().strip()
        ptype = (property_type or "unknown").lower().strip()
        tier = self._price_tier(price)
        return f"{region}|{ptype}|{tier}"

    def _get_registry(self, key: str) -> HorizonCalibratorRegistry:
        if key not in self._registries:
            self._registries[key] = HorizonCalibratorRegistry(
                horizons=self.horizons,
                alpha=self.alpha,
                window_size=self.window_size,
            )
        return self._registries[key]

    def update(
        self,
        key: str,
        horizon_months: int,
        actual: float,
        pred_q10: float,
        pred_q50: float,
        pred_q90: float
    ):
        registry = self._get_registry(key)
        registry.update(horizon_months, actual, pred_q10, pred_q50, pred_q90)

    def calibrate_interval(
        self,
        key: str,
        pred_q10: float,
        pred_q50: float,
        pred_q90: float,
        horizon_months: int
    ) -> Tuple[float, float, float]:
        registry = self._get_registry(key)
        return registry.calibrate_interval(pred_q10, pred_q50, pred_q90, horizon_months=horizon_months)

    def is_calibrated(self, key: str, horizon_months: int = 0, min_samples: int = 20) -> bool:
        registry = self._get_registry(key)
        return registry.is_calibrated(horizon_months=horizon_months, min_samples=min_samples)

    def bootstrap_interval(
        self,
        key: str,
        pred_q10: float,
        pred_q50: float,
        pred_q90: float,
        horizon_months: int,
        *,
        min_uncertainty_pct: float = 0.08,
    ) -> Tuple[float, float, float]:
        _ = self._get_registry(key)
        if pred_q50 <= 0:
            return ConformalCalibrator._enforce_monotonicity(pred_q10, pred_q50, pred_q90)

        half_range = (pred_q90 - pred_q10) / 2
        min_half = abs(pred_q50) * max(0.0, float(min_uncertainty_pct))
        half_range = max(half_range, min_half)
        half_range *= self._bootstrap_scale

        cal_q10 = pred_q50 - half_range
        cal_q90 = pred_q50 + half_range
        return ConformalCalibrator._enforce_monotonicity(cal_q10, pred_q50, cal_q90)

    def _compute_bootstrap_scale(self) -> float:
        try:
            base_z = NormalDist().inv_cdf(0.9)
            target_z = NormalDist().inv_cdf(1 - self.alpha / 2)
            if base_z <= 0:
                return 1.0
            return max(1.0, target_z / base_z)
        except Exception:
            return 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "horizons": self.horizons,
            "alpha": self.alpha,
            "window_size": self.window_size,
            "price_tiers": self.price_tiers,
            "registries": {k: v.to_dict() for k, v in self._registries.items()},
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "StratifiedCalibratorRegistry":
        registry = cls(
            horizons=payload.get("horizons", [0, 12, 36, 60]),
            alpha=payload.get("alpha", 0.1),
            window_size=payload.get("window_size", 50),
            price_tiers=payload.get("price_tiers", [150000, 300000, 600000, 1000000]),
        )
        registries = payload.get("registries", {})
        for key, reg_payload in registries.items():
            registry._registries[key] = HorizonCalibratorRegistry.from_dict(reg_payload)
        return registry

    def save(self, path: str):
        import json
        with open(path, "w") as f:
            json.dump(self.to_dict(), f)

    @classmethod
    def load(cls, path: str) -> "StratifiedCalibratorRegistry":
        import json
        with open(path, "r") as f:
            payload = json.load(f)
        return cls.from_dict(payload)


class HierarchicalReconciler:
    """
    MinT-style hierarchical reconciliation.
    
    Ensures that barrio forecasts sum to city forecasts.
    
    Reference:
    - Wickramasuriya et al. "Optimal Forecast Reconciliation for Hierarchical and Grouped Time Series"
    """
    
    def __init__(self, hierarchy: dict):
        """
        Args:
            hierarchy: Dict mapping parent -> list of children
                       e.g. {"madrid": ["ezjmgu", "ezjmgv", ...]}
        """
        self.hierarchy = hierarchy
    
    def reconcile(
        self,
        forecasts: dict,  # {region_id: {q10, q50, q90}}
    ) -> dict:
        """
        Reconcile forecasts to ensure hierarchical consistency.
        
        For each parent node, child forecasts are adjusted so they sum
        to the parent forecast.
        
        Args:
            forecasts: Dict mapping region_id to quantile forecasts
            
        Returns:
            Reconciled forecasts
        """
        reconciled = {k: dict(v) for k, v in forecasts.items()}  # Deep copy
        
        for parent, children in self.hierarchy.items():
            if parent not in forecasts:
                continue
            
            parent_forecast = forecasts[parent]
            
            # Get child forecasts
            child_forecasts = [forecasts.get(c, {}) for c in children if c in forecasts]
            
            if not child_forecasts:
                continue
            
            # Compute sum of children for each quantile
            for q in ['q10', 'q50', 'q90']:
                child_sum = sum(cf.get(q, 0) for cf in child_forecasts)
                parent_val = parent_forecast.get(q, child_sum)
                
                if child_sum > 0 and parent_val > 0:
                    # Scale children proportionally to match parent
                    scale = parent_val / child_sum
                    
                    for i, child in enumerate(children):
                        if child in reconciled and q in child_forecasts[i]:
                            reconciled[child][q] = child_forecasts[i][q] * scale
        
        return reconciled


def enforce_monotonicity(q10: float, q50: float, q90: float) -> Tuple[float, float, float]:
    """
    Standalone function to enforce q10 <= q50 <= q90.
    
    Useful for post-processing any quantile predictions.
    """
    # Sort and reassign
    sorted_q = sorted([q10, q50, q90])
    return sorted_q[0], sorted_q[1], sorted_q[2]


if __name__ == "__main__":
    # Test per-horizon calibration
    registry = HorizonCalibratorRegistry(horizons=[0, 12, 36, 60])
    
    # Simulate training data
    np.random.seed(42)
    for _ in range(100):
        actual = np.random.normal(300000, 30000)
        pred_q50 = actual + np.random.normal(0, 15000)
        pred_q10 = pred_q50 - 45000
        pred_q90 = pred_q50 + 45000
        
        # Update spot calibrator
        registry.update(0, actual, pred_q10, pred_q50, pred_q90)
        
        # Update 12m with more noise
        actual_12m = actual * 1.03 + np.random.normal(0, 20000)
        pred_q50_12m = actual_12m + np.random.normal(0, 25000)
        registry.update(12, actual_12m, pred_q50_12m - 60000, pred_q50_12m, pred_q50_12m + 60000)
    
    # Print diagnostics
    print("=== Calibration Diagnostics ===")
    for horizon, diag in registry.get_all_diagnostics().items():
        print(f"\n{horizon}:")
        print(f"  Coverage: {diag.coverage_rate:.1%} (target: {diag.target_coverage:.1%})")
        print(f"  Avg width: {diag.avg_interval_width:,.0f}")
        print(f"  Lower err: {diag.lower_avg_error:,.0f}, Upper err: {diag.upper_avg_error:,.0f}")
    
    # Test calibration
    print("\n=== Test Calibration ===")
    raw = (255000, 300000, 345000)
    cal = registry.calibrate_interval(*raw, horizon_months=0)
    print(f"Spot: {raw} -> {tuple(f'{x:,.0f}' for x in cal)}")
    
    cal_12m = registry.calibrate_interval(*raw, horizon_months=12)
    print(f"12m:  {raw} -> {tuple(f'{x:,.0f}' for x in cal_12m)}")
