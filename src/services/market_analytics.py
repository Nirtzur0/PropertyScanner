import sqlite3
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
import structlog
from src.core.domain.schema import MarketProfile, ValuationProjection, CanonicalListing

logger = structlog.get_logger(__name__)

class MarketAnalyticsService:
    """
    Computes market trends, liquidity scores, and value projections.
    Implements the "Triple-Signal" approach.
    """
    def __init__(self, db_path: str = "data/listings.db"):
        self.db_path = db_path
        self._init_stats_table()

    def _init_stats_table(self):
        """Create table for historical snapshots if not exists"""
        # Set timeout to wait for lock to release (bg crawler might be writing)
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_snapshots (
                id TEXT PRIMARY KEY, 
                zone_id TEXT, 
                date DATE, 
                avg_price_sqm FLOAT, 
                listing_count INT, 
                median_dom INT
            )
        """)
        conn.commit()
        conn.close()

    def _get_listings_df(self, city: str = None) -> pd.DataFrame:
        """Load listings into a DataFrame for vectorized analysis"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        query = "SELECT * FROM listings"
        if city:
            query += f" WHERE city = '{city}'"
        
        try:
            df = pd.read_sql(query, conn)
            # Ensure types
            df['price'] = pd.to_numeric(df['price'], errors='coerce')
            df['surface_area_sqm'] = pd.to_numeric(df['surface_area_sqm'], errors='coerce')
            df['listed_at'] = pd.to_datetime(df['listed_at'])
            
            # Derived
            df['price_sqm'] = df['price'] / df['surface_area_sqm']
            
            return df
        except Exception as e:
            logger.error("dataframe_load_failed", error=str(e))
            return pd.DataFrame()
        finally:
            conn.close()

    def calculate_momentum(self, df_zone: pd.DataFrame) -> Tuple[float, float]:
        """
        Signal A: Temporal Trend.
        Returns (Annual_Growth_Rate, Confidence)
        Using simple linear regression on price_sqm ~ time.
        """
        if len(df_zone) < 5:
            return 0.0, 0.0
            
        df_clean = df_zone.dropna(subset=['price_sqm', 'listed_at']).sort_values('listed_at')
        if df_clean.empty:
             return 0.0, 0.0
             
        # Convert dates to ordinal for regression
        df_clean['date_ord'] = df_clean['listed_at'].map(datetime.toordinal)
        
        X = df_clean['date_ord'].values.reshape(-1, 1)
        y = df_clean['price_sqm'].values
        
        # Simple Linear Regression
        # Slope = change in price per day
        try:
            # Center X to avoid large numbers
            X_mean = X.mean()
            slope, intercept = np.polyfit((X - X_mean).flatten(), y, 1)
            
            # Annualize
            annual_change_sqm = slope * 365
            current_avg = y.mean()
            growth_rate = annual_change_sqm / current_avg if current_avg > 0 else 0
            
            # Confidence based on R-squared or just sample size for now
            confidence = min(len(df_clean) / 50.0, 0.9) # Max 0.9 confidence if > 50 samples
            
            return growth_rate, confidence
        except:
            return 0.0, 0.0

    def calculate_liquidity(self, df_zone: pd.DataFrame) -> float:
        """
        Signal C: Liquidity Score (0.0 - 1.0)
        Based on Days on Market (proxy: time since listed for active, or actual DOM if we tracked sold).
        For now, we use 'age of active listings' as inverse proxy.
        Older active listings = Lower Liquidity.
        """
        if df_zone.empty:
            return 0.5
            
        now = datetime.now()
        df_zone['age_days'] = (now - df_zone['listed_at']).dt.days
        median_age = df_zone['age_days'].median()
        
        # Heuristic: 
        # < 30 days med age = High Liquidity (1.0)
        # > 180 days med age = Low Liquidity (0.0)
        if pd.isna(median_age): return 0.5
        
        score = max(0.0, min(1.0, 1.0 - (median_age - 30) / 150.0))
        return score

    def analyze_listing(self, listing: CanonicalListing) -> MarketProfile:
        """
        Main entry point. Analyzes market for a specific listing.
        """
        # 1. Define Zone (Cluster)
        # For now, simple clustering by City + approx Latitude (primitive tiling)
        # In prod, use H3 or Geohash
        df = self._get_listings_df(city=listing.location.city if listing.location else None)
        
        if df.empty:
            return MarketProfile(
                zone_id="unknown", momentum_score=0, liquidity_score=0, catchup_potential=0, avg_price_sqm=0, inventory_trend="stable"
            )

        # Filter by proximity (simulated by lat/lon box if available, else city wide)
        # Using a simplistic "zone" for now
        zone_df = df # entire city for now to ensure data volume
        
        # 2. Calculate Signals
        growth_rate, confidence = self.calculate_momentum(zone_df)
        liquidity = self.calculate_liquidity(zone_df)
        
        # 3. Calculate Ripple (Simplistic: compare to city avg)
        # If this listing is in a cheaper zone but city is booming
        avg_price_sqm = zone_df['price_sqm'].mean()
        catchup = 0.0
        if listing.surface_area_sqm and listing.price:
            l_price_sqm = listing.price / listing.surface_area_sqm
            if l_price_sqm < avg_price_sqm * 0.8 and growth_rate > 0.02:
                # Cheaper than avg in a growing market -> High Catchup
                catchup = 0.8
        
        # 4. Projections
        projections = []
        current_val = listing.price
        
        for year in [1, 3, 5]:
            # Compound growth
            future_val = current_val * ((1 + growth_rate) ** year)
            projections.append(ValuationProjection(
                years_future=year,
                predicted_value=future_val,
                confidence_score=confidence * (0.9 ** year), # decay confidence
                growth_rate_annual=growth_rate,
                scenarios={
                    "pessimistic": future_val * 0.9,
                    "optimistic": future_val * 1.1
                }
            ))

        return MarketProfile(
            zone_id=listing.location.city if listing.location else "unknown",
            momentum_score=growth_rate,
            liquidity_score=liquidity,
            catchup_potential=catchup,
            avg_price_sqm=float(avg_price_sqm) if not pd.isna(avg_price_sqm) else 0.0,
            median_dom=int(zone_df['age_days'].median()) if 'age_days' in zone_df else 0,
            inventory_trend="stable", # placeholder
            projections=projections
        )
