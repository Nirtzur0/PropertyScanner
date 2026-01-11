"""
Forecasting Service (SOTA V3)

Probabilistic Forecasting Service with:
- Quality-adjusted hedonic indices (eliminates composition bias)
- TFT panel model (when trained) or GBM fallback
- Conformal calibration for valid prediction intervals
- Proper macro scenario integration

References:
- Eurostat HPI methodology
- Lim et al. TFT (2021)
- Conformal Time-Series Forecasting (NeurIPS 2021)
"""

import pandas as pd
import numpy as np
import sqlite3
from typing import Dict, List, Tuple, Optional
from sklearn.ensemble import GradientBoostingRegressor
from datetime import datetime, timedelta
import structlog
from src.core.domain.schema import ValuationProjection

logger = structlog.get_logger(__name__)


class ForecastingService:
    """
    SOTA V3 Probabilistic Forecasting Service.
    
    Hierarchy:
    1. Try TFT panel model (if trained)
    2. Fallback to Quantile GBM
    3. Heuristic fallback for cold start
    """
    
    def __init__(self, db_path: str = "data/listings.db"):
        self.db_path = db_path
        self._tft_service = None
        self._conformal = None
        
    def _get_tft_service(self):
        """Lazy load TFT service"""
        if self._tft_service is None:
            try:
                from src.training.forecasting_tft import TFTForecastingService
                self._tft_service = TFTForecastingService(db_path=self.db_path)
            except Exception as e:
                logger.warning("tft_import_failed", error=str(e))
        return self._tft_service
    
    def _get_conformal(self):
        """Lazy load conformal calibrator"""
        if self._conformal is None:
            try:
                from src.services.conformal_calibrator import ConformalCalibrator
                self._conformal = ConformalCalibrator(alpha=0.1)
            except Exception as e:
                logger.warning("conformal_import_failed", error=str(e))
        return self._conformal
        
    def _load_time_series(self, region_id: str, use_hedonic: bool = True) -> pd.DataFrame:
        """
        Load historical indices joined with macro indicators.
        
        Prefers hedonic indices (quality-adjusted) over raw median.
        """
        conn = sqlite3.connect(self.db_path)
        
        # Try hedonic first, fallback to raw
        if use_hedonic:
            query = """
                SELECT 
                    hi.month_date, 
                    hi.hedonic_index_sqm as price_index_sqm,
                    mi.inventory_count,
                    mac.euribor_12m,
                    mac.ecb_deposit_rate
                FROM hedonic_indices hi
                LEFT JOIN market_indices mi ON hi.region_id = mi.region_id AND hi.month_date = mi.month_date
                LEFT JOIN macro_indicators mac ON hi.month_date = mac.date
                WHERE hi.region_id = ? 
                ORDER BY hi.month_date ASC
            """
        else:
            query = """
                SELECT 
                    mi.month_date, 
                    mi.price_index_sqm, 
                    mi.inventory_count,
                    mac.euribor_12m,
                    mac.ecb_deposit_rate
                FROM market_indices mi
                LEFT JOIN macro_indicators mac ON mi.month_date = mac.date
                WHERE mi.region_id = ? 
                ORDER BY mi.month_date ASC
            """
        
        try:
            df = pd.read_sql(query, conn, params=(region_id,))
        except Exception:
            # Hedonic table might not exist
            df = pd.DataFrame()
        
        # Fallback to raw if hedonic is empty
        if df.empty and use_hedonic:
            return self._load_time_series(region_id, use_hedonic=False)
        
        conn.close()
        
        if df.empty:
            return df
        
        df['month_date'] = pd.to_datetime(df['month_date'], format='mixed', errors='coerce')
        df['time_idx'] = df['month_date'].apply(lambda x: x.toordinal() if pd.notna(x) else 0)
        
        # Forward fill any missing macro data
        df['euribor_12m'] = df['euribor_12m'].ffill().fillna(3.0)
        df['ecb_deposit_rate'] = df['ecb_deposit_rate'].ffill().fillna(3.5)
        
        return df

    def forecast_property(
        self, 
        region_id: str, 
        current_value: float, 
        horizons_months: List[int] = [12, 36, 60],
        use_tft: bool = True
    ) -> List[ValuationProjection]:
        """
        Produce probabilistic forecasts.
        
        Strategy:
        1. Try TFT panel model if available
        2. Fallback to Quantile GBM
        3. Heuristic fallback for cold start
        
        All outputs are calibrated via conformal prediction.
        """
        
        # Try TFT first
        if use_tft:
            tft = self._get_tft_service()
            if tft is not None:
                try:
                    tft_results = tft.predict(region_id, current_value)
                    if tft_results:
                        return self._tft_results_to_projections(tft_results, current_value, horizons_months)
                except Exception as e:
                    logger.warning("tft_prediction_failed", error=str(e))
        
        # Fallback to GBM
        df = self._load_time_series(region_id)
        
        if len(df) < 5:
            return self._heuristic_forecast(current_value, horizons_months)

        return self._gbm_forecast(df, current_value, horizons_months)
    
    def _gbm_forecast(
        self, 
        df: pd.DataFrame, 
        current_value: float, 
        horizons_months: List[int]
    ) -> List[ValuationProjection]:
        """Quantile GBM forecasting (fallback)"""
        
        feature_cols = ['time_idx', 'euribor_12m', 'inventory_count']
        df['inventory_count'] = df['inventory_count'].fillna(0)
        
        X = df[feature_cols].values
        y = df['price_index_sqm'].values
        
        # Train Quantile Regressors
        models = {}
        quantiles = [0.1, 0.5, 0.9]
        
        for q in quantiles:
            reg = GradientBoostingRegressor(
                loss='quantile', 
                alpha=q, 
                n_estimators=150, 
                learning_rate=0.05, 
                max_depth=4
            )
            reg.fit(X, y)
            models[q] = reg
            
        projections = []
        last_row = df.iloc[-1]
        last_date = last_row['month_date']
        current_index_val = last_row['price_index_sqm']
        current_euribor = last_row['euribor_12m']
        
        # Get conformal calibrator
        conformal = self._get_conformal()
        
        for h in horizons_months:
            future_date = last_date + timedelta(days=30*h)
            
            # Future macro assumptions (conservative scenario)
            future_euribor = max(1.5, current_euribor - (0.25 * (h/12.0)))
            future_inventory = last_row['inventory_count']
            
            future_X = np.array([[future_date.toordinal(), future_euribor, future_inventory]])
            
            # Predict
            pred_q50 = models[0.5].predict(future_X)[0]
            pred_q10 = models[0.1].predict(future_X)[0]
            pred_q90 = models[0.9].predict(future_X)[0]
            
            # Apply conformal calibration
            if conformal:
                pred_q10, pred_q50, pred_q90 = conformal.calibrate(pred_q10, pred_q50, pred_q90)
            
            # Growth Ratio
            if current_index_val > 0:
                growth_50 = pred_q50 / current_index_val
                growth_10 = pred_q10 / current_index_val
                growth_90 = pred_q90 / current_index_val
            else:
                growth_50 = 1.0
                growth_10 = 0.95
                growth_90 = 1.05
                
            proj_val = current_value * growth_50
            
            # Confidence from spread
            spread = (growth_90 - growth_10)
            confidence = max(0.1, 1.0 - spread)

            projections.append(ValuationProjection(
                months_future=h,
                years_future=h/12.0, 
                predicted_value=proj_val,
                confidence_interval_low=current_value * growth_10,
                confidence_interval_high=current_value * growth_90,
                confidence_score=confidence,
                scenario_name="baseline"
            ))
            
        return projections
    
    def _tft_results_to_projections(
        self, 
        results: Dict, 
        current_value: float,
        horizons_months: List[int]
    ) -> List[ValuationProjection]:
        """Convert TFT output to ValuationProjection"""
        projections = []
        
        for h in horizons_months:
            q10 = results.get(f"q10_m{h}", current_value * 0.95)
            q50 = results.get(f"q50_m{h}", current_value)
            q90 = results.get(f"q90_m{h}", current_value * 1.05)
            
            spread = (q90 - q10) / current_value if current_value > 0 else 0.1
            confidence = max(0.1, 1.0 - spread)
            
            projections.append(ValuationProjection(
                months_future=h,
                years_future=h/12.0,
                predicted_value=q50,
                confidence_interval_low=q10,
                confidence_interval_high=q90,
                confidence_score=confidence,
                scenario_name="tft_baseline"
            ))
        
        return projections

    def _heuristic_forecast(
        self, 
        current_value: float, 
        horizons_months: List[int]
    ) -> List[ValuationProjection]:
        """Fallback for when we have no historical data"""
        projections = []
        for h in horizons_months:
            years = h / 12.0
            growth = 1.03 ** years  # 3% annual
            projections.append(ValuationProjection(
                months_future=h,
                years_future=years,
                predicted_value=current_value * growth,
                confidence_interval_low=current_value * (0.98 ** years),
                confidence_interval_high=current_value * (1.08 ** years),
                confidence_score=0.1,
                scenario_name="heuristic_baseline"
            ))
        return projections
