import sqlite3
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
import structlog
from src.core.domain.schema import MarketProfile, ValuationProjection, CanonicalListing
from src.services.eri_signals import ERISignalsService

logger = structlog.get_logger(__name__)


class MarketAnalyticsService:
    """
    Computes market trends, liquidity scores, and value projections.
    Implements the "Triple-Signal" approach.
    """
    def __init__(self, db_path: str = "data/listings.db"):
        self.db_path = db_path
        self.eri = ERISignalsService(db_path=db_path)

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

        if len(y) < 5 or np.std(y) < 1e-6 or np.std(X) < 1e-6:
            return 0.0, 0.0
        
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

        eri_signals = {}
        if listing.location and listing.location.city:
            eri_signals = self.eri.get_signals(
                listing.location.city.lower(),
                listing.updated_at if listing.updated_at else datetime.now()
            )

        if eri_signals:
            txn_z = eri_signals.get("txn_volume_z", 0.0)
            eri_liquidity = 1.0 / (1.0 + np.exp(-txn_z))
            liquidity = 0.5 * liquidity + 0.5 * eri_liquidity

            registral_change = eri_signals.get("registral_price_sqm_change")
            if registral_change is not None:
                growth_rate = 0.6 * registral_change + 0.4 * growth_rate
        
        # 3. Calculate Ripple (Simplistic: compare to city avg)
        # If this listing is in a cheaper zone but city is booming
        avg_price_sqm = zone_df['price_sqm'].mean()
        catchup = 0.0
        if listing.surface_area_sqm and listing.price:
            l_price_sqm = listing.price / listing.surface_area_sqm
            if l_price_sqm < avg_price_sqm * 0.8 and growth_rate > 0.02:
                # Cheaper than avg in a growing market -> High Catchup
                catchup = 0.8
        
        # 4. Projections (Handled by MarketDynamicsAgent via ForecastingService)
        projections = []

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
