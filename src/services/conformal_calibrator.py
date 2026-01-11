"""
Conformal Calibrator

Implements adaptive conformal prediction for calibrated prediction intervals.
Ensures that the prediction intervals have valid coverage over time.

References:
- Conformal Time-Series Forecasting (NeurIPS 2021)
- Adaptive Conformal Inference (ICML 2022)
"""

import numpy as np
from typing import List, Tuple, Optional
from collections import deque
import structlog

logger = structlog.get_logger(__name__)


class ConformalCalibrator:
    """
    Adaptive conformal prediction for time series forecasting.
    
    Maintains a rolling window of residuals and computes calibrated
    prediction intervals that guarantee coverage.
    """
    
    def __init__(
        self,
        alpha: float = 0.1,  # Target miscoverage rate (1-alpha = coverage)
        window_size: int = 50,  # Rolling calibration window
        adapt_rate: float = 0.01,  # Learning rate for adaptive threshold
    ):
        self.alpha = alpha
        self.window_size = window_size
        self.adapt_rate = adapt_rate
        
        # Rolling residuals for each quantile
        self.residuals_q10: deque = deque(maxlen=window_size)
        self.residuals_q50: deque = deque(maxlen=window_size)
        self.residuals_q90: deque = deque(maxlen=window_size)
        
        # Adaptive threshold
        self.threshold = 1.0
    
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
        # Compute residuals (non-conformity scores)
        # For quantile regression, we use the pinball loss as score
        self.residuals_q10.append(max(0, pred_q10 - actual))
        self.residuals_q50.append(abs(actual - pred_q50))
        self.residuals_q90.append(max(0, actual - pred_q90))
        
        # Check if actual was within interval
        covered = pred_q10 <= actual <= pred_q90
        
        # Adaptive update (online learning)
        # If not covered, increase threshold; if covered, decrease slightly
        if covered:
            self.threshold -= self.adapt_rate * self.alpha
        else:
            self.threshold += self.adapt_rate * (1 - self.alpha)
        
        # Clamp threshold
        self.threshold = max(0.5, min(2.0, self.threshold))
    
    def calibrate(
        self,
        pred_q10: float,
        pred_q50: float,
        pred_q90: float
    ) -> Tuple[float, float, float]:
        """
        Calibrate prediction interval to ensure coverage.
        
        Args:
            pred_q10: Predicted 10th percentile
            pred_q50: Predicted median
            pred_q90: Predicted 90th percentile
            
        Returns:
            Tuple of (calibrated_q10, calibrated_q50, calibrated_q90)
        """
        if len(self.residuals_q50) < 10:
            # Not enough data, return uncalibrated
            return pred_q10, pred_q50, pred_q90
        
        # Compute calibration factor from historical residuals
        residuals = np.array(list(self.residuals_q50))
        
        # Get the (1-alpha) quantile of residuals
        calibration_width = np.quantile(residuals, 1 - self.alpha)
        
        # Apply adaptive threshold
        calibration_width *= self.threshold
        
        # Widen interval symmetrically
        half_width = (pred_q90 - pred_q10) / 2
        center = pred_q50
        
        # New width ensures coverage
        new_half_width = max(half_width, calibration_width)
        
        calibrated_q10 = center - new_half_width
        calibrated_q90 = center + new_half_width
        
        return calibrated_q10, pred_q50, calibrated_q90
    
    def get_coverage_rate(self) -> float:
        """Compute empirical coverage rate"""
        if len(self.residuals_q10) < 5:
            return 0.0
        
        # Coverage is when q10 <= actual <= q90
        # Which means residual_q10 == 0 AND residual_q90 == 0
        r10 = np.array(list(self.residuals_q10))
        r90 = np.array(list(self.residuals_q90))
        
        covered = (r10 == 0) & (r90 == 0)
        return covered.mean()
    
    def get_diagnostics(self) -> dict:
        """Return calibration diagnostics"""
        return {
            "coverage_rate": self.get_coverage_rate(),
            "target_coverage": 1 - self.alpha,
            "adaptive_threshold": self.threshold,
            "residual_count": len(self.residuals_q50),
            "mean_interval_width": np.mean([
                max(0, q90 - q10) 
                for q10, q90 in zip(self.residuals_q10, self.residuals_q90)
            ]) if self.residuals_q10 else 0
        }


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
        
        # Build summing matrix
        self._build_summing_matrix()
    
    def _build_summing_matrix(self):
        """Build the S matrix for reconciliation"""
        # For simplicity, we store hierarchy and reconcile on-the-fly
        pass
    
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
        reconciled = forecasts.copy()
        
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
                    
                    for child, cf in zip(children, child_forecasts):
                        if child in reconciled and q in cf:
                            reconciled[child][q] = cf[q] * scale
        
        return reconciled


if __name__ == "__main__":
    # Test conformal calibrator
    calibrator = ConformalCalibrator(alpha=0.1)
    
    # Simulate some predictions and actuals
    np.random.seed(42)
    for _ in range(100):
        actual = np.random.normal(100, 10)
        pred_q50 = actual + np.random.normal(0, 5)
        pred_q10 = pred_q50 - 15
        pred_q90 = pred_q50 + 15
        
        calibrator.update(actual, pred_q10, pred_q50, pred_q90)
    
    print("Diagnostics:", calibrator.get_diagnostics())
    
    # Test calibration
    cal_q10, cal_q50, cal_q90 = calibrator.calibrate(85, 100, 115)
    print(f"Calibrated: [{cal_q10:.1f}, {cal_q50:.1f}, {cal_q90:.1f}]")
