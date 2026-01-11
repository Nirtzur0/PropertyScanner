import pandas as pd
import numpy as np
import sqlite3
from typing import Dict, List, Tuple
from sklearn.ensemble import GradientBoostingRegressor
from datetime import datetime, timedelta
import structlog
from src.core.domain.schema import ValuationProjection

logger = structlog.get_logger(__name__)

class ForecastingService:
    """
    Probabilistic Forecasting Service.
    MVP: Uses GradientBoosting with Quantile Loss to project Market Indices.
    """
    def __init__(self, db_path: str = "data/listings.db"):
        self.db_path = db_path
        
    def _load_time_series(self, region_id: str) -> pd.DataFrame:
        """Load historical indices joined with macro indicators"""
        conn = sqlite3.connect(self.db_path)
        # Left join listings indices with macro data on month
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
        df = pd.read_sql(query, conn, params=(region_id,))
        conn.close()
        
        if df.empty: return df
        
        df['month_date'] = pd.to_datetime(df['month_date'])
        df['time_idx'] = df['month_date'].map(datetime.toordinal)
        
        # Forward fill any missing macro data (essential for robust ML)
        df['euribor_12m'] = df['euribor_12m'].ffill().fillna(3.0) # Default robust fallback
        df['ecb_deposit_rate'] = df['ecb_deposit_rate'].ffill().fillna(3.5)
        
        return df

    def forecast_property(self, region_id: str, current_value: float, horizons_months=[3, 6, 12]) -> List[ValuationProjection]:
        """
        Produce probabilistic forecasts using Local Trend + Macro Signals.
        """
        df = self._load_time_series(region_id)
        
        # Cold Start
        if len(df) < 5: # Need slightly more data for multivariate
            return self._heuristic_forecast(current_value, horizons_months)

        # Prepare Features: [Time, Euribor, Inventory]
        feature_cols = ['time_idx', 'euribor_12m', 'inventory_count']
        # Handle missing inventory
        df['inventory_count'] = df['inventory_count'].fillna(0)
        
        X = df[feature_cols].values
        y = df['price_index_sqm'].values
        
        # Train Quantile Regressors
        models = {}
        quantiles = [0.1, 0.5, 0.9]
        
        for q in quantiles:
            # More estimators for multivariate
            reg = GradientBoostingRegressor(loss='quantile', alpha=q, n_estimators=150, learning_rate=0.05, max_depth=4)
            reg.fit(X, y)
            models[q] = reg
            
        projections = []
        last_row = df.iloc[-1]
        last_date = last_row['month_date']
        current_index_val = last_row['price_index_sqm']
        
        # Future Macro Assumptions (Simple scenario logic)
        # In a real system, we would have a 'ScenarioGenerator' service
        # Here: Assume Euribor drops slightly (market consensus)
        current_euribor = last_row['euribor_12m']
        
        for h in horizons_months:
            future_date = last_date + timedelta(days=30*h)
            
            # Scenario: Euribor drops 0.25% per year
            future_euribor = max(1.5, current_euribor - (0.0025 * (h/12.0)))
            # Scenario: Inventory stable
            future_inventory = last_row['inventory_count']
            
            future_X = np.array([[future_date.toordinal(), future_euribor, future_inventory]])
            
            # Predict
            pred_q50 = models[0.5].predict(future_X)[0]
            pred_q10 = models[0.1].predict(future_X)[0]
            pred_q90 = models[0.9].predict(future_X)[0]
            
            # Growth Ratio
            if current_index_val > 0:
                growth_50 = pred_q50 / current_index_val
                growth_10 = pred_q10 / current_index_val
                growth_90 = pred_q90 / current_index_val
            else:
                growth_50 = 1.0
                growth_10 = 0.95
                growth_90 = 1.05
                
            # Apply to Property Value
            proj_val = current_value * growth_50
            
            # Annualized growth rate
            annual_rate = (growth_50 - 1) * (12/h)
            
            # Confidence: Inverse of spread width
            spread = (growth_90 - growth_10)
            confidence = max(0.1, 1.0 - spread)

            projections.append(ValuationProjection(
                years_future=h/12.0, # Approximate
                predicted_value=proj_val,
                confidence_score=confidence,
                growth_rate_annual=annual_rate,
                scenarios={
                    "pessimistic": current_value * growth_10,
                    "optimistic": current_value * growth_90,
                    "boom_regime": current_value * growth_90 * 1.05, # Simple heuristic for now
                    "bust_regime": current_value * growth_10 * 0.95
                }
            ))
            
        return projections

    def _heuristic_forecast(self, current_value: float, horizons_months: List[int]) -> List[ValuationProjection]:
        """Fallback for when we have no historical data"""
        projections = []
        for h in horizons_months:
            years = h / 12.0
            # Assume 3% inflation-like growth
            growth = 1.03 ** years
            projections.append(ValuationProjection(
                years_future=years,
                predicted_value=current_value * growth,
                confidence_score=0.1, # Low confidence
                growth_rate_annual=0.03,
                scenarios={
                    "pessimistic": current_value * (0.98 ** years),
                    "optimistic": current_value * (1.08 ** years)
                }
            ))
        return projections
