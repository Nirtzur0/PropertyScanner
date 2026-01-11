
import sqlite3
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import structlog

logger = structlog.get_logger(__name__)

class HedonicIndexService:
    """
    Computes Quality-Adjusted Price Indices using Time-Dummy Hedonic Regression.
    Model: ln(Price) ~ Size + Beds + Baths + Elevator + Geohash(Fixed Effects) + Time(Dummies)
    """
    def __init__(self, db_path: str = "data/listings.db"):
        self.db_path = db_path
        
    def compute_index(self, region_type="city", region_name="madrid") -> pd.DataFrame:
        """
        Returns a DataFrame with ['month', 'price_index']
        """
        conn = sqlite3.connect(self.db_path)
        
        # 1. Load Data
        query = """
            SELECT price, surface_area_sqm, bedrooms, bathrooms, has_elevator, 
                   listed_at, geohash
            FROM listings 
            WHERE city = ? 
              AND price > 5000 
              AND surface_area_sqm > 15
        """
        try:
            df = pd.read_sql(query, conn, params=(region_name,))
        except Exception as e:
            logger.error("hedonic_load_failed", error=str(e))
            return pd.DataFrame()
        finally:
            conn.close()
            
        if len(df) < 5: # Not enough data
            return pd.DataFrame()
            
        # 2. Preprocessing
        df['listed_at'] = pd.to_datetime(df['listed_at'], format='mixed', errors='coerce')
        df['month'] = df['listed_at'].dt.to_period('M')
        df['log_price'] = np.log(df['price'])
        
        # Handle Missing
        df['bedrooms'] = df['bedrooms'].fillna(2)
        df['bathrooms'] = df['bathrooms'].fillna(1)
        df['has_elevator'] = df['has_elevator'].fillna(False).astype(int)
        df['surface_area_sqm'] = df['surface_area_sqm'].fillna(df['surface_area_sqm'].median())
        
        # 3. Features & Dummies
        # Spatial Fixed Effects: Use first 5 chars of geohash (Neighborhood scale)
        df['gh_short'] = df['geohash'].astype(str).str[:5]
        
        # One-Hot Encoding
        X = pd.get_dummies(df[['month', 'gh_short']], drop_first=True)
        # Add numeric features
        X['surface_area_sqm'] = df['surface_area_sqm']
        X['bedrooms'] = df['bedrooms']
        X['bathrooms'] = df['bathrooms']
        X['has_elevator'] = df['has_elevator']
        
        y = df['log_price']
        
        # 4. Regression
        model = LinearRegression()
        model.fit(X, y)
        
        # 5. Extract Index
        # Find columns starting with 'month_'
        month_cols = [c for c in X.columns if str(c).startswith('month_')]
        
        index_data = []
        base_price_log = model.intercept_ # Baseline (Reference Month + Reference Area + 0 size)
        # This intercept interpretation is tricky with continuous vars, 
        # so we usually normalize to the first period = 100.
        
        # Let's reconstitute the time curve
        # Get period names
        periods = sorted(df['month'].unique())
        reference_period = periods[0] # The one dropped by drop_first=True
        
        # Base value (100)
        index_data.append({
            "month": str(reference_period),
            "hedonic_index": 100.0
        })
        
        for p in periods[1:]:
            col_name = f"month_{p}"
            if col_name in X.columns:
                coef = model.coef_[list(X.columns).index(col_name)]
                # Index value = 100 * exp(coef)
                val = 100.0 * np.exp(coef)
                index_data.append({
                    "month": str(p),
                    "hedonic_index": val
                })
        
        return pd.DataFrame(index_data)

if __name__ == "__main__":
    svc = HedonicIndexService()
    df = svc.compute_index(region_name="madrid")
    print(df)
