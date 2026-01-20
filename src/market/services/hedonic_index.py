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
from sqlalchemy import text
from src.platform.config import DEFAULT_DB_PATH
from src.platform.db.base import resolve_db_url
from src.market.repositories.hedonic_indices import HedonicIndicesRepository
from src.listings.repositories.listings import ListingsRepository
from src.platform.storage import StorageService
from src.platform.settings import AppConfig
from src.platform.utils.config import load_app_config_safe

logger = structlog.get_logger(__name__)


@dataclass
class IndexResult:
    """Result from hedonic index query with metadata"""
    value: float
    r_squared: float
    n_observations: int
    is_fallback: bool = False
    fallback_reason: Optional[str] = None
    source: Optional[str] = None
    provider_id: Optional[str] = None
    metric: Optional[str] = None
    period_date: Optional[str] = None
    lag_days: Optional[int] = None


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
        app_config: Optional[AppConfig] = None,
    ):
        self.app_config = app_config or load_app_config_safe()
        self.config = self.app_config.hedonic
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

    def _build_design_matrix(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, int, int]:
        X_base = df[self.feature_cols].values
        y = df['log_price'].values
        neighborhoods = df['neighborhood'].values
        unique_neighborhoods = np.unique(neighborhoods)
        n_neighborhoods = len(unique_neighborhoods)

        if self.config.include_neighborhood_fe and n_neighborhoods > 1:
            neighborhood_dummies = pd.get_dummies(
                df['neighborhood'],
                prefix='nh',
                drop_first=True
            ).values
            X = np.hstack([X_base, neighborhood_dummies])
            n_dummies = neighborhood_dummies.shape[1]
        else:
            X = X_base
            n_dummies = 0

        return X, y, n_neighborhoods, n_dummies

    def _reference_row(self, n_dummies: int) -> np.ndarray:
        ref_X = np.array([[
            self.reference_basket['surface_area_sqm'],
            self.reference_basket['bedrooms'],
            self.reference_basket['bathrooms'],
            self.reference_basket['has_elevator'],
            self.reference_basket['floor'],
        ]])
        if n_dummies > 0:
            ref_X = np.hstack([ref_X, np.zeros((1, n_dummies))])
        return ref_X

    def _month_end(self, month_date: str) -> Optional[datetime]:
        if not month_date:
            return None
        dt = pd.to_datetime(month_date, format="mixed", errors="coerce")
        if pd.isna(dt):
            return None
        period = dt.to_period("M")
        return period.end_time.to_pydatetime()

    def _registry_providers(self) -> List[str]:
        if self.config.registry_provider_priority:
            providers = list(self.config.registry_provider_priority)
        else:
            providers = []
            if self.app_config and getattr(self.app_config, "registry", None):
                for source in self.app_config.registry.sources:
                    if source.enabled and source.provider_id:
                        providers.append(source.provider_id)
            for default_id in ("eri_es", "ine_ipv"):
                if default_id not in providers:
                    providers.append(default_id)
        return [p for p in providers if p]

    def _fetch_registry_metric(
        self,
        *,
        provider_id: str,
        region_id: str,
        metric: str,
        target_end: datetime,
        housing_type: Optional[str] = None,
    ) -> Optional[Tuple[float, datetime]]:
        clause = ""
        params = {
            "provider_id": provider_id,
            "region_id": region_id,
            "metric": metric,
            "target_end": target_end.date().isoformat(),
        }
        if housing_type:
            clause = "AND housing_type = :housing_type"
            params["housing_type"] = housing_type

        query = text(
            f"""
            SELECT value, period_date
            FROM official_metrics
            WHERE provider_id = :provider_id
              AND metric = :metric
              AND period_date IS NOT NULL
              AND LOWER(region_id) = :region_id
              {clause}
              AND period_date <= :target_end
            ORDER BY period_date DESC
            LIMIT 1
            """
        )
        with self.storage.engine.connect() as conn:
            row = conn.execute(query, params).fetchone()
        if not row or row[0] is None or row[1] is None:
            return None
        value = float(row[0])
        period_dt = pd.to_datetime(row[1], format="mixed", errors="coerce")
        if pd.isna(period_dt):
            return None
        return value, period_dt.to_pydatetime()

    def _fetch_registry_global_metric(
        self,
        *,
        provider_id: str,
        metric: str,
        target_end: datetime,
        housing_type: Optional[str] = None,
    ) -> Optional[Tuple[float, datetime]]:
        clause = ""
        params = {
            "provider_id": provider_id,
            "metric": metric,
            "target_end": target_end.date().isoformat(),
        }
        if housing_type:
            clause = "AND housing_type = :housing_type"
            params["housing_type"] = housing_type

        query = text(
            f"""
            SELECT AVG(value) as avg_value, period_date
            FROM official_metrics
            WHERE provider_id = :provider_id
              AND metric = :metric
              AND period_date IS NOT NULL
              {clause}
              AND period_date <= :target_end
            GROUP BY period_date
            ORDER BY period_date DESC
            LIMIT 1
            """
        )
        with self.storage.engine.connect() as conn:
            row = conn.execute(query, params).fetchone()
        if not row or row[0] is None or row[1] is None:
            return None
        value = float(row[0])
        period_dt = pd.to_datetime(row[1], format="mixed", errors="coerce")
        if pd.isna(period_dt):
            return None
        return value, period_dt.to_pydatetime()

    def _get_registry_index(self, region_id: str, month_date: str) -> Optional[IndexResult]:
        if not self.repo.has_table("official_metrics"):
            return None
        target_end = self._month_end(month_date)
        if target_end is None:
            return None
        max_lag = timedelta(days=int(self.config.registry_max_lag_days))
        providers = self._registry_providers()
        metrics = list(self.config.registry_metric_priority or ["price_sqm", "index"])
        if not providers:
            return None

        region_norm = str(region_id or "").strip().lower()
        region_candidates = [region_norm]
        if region_norm and region_norm != "all":
            region_candidates.append("all")

        for provider_id in providers:
            for metric in metrics:
                housing_type = "general" if provider_id == "ine_ipv" and metric == "index" else None
                for region_key in region_candidates:
                    if not region_key:
                        continue
                    row = self._fetch_registry_metric(
                        provider_id=provider_id,
                        region_id=region_key,
                        metric=metric,
                        target_end=target_end,
                        housing_type=housing_type,
                    )
                    if not row:
                        continue
                    value, period_dt = row
                    lag_days = (target_end.date() - period_dt.date()).days
                    if lag_days < 0 or lag_days > max_lag.days:
                        continue
                    is_fallback = region_key != region_norm
                    fallback_reason = None
                    if is_fallback:
                        fallback_reason = f"registry_region:{region_key}"
                    elif not self.config.registry_primary:
                        is_fallback = True
                        fallback_reason = "registry_fallback"
                    return IndexResult(
                        value=value,
                        r_squared=0.0,
                        n_observations=0,
                        is_fallback=is_fallback,
                        fallback_reason=fallback_reason,
                        source="registry",
                        provider_id=provider_id,
                        metric=metric,
                        period_date=period_dt.date().isoformat(),
                        lag_days=lag_days,
                    )
                row = self._fetch_registry_global_metric(
                    provider_id=provider_id,
                    metric=metric,
                    target_end=target_end,
                    housing_type=housing_type,
                )
                if not row:
                    continue
                value, period_dt = row
                lag_days = (target_end.date() - period_dt.date()).days
                if lag_days < 0 or lag_days > max_lag.days:
                    continue
                return IndexResult(
                    value=value,
                    r_squared=0.0,
                    n_observations=0,
                    is_fallback=True,
                    fallback_reason="registry_global_avg",
                    source="registry",
                    provider_id=provider_id,
                    metric=metric,
                    period_date=period_dt.date().isoformat(),
                    lag_days=lag_days,
                )
        return None

    def _index_quality_ok(self, r_squared: float, n_obs: int) -> bool:
        return n_obs >= int(self.config.min_monthly_obs) and r_squared >= float(self.config.min_monthly_r2)

    def _get_hedonic_index(self, region_id: str, month_date: str) -> Optional[IndexResult]:
        row = self.repo.fetch_index(region_id, month_date)
        if row:
            value, r_squared, n_observations = row
            quality_ok = self._index_quality_ok(r_squared, n_observations)
            fallback_reason = None if quality_ok else "hedonic_low_quality"
            return IndexResult(
                value=float(value),
                r_squared=float(r_squared) if r_squared else 0.0,
                n_observations=int(n_observations) if n_observations else 0,
                is_fallback=not quality_ok,
                fallback_reason=fallback_reason,
                source="hedonic",
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
                    source="hedonic",
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
                source="hedonic",
                period_date=str(latest_month),
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
                    source="hedonic",
                    period_date=str(latest_month),
                )

        return None
    
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

        if len(df) < int(self.config.min_total_obs):
            logger.warning("insufficient_data_for_hedonic", count=len(df))
            return pd.DataFrame()

        # Get unique months
        months = sorted(df['month'].dropna().unique())
        results = []

        if str(self.config.index_mode).lower() == "pooled":
            try:
                X, y, n_neighborhoods, n_dummies = self._build_design_matrix(df)
                model = Ridge(alpha=float(self.config.ridge_alpha))
                model.fit(X, y)
                r_squared = model.score(X, y)

                ref_X = self._reference_row(n_dummies)
                beta = model.coef_
                adj_log_price = y - (X - ref_X) @ beta
                df = df.copy()
                df['adj_price'] = np.exp(adj_log_price)

                for month in months:
                    month_df = df[df['month'] == month].copy()
                    if len(month_df) < int(self.config.pooled_min_monthly_obs):
                        continue

                    hedonic_index = (month_df['adj_price'] / self.reference_basket['surface_area_sqm']).median()
                    raw_median = (month_df['price'] / month_df['surface_area_sqm']).median()

                    results.append({
                        'month': month,
                        'hedonic_index': float(hedonic_index),
                        'raw_median': float(raw_median),
                        'r_squared': float(r_squared),
                        'n_obs': len(month_df),
                        'n_neighborhoods': n_neighborhoods,
                        'coefficients': dict(zip(self.feature_cols, model.coef_[:len(self.feature_cols)])),
                    })

            except Exception as e:
                logger.warning("hedonic_fit_failed", mode="pooled", error=str(e))
        else:
            for month in months:
                month_df = df[df['month'] == month].copy()

                if len(month_df) < int(self.config.min_monthly_obs):
                    continue

                try:
                    X, y, n_neighborhoods, n_dummies = self._build_design_matrix(month_df)
                    model = Ridge(alpha=float(self.config.ridge_alpha))
                    model.fit(X, y)

                    r_squared = model.score(X, y)
                    ref_X = self._reference_row(n_dummies)
                    log_ref_price = model.predict(ref_X)[0]
                    ref_price = np.exp(log_ref_price)

                    hedonic_index = ref_price / self.reference_basket['surface_area_sqm']
                    raw_median = (month_df['price'] / month_df['surface_area_sqm']).median()

                    results.append({
                        'month': month,
                        'hedonic_index': float(hedonic_index),
                        'raw_median': float(raw_median),
                        'r_squared': float(r_squared),
                        'n_obs': len(month_df),
                        'n_neighborhoods': n_neighborhoods,
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
        region_norm = str(region_id or "").strip().lower() if region_id else "all"

        if self.config.registry_primary:
            registry_result = self._get_registry_index(region_norm, month_date)
            if registry_result:
                return registry_result

        hedonic_result = self._get_hedonic_index(region_norm, month_date)
        if hedonic_result:
            return hedonic_result

        if not self.config.registry_primary:
            registry_result = self._get_registry_index(region_norm, month_date)
            if registry_result:
                return registry_result

        # Fallback: Try INE IPV (Official Benchmark)
        ine_val = self._get_ine_benchmark(region_id, month_date)
        if ine_val:
            return IndexResult(
                value=ine_val,
                r_squared=0.0,
                n_observations=0,
                is_fallback=True,
                fallback_reason="ine_ipv_anchor",
                source="registry",
                provider_id="ine_ipv",
                metric="index",
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
            "comp_index_source": comp_index.source,
            "target_index_source": target_index.source,
            "comp_index_provider": comp_index.provider_id,
            "target_index_provider": target_index.provider_id,
            "comp_index_metric": comp_index.metric,
            "target_index_metric": target_index.metric,
            "comp_index_period": comp_index.period_date,
            "target_index_period": target_index.period_date,
            "comp_index_lag_days": comp_index.lag_days,
            "target_index_lag_days": target_index.lag_days,
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
