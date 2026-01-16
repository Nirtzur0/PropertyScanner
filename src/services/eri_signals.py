from datetime import datetime, timedelta
from typing import Dict, Optional
import sqlite3
import structlog
import pandas as pd
import numpy as np
from src.core.config import DEFAULT_DB_PATH

logger = structlog.get_logger(__name__)


class ERISignalsService:
    """
    Provides lag-aware ERI (registral) liquidity + price signals.

    ERI data is lagged (~45 days); we treat it as a quarterly regime signal.
    """

    def __init__(self, db_path: str = str(DEFAULT_DB_PATH), lag_days: int = 45, trailing_years: int = 3):
        self.db_path = db_path
        self.lag_days = int(lag_days)
        self.trailing_years = int(trailing_years)

    def _load_series(self, region_id: str) -> pd.DataFrame:
        conn = sqlite3.connect(self.db_path)
        query = """
            SELECT period_date, txn_count, mortgage_count, price_sqm, price_sqm_yoy, price_sqm_qoq
            FROM eri_metrics
            WHERE region_id = ?
            ORDER BY period_date ASC
        """
        try:
            df = pd.read_sql(query, conn, params=(region_id,))
        except Exception as e:
            logger.warning("eri_load_failed", error=str(e))
            return pd.DataFrame()
        finally:
            conn.close()

        if df.empty:
            return df

        df["period_date"] = pd.to_datetime(df["period_date"], format="mixed", errors="coerce")
        df = df.dropna(subset=["period_date"])
        for col in ("txn_count", "mortgage_count", "price_sqm", "price_sqm_yoy", "price_sqm_qoq"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
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

    def get_signals(self, region_id: str, as_of_date: Optional[datetime]) -> Dict[str, float]:
        df = self._load_series(region_id)
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
