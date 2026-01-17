"""
Hedonic Index Service (SOTA V3)

Implements quality-adjusted price indices using hedonic regression.
This eliminates composition bias from raw median €/m² indices.

Model: ln(P) = β·Features + γ_neighborhood + ε

Where:
- Features = [sqm, bedrooms, bathrooms, has_elevator, floor]
- γ_neighborhood = fixed effects per geohash-6 (one-hot encoded)

Key Methods:
- get_index(region_id, month_date) -> float
- compute_adjustment_factor(region_id, comp_timestamp, target_timestamp) -> float

References:
- Eurostat HPI methodology
- Case-Shiller repeat-sales approach (adapted for listings)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import structlog
from sklearn.linear_model import Ridge
from dataclasses import dataclass
from src.platform.config import DEFAULT_DB_PATH
from src.platform.db.base import resolve_db_url
from src.market.repositories.hedonic_indices import HedonicIndicesRepository
from src.listings.repositories.listings import ListingsRepository
from src.platform.storage import StorageService

logger = structlog.get_logger(__name__)


@dataclass
class IndexResult:
    """Result from hedonic index query with metadata"""
    value: float
    r_squared: float
    n_observations: int
    is_fallback: bool = False
    fallback_reason: Optional[str] = None


class HedonicIndexService:
    """
    Computes quality-adjusted price indices using hedonic regression.
    
    Provides time-adjustment API for comp price normalization.
    """
    
    def __init__(
        self,
        db_path: str = str(DEFAULT_DB_PATH),
        db_url: Optional[str] = None,
        storage: Optional[StorageService] = None,
    ):
        self.db_url = resolve_db_url(db_url=db_url, db_path=db_path)
        self.storage = storage or StorageService(db_url=self.db_url)
        self.listings_repo = ListingsRepository(storage=self.storage)
        self.repo = HedonicIndicesRepository(storage=self.storage)
        
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
        
        # Cache for loaded indices
        self._index_cache: Dict[str, pd.DataFrame] = {}
    
    def _load_listings(self, region_name: str = None) -> pd.DataFrame:
        """Load listings with required features"""
        df = self.listings_repo.load_listings_for_hedonic(region_name)
        
        # Parse dates
        df['listed_at'] = pd.to_datetime(df['listed_at'], format='mixed', errors='coerce')
        df['updated_at'] = pd.to_datetime(df['updated_at'], format='mixed', errors='coerce')
        
        # Derive month bucket
        df['month'] = df['listed_at'].dt.to_period('M')
        
        # Log price (target for hedonic regression)
        df['log_price'] = np.log(df['price'])
        
        # Fill missing values with reasonable defaults
        df['bedrooms'] = pd.to_numeric(df['bedrooms'], errors='coerce').fillna(2)
        df['bathrooms'] = pd.to_numeric(df['bathrooms'], errors='coerce').fillna(1)
        df['has_elevator'] = pd.to_numeric(df['has_elevator'], errors='coerce').fillna(0).astype(int)
        df['floor'] = pd.to_numeric(df['floor'], errors='coerce').fillna(1)
        
        # Geohash-6 for neighborhood fixed effects
        if 'geohash' in df.columns and df['geohash'].notna().any():
            df['neighborhood'] = df['geohash'].str[:6].fillna('unknown')
        else:
            df['neighborhood'] = 'unknown'
        
        return df
    
    def compute_index(self, region_name: str = None) -> pd.DataFrame:
        """
        Compute quality-adjusted hedonic index time series.
        
        Includes actual neighborhood fixed effects via one-hot encoding.
        
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
            
            # Prepare base features
            X_base = month_df[self.feature_cols].values
            y = month_df['log_price'].values
            
            # Add neighborhood fixed effects (one-hot encoding)
            neighborhoods = month_df['neighborhood'].values
            unique_neighborhoods = np.unique(neighborhoods)
            
            # Only add FE if we have multiple neighborhoods
            if len(unique_neighborhoods) > 1:
                # Create one-hot encoding (drop_first to avoid multicollinearity)
                neighborhood_dummies = pd.get_dummies(
                    month_df['neighborhood'], 
                    prefix='nh',
                    drop_first=True
                ).values
                X = np.hstack([X_base, neighborhood_dummies])
            else:
                X = X_base
            
            try:
                # Fit hedonic model: ln(P) = β·X + γ_neighborhood
                # Ridge regularization handles multicollinearity from FE
                model = Ridge(alpha=1.0)
                model.fit(X, y)
                
                r_squared = model.score(X, y)
                
                # Predict price for reference basket (no neighborhood effect)
                ref_X = np.array([[
                    self.reference_basket['surface_area_sqm'],
                    self.reference_basket['bedrooms'],
                    self.reference_basket['bathrooms'],
                    self.reference_basket['has_elevator'],
                    self.reference_basket['floor'],
                ]])
                
                # Pad with zeros for neighborhood dummies
                if X.shape[1] > len(self.feature_cols):
                    n_dummies = X.shape[1] - len(self.feature_cols)
                    ref_X = np.hstack([ref_X, np.zeros((1, n_dummies))])
                
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
                    'n_neighborhoods': len(unique_neighborhoods),
                    'coefficients': dict(zip(self.feature_cols, model.coef_[:len(self.feature_cols)])),
                })
                
            except Exception as e:
                logger.warning("hedonic_fit_failed", month=str(month), error=str(e))
                continue
        
        return pd.DataFrame(results)
    
    # =========================================================================
    # TIME-ADJUSTMENT API (for comp price normalization)
    # =========================================================================
    
    def get_index(self, region_id: str, month_date: str) -> IndexResult:
        """
        Get hedonic index value for a specific region and month.

        Args:
            region_id: City name or geohash prefix
            month_date: Month string in format "YYYY-MM" or "YYYY-MM-DD"
            
        Returns:
            IndexResult with value and metadata
        """
        # Normalize month to "YYYY-MM"
        if len(month_date) > 7:
            month_date = month_date[:7]
        
        result = self._query_index(region_id, month_date)

        if not result:
            logger.warning("hedonic_index_not_found", region=region_id, month=month_date)
            raise ValueError("hedonic_index_not_found")

        return result
    
    def _query_index(self, region_id: str, month_date: str) -> Optional[IndexResult]:
        """Query database for index value"""
        row = self.repo.fetch_index(region_id, month_date)
        if row:
            value, r_squared, n_observations = row
            return IndexResult(
                value=float(value),
                r_squared=float(r_squared) if r_squared else 0.0,
                n_observations=int(n_observations) if n_observations else 0,
                is_fallback=False,
            )

        if region_id != "all":
            row = self.repo.fetch_index("all", month_date)
            if row:
                value, r_squared, n_observations = row
                return IndexResult(
                    value=float(value),
                    r_squared=float(r_squared) if r_squared else 0.0,
                    n_observations=int(n_observations) if n_observations else 0,
                    is_fallback=True,
                    fallback_reason="global_region",
                )

        latest = self.repo.fetch_latest_index(region_id)
        if latest:
            value, r_squared, n_observations, latest_month = latest
            return IndexResult(
                value=float(value),
                r_squared=float(r_squared) if r_squared else 0.0,
                n_observations=int(n_observations) if n_observations else 0,
                is_fallback=True,
                fallback_reason=f"recent_month:{latest_month}",
            )

        if region_id != "all":
            latest_global = self.repo.fetch_latest_index("all")
            if latest_global:
                value, r_squared, n_observations, latest_month = latest_global
                return IndexResult(
                    value=float(value),
                    r_squared=float(r_squared) if r_squared else 0.0,
                    n_observations=int(n_observations) if n_observations else 0,
                    is_fallback=True,
                    fallback_reason=f"global_recent:{latest_month}",
                )

        # Fallback: Try INE IPV (Official Benchmark)
        ine_val = self._get_ine_benchmark(region_id, month_date)
        if ine_val:
            return IndexResult(
                value=ine_val,
                r_squared=0.0,
                n_observations=0,
                is_fallback=True,
                fallback_reason="ine_ipv_anchor"
            )

        return None

    def _get_ine_benchmark(self, region_id: str, month_date: str) -> Optional[float]:
        """
        Fetch official INE Housing Price Index (IPV) as a relative benchmark.
        Note: IPV is an index (base 100), not a €/m² price. 
        We use it to project from a known base price if available, or just return the index raw 
        if the caller handles relative adjustment (which compute_adjustment_factor does).
        """
        try:
            # simple month -> quarter (YYYY-02 -> 2024-Q1)
            y, m = month_date.split('-')[:2]
            q = (int(m) - 1) // 3 + 1
            period = f"{y}-Q{q}"
            
            # 1. Try Specific Region
            value = self.repo.fetch_ine_benchmark(region_id, period)
            if value is not None:
                return float(value)
                
        except Exception as e:
            logger.warning("ine_fallback_failed", error=str(e))
            
        return None
    
    def get_index_series(
        self, 
        region_id: str, 
        start_month: str, 
        end_month: str
    ) -> pd.Series:
        """
        Get hedonic index time series for a region.
        
        Args:
            region_id: City name or region identifier
            start_month: Start month (YYYY-MM)
            end_month: End month (YYYY-MM)
            
        Returns:
            pd.Series with month index and hedonic values
        """
        df = self.repo.fetch_index_series(region_id, start_month, end_month)
        
        if df.empty:
            return pd.Series(dtype=float)
        
        return df.set_index('month_date')['hedonic_index_sqm']
    
    def compute_adjustment_factor(
        self,
        region_id: str,
        comp_timestamp: datetime,
        target_timestamp: datetime
    ) -> Tuple[float, Dict]:
        """
        Compute time-adjustment factor for a comp price.
        
        Formula: adj_factor = I_r(target_month) / I_r(comp_month)
        
        Args:
            region_id: City or neighborhood identifier
            comp_timestamp: When the comp was observed/sold
            target_timestamp: Valuation date (typically today)
            
        Returns:
            Tuple of (adjustment_factor, metadata_dict)
            
        Example:
            If target_month index is 3300 and comp_month index was 3000,
            adj_factor = 3300/3000 = 1.10 (10% appreciation)
            price_adj = price_raw * 1.10
        """
        comp_month = comp_timestamp.strftime("%Y-%m")
        target_month = target_timestamp.strftime("%Y-%m")
        
        # Get indices
        comp_index = self.get_index(region_id, comp_month)
        target_index = self.get_index(region_id, target_month)
        
        if comp_index.value <= 0 or target_index.value <= 0:
            raise ValueError("invalid_hedonic_index_values")

        adj_factor = target_index.value / comp_index.value
        if adj_factor <= 0:
            raise ValueError("invalid_hedonic_adjustment")
        clamped = False
        if adj_factor < 0.5:
            adj_factor = 0.5
            clamped = True
        elif adj_factor > 2.0:
            adj_factor = 2.0
            clamped = True
        
        metadata = {
            "comp_month": comp_month,
            "target_month": target_month,
            "comp_index": comp_index.value,
            "target_index": target_index.value,
            "comp_index_fallback": comp_index.is_fallback,
            "target_index_fallback": target_index.is_fallback,
            "comp_fallback_reason": comp_index.fallback_reason,
            "target_fallback_reason": target_index.fallback_reason,
            "raw_factor": target_index.value / comp_index.value,
            "clamped": clamped,
        }
        
        return adj_factor, metadata
    
    def adjust_comp_price(
        self,
        raw_price: float,
        region_id: str,
        comp_timestamp: datetime,
        target_timestamp: datetime
    ) -> Tuple[float, float, Dict]:
        """
        Convenience method to adjust a comp price to target date.
        
        Args:
            raw_price: Original comp price
            region_id: City or neighborhood
            comp_timestamp: When comp was observed
            target_timestamp: Valuation date
            
        Returns:
            Tuple of (adjusted_price, adjustment_factor, metadata)
        """
        factor, metadata = self.compute_adjustment_factor(
            region_id, comp_timestamp, target_timestamp
        )
        adjusted_price = raw_price * factor
        
        return adjusted_price, factor, metadata
    
    # =========================================================================
    # DATABASE PERSISTENCE
    # =========================================================================
    
    def save_to_db(self, region_name: str = None):
        """Compute and save hedonic indices to database"""
        df = self.compute_index(region_name)
        
        if df.empty:
            return

        region_id = region_name.lower().strip() if region_name else "all"
        has_nh = self.repo.has_column("hedonic_indices", "n_neighborhoods")
        updated_at = datetime.now().isoformat()

        records = []
        
        for _, row in df.iterrows():
            month_str = str(row['month'])
            record_id = f"{region_id}|{month_str}"
            month_date = f"{month_str}-01"
            n_neighborhoods = int(row.get('n_neighborhoods', 1))
            if has_nh:
                records.append(
                    (
                        record_id,
                        region_id,
                        month_date,
                        float(row['hedonic_index']),
                        float(row['raw_median']),
                        float(row['r_squared']),
                        int(row['n_obs']),
                        n_neighborhoods,
                        str(row['coefficients']),
                        updated_at,
                    )
                )
            else:
                records.append(
                    (
                        record_id,
                        region_id,
                        month_date,
                        float(row['hedonic_index']),
                        float(row['raw_median']),
                        float(row['r_squared']),
                        int(row['n_obs']),
                        str(row['coefficients']),
                        updated_at,
                    )
                )

        self.repo.upsert_indices(records)
        
        logger.info("hedonic_indices_saved", region=region_id, count=len(df))


if __name__ == "__main__":
    # Test run
    svc = HedonicIndexService()
    
    # Compute and save
    df = svc.compute_index()
    print(f"Computed {len(df)} months of indices")
    
    if not df.empty:
        svc.save_to_db()
        
        # Test query API
        result = svc.get_index("all", "2024-01")
        print(f"Index for 2024-01: {result}")
        
        # Test adjustment factor
        from datetime import datetime
        factor, meta = svc.compute_adjustment_factor(
            "all",
            datetime(2024, 1, 15),
            datetime(2024, 6, 15)
        )
        print(f"Adjustment factor Jan->Jun 2024: {factor:.3f}")
        print(f"Metadata: {meta}")
