from datetime import datetime, timedelta
from typing import Dict, Optional
import structlog
import pandas as pd
import numpy as np
from src.core.config import DEFAULT_DB_PATH
from src.repositories.base import resolve_db_url
from src.repositories.eri_metrics import ERIMetricsRepository
from src.repositories.market_indices import MarketIndicesRepository

logger = structlog.get_logger(__name__)


class ERISignalsService:
    """
    Provides lag-aware ERI (registral) liquidity + price signals.

    ERI data is lagged (~45 days); we treat it as a quarterly regime signal.
    """

    def __init__(self, db_path: str = str(DEFAULT_DB_PATH), db_url: Optional[str] = None, lag_days: int = 45, trailing_years: int = 3):
        self.db_url = resolve_db_url(db_url=db_url, db_path=db_path)
        self.lag_days = int(lag_days)
        self.trailing_years = int(trailing_years)
        self.eri_repo = ERIMetricsRepository(db_url=self.db_url)
        self.market_repo = MarketIndicesRepository(db_url=self.db_url)

    def _load_series(self, region_id: str, allow_proxy: bool = True) -> pd.DataFrame:
        # Priority 1: Official ERI Data
        try:
            df = self.eri_repo.load_series(region_id)
        except Exception as e:
            logger.warning("eri_load_failed", error=str(e))
            df = pd.DataFrame()

        if df.empty and allow_proxy:
            # Fallback to internal proxy
            try:
                proxy = self.market_repo.fetch_series(region_id)
                if not proxy.empty:
                    df = proxy.rename(
                        columns={
                            "month_date": "period_date",
                            "new_listings_count": "txn_count",
                            "price_index_sqm": "price_sqm",
                        }
                    )
                    df["mortgage_count"] = 0
            except Exception as e:
                logger.warning("eri_proxy_failed", error=str(e))
                return pd.DataFrame()

        if df.empty:
            return df

        df["period_date"] = pd.to_datetime(df["period_date"], format="mixed", errors="coerce")
        df = df.dropna(subset=["period_date"])
        for col in ("txn_count", "mortgage_count", "price_sqm"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        
        # Calculate derived changes dynamically if missing
        if "price_sqm_yoy" not in df.columns or df["price_sqm_yoy"].isna().all():
            df["price_sqm_yoy"] = df["price_sqm"].pct_change(periods=4).fillna(0) # Quarterly assumption for ERI
        if "price_sqm_qoq" not in df.columns or df["price_sqm_qoq"].isna().all():
            df["price_sqm_qoq"] = df["price_sqm"].pct_change(periods=1).fillna(0)
        
        return df

    def _effective_date(self, as_of_date: Optional[datetime]) -> datetime:
        base = as_of_date or datetime.utcnow()
        return base - timedelta(days=self.lag_days)

    def _window_size(self, df: pd.DataFrame) -> int:
        if len(df) < 2:
            return len(df)
        diffs = df["period_date"].diff().dt.days.dropna()
        if diffs.empty:
            return len(df)
        median_days = diffs.median()
        # Quarterly if cadence > ~60 days
        if median_days >= 60:
            return self.trailing_years * 4
        return self.trailing_years * 12

    def get_signals(
        self,
        region_id: str,
        as_of_date: Optional[datetime],
        allow_proxy: bool = True
    ) -> Dict[str, float]:
        df = self._load_series(region_id, allow_proxy=allow_proxy)
        if df.empty:
            return {}

        effective_date = self._effective_date(as_of_date)
        df = df[df["period_date"] <= effective_date].sort_values("period_date")
        if df.empty:
            return {}

        latest = df.iloc[-1]
        window_size = self._window_size(df)
        window = df.tail(window_size)

        txn_count = latest.get("txn_count")
        txn_volume_z = None
        if txn_count is not None and not np.isnan(txn_count):
            mean = window["txn_count"].mean()
            std = window["txn_count"].std()
            if std and std > 0:
                txn_volume_z = float((txn_count - mean) / std)
            else:
                txn_volume_z = 0.0

        mortgage_share = None
        mortgage_count = latest.get("mortgage_count")
        if txn_count and txn_count > 0 and mortgage_count is not None and not np.isnan(mortgage_count):
            mortgage_share = float(mortgage_count / txn_count)

        registral_change = None
        if "price_sqm_yoy" in latest and not pd.isna(latest["price_sqm_yoy"]):
            registral_change = float(latest["price_sqm_yoy"])
        elif "price_sqm_qoq" in latest and not pd.isna(latest["price_sqm_qoq"]):
            registral_change = float(latest["price_sqm_qoq"])
        else:
            # Compute YoY change if possible.
            if "price_sqm" in df.columns:
                prev_date = effective_date - timedelta(days=365)
                prev = df[df["period_date"] <= prev_date].tail(1)
                if not prev.empty:
                    prev_price = prev.iloc[-1].get("price_sqm")
                    curr_price = latest.get("price_sqm")
                    if prev_price and curr_price and prev_price > 0:
                        registral_change = float(curr_price / prev_price - 1.0)

        payload = {
            "txn_volume_z": txn_volume_z if txn_volume_z is not None else 0.0,
            "mortgage_share": mortgage_share if mortgage_share is not None else 0.0,
            "effective_date": effective_date.date().isoformat()
        }
        if registral_change is not None:
            payload["registral_price_sqm_change"] = registral_change
        return payload
