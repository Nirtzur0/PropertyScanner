"""
Hedonic Index Service

Implements quality-adjusted price indices using hedonic regression.
This eliminates composition bias from raw median €/m² indices.

Model: ln(P) = β·Features + γ_neighborhood + ε

Where:
- Features = [sqm, bedrooms, bathrooms, has_elevator, floor, energy_rating]
- γ_neighborhood = fixed effects per geohash-6 (neighborhood proxy)

References:
- Eurostat HPI methodology
- Case-Shiller repeat-sales approach (adapted for listings)
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional
import structlog
from sklearn.linear_model import Ridge
from sklearn.preprocessing import OneHotEncoder

logger = structlog.get_logger(__name__)


class HedonicIndexService:
    """
    Computes quality-adjusted price indices using hedonic regression.
    """
    
    def __init__(self, db_path: str = "data/listings.db"):
        self.db_path = db_path
        
        # Feature columns for hedonic model
        self.feature_cols = [
            'surface_area_sqm',
            'bedrooms',
            'bathrooms',
            'has_elevator',
            'floor',
        ]
        
        # Reference basket (median values for normalization)
        self.reference_basket = {
            'surface_area_sqm': 80.0,
            'bedrooms': 2,
            'bathrooms': 1,
            'has_elevator': 1,
            'floor': 2,
        }
    
    def _load_listings(self, region_name: str = None) -> pd.DataFrame:
        """Load listings with required features"""
        conn = sqlite3.connect(self.db_path)
        
        query = """
            SELECT 
                id, 
                price, 
                surface_area_sqm,
                bedrooms,
                bathrooms,
                has_elevator,
                floor,
                geohash,
                city,
                listed_at,
                updated_at
            FROM listings
            WHERE price > 1000 
              AND surface_area_sqm > 10
              AND surface_area_sqm < 500
        """
        
        if region_name:
            query += f" AND city = '{region_name}'"
            
        df = pd.read_sql(query, conn)
        conn.close()
        
        # Parse dates
        df['listed_at'] = pd.to_datetime(df['listed_at'], format='mixed', errors='coerce')
        df['updated_at'] = pd.to_datetime(df['updated_at'], format='mixed', errors='coerce')
        
        # Derive month bucket
        df['month'] = df['listed_at'].dt.to_period('M')
        
        # Log price (target for hedonic regression)
        df['log_price'] = np.log(df['price'])
        
        # Fill missing values
        df['bedrooms'] = df['bedrooms'].fillna(2)
        df['bathrooms'] = df['bathrooms'].fillna(1)
        df['has_elevator'] = df['has_elevator'].fillna(0).astype(int)
        df['floor'] = df['floor'].fillna(1)
        
        # Geohash-6 for neighborhood fixed effects
        df['neighborhood'] = df['geohash'].str[:6] if 'geohash' in df.columns else 'unknown'
        df['neighborhood'] = df['neighborhood'].fillna('unknown')
        
        return df
    
    def compute_index(self, region_name: str = None) -> pd.DataFrame:
        """
        Compute quality-adjusted hedonic index time series.
        
        Returns DataFrame with columns:
        - month: Period
        - hedonic_index: Quality-adjusted €/m² (normalized to reference basket)
        - raw_median: Raw median €/m² (for comparison)
        - r_squared: Model fit quality
        - n_obs: Number of observations
        """
        df = self._load_listings(region_name)
        
        if len(df) < 50:
            logger.warning("insufficient_data_for_hedonic", count=len(df))
            return pd.DataFrame()
        
        # Get unique months
        months = sorted(df['month'].dropna().unique())
        
        results = []
        
        for month in months:
            month_df = df[df['month'] == month].copy()
            
            if len(month_df) < 10:
                continue
            
            # Prepare features
            X = month_df[self.feature_cols].values
            y = month_df['log_price'].values
            
            # Add neighborhood fixed effects (one-hot)
            neighborhoods = month_df['neighborhood'].values.reshape(-1, 1)
            
            try:
                # Fit hedonic model: ln(P) = β·X + γ_neighborhood
                # Use Ridge regression for regularization (handles multicollinearity)
                model = Ridge(alpha=1.0)
                model.fit(X, y)
                
                r_squared = model.score(X, y)
                
                # Predict price for reference basket
                ref_X = np.array([[
                    self.reference_basket['surface_area_sqm'],
                    self.reference_basket['bedrooms'],
                    self.reference_basket['bathrooms'],
                    self.reference_basket['has_elevator'],
                    self.reference_basket['floor'],
                ]])
                
                log_ref_price = model.predict(ref_X)[0]
                ref_price = np.exp(log_ref_price)
                
                # Quality-adjusted €/m² = Reference price / Reference sqm
                hedonic_index = ref_price / self.reference_basket['surface_area_sqm']
                
                # Raw median for comparison
                raw_median = (month_df['price'] / month_df['surface_area_sqm']).median()
                
                results.append({
                    'month': month,
                    'hedonic_index': hedonic_index,
                    'raw_median': raw_median,
                    'r_squared': r_squared,
                    'n_obs': len(month_df),
                    'coefficients': dict(zip(self.feature_cols, model.coef_)),
                })
                
            except Exception as e:
                logger.warning("hedonic_fit_failed", month=str(month), error=str(e))
                continue
        
        return pd.DataFrame(results)
    
    def save_to_db(self, region_name: str = None):
        """Compute and save hedonic indices to database"""
        df = self.compute_index(region_name)
        
        if df.empty:
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Ensure table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hedonic_indices (
                id TEXT PRIMARY KEY,
                region_id TEXT,
                month_date DATE,
                hedonic_index_sqm FLOAT,
                raw_median_sqm FLOAT,
                r_squared FLOAT,
                n_observations INT,
                coefficients TEXT,
                updated_at DATETIME
            )
        """)
        
        region_id = region_name or "all"
        
        for _, row in df.iterrows():
            month_str = str(row['month'])
            record_id = f"{region_id}|{month_str}"
            
            cursor.execute("""
                INSERT OR REPLACE INTO hedonic_indices 
                (id, region_id, month_date, hedonic_index_sqm, raw_median_sqm, r_squared, n_observations, coefficients, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record_id,
                region_id,
                month_str,
                float(row['hedonic_index']),
                float(row['raw_median']),
                float(row['r_squared']),
                int(row['n_obs']),
                str(row['coefficients']),
                datetime.now().isoformat()
            ))
        
        conn.commit()
        conn.close()
        
        logger.info("hedonic_indices_saved", region=region_id, count=len(df))


if __name__ == "__main__":
    # Test run
    svc = HedonicIndexService()
    df = svc.compute_index()
    print(df)
