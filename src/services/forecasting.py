"""
Forecasting Service (SOTA V3)

Regime-aware index drift forecaster:
- Uses market or hedonic indices as the single source of truth
- Applies macro + area adjustments to drift
- Explicitly requires sufficient history (no fallbacks)
"""

import sqlite3
from datetime import timedelta
from typing import List, Tuple

import numpy as np
import pandas as pd
import structlog

from src.core.domain.schema import ValuationProjection
from src.services.area_intelligence import AreaIntelligenceService

logger = structlog.get_logger(__name__)

Z_SCORES = {"0.1": -1.2816, "0.5": 0.0, "0.9": 1.2816}


class ForecastingService:
    """
    Regime-aware index drift forecaster (no fallbacks).

    Requires a minimum history window and uses macro + area adjustments.
    """

    def __init__(
        self,
        db_path: str = "data/listings.db",
        min_history_months: int = 12,
        return_window_months: int = 12,
        index_source: str = "market",
    ):
        self.db_path = db_path
        self.area_intelligence = AreaIntelligenceService(db_path)
        self.min_history_months = max(6, int(min_history_months))
        self.return_window_months = max(self.min_history_months, int(return_window_months))
        self.index_source = index_source.strip().lower()

    def _load_time_series(self, region_id: str) -> pd.DataFrame:
        """Load price index history joined with macro indicators and area intelligence."""
        conn = sqlite3.connect(self.db_path)
        if self.index_source == "hedonic":
            query = """
                SELECT
                    hi.month_date,
                    hi.hedonic_index_sqm as index_value,
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
                    mi.price_index_sqm as index_value,
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
        finally:
            conn.close()

        if df.empty:
            return df

        df["month_date"] = pd.to_datetime(df["month_date"], format="mixed", errors="coerce")
        df = df.dropna(subset=["month_date"])
        df["index_value"] = pd.to_numeric(df.get("index_value"), errors="coerce")
        df = df.dropna(subset=["index_value"])
        df = df[df["index_value"] > 0]

        df["euribor_12m"] = pd.to_numeric(df.get("euribor_12m"), errors="coerce").ffill().fillna(3.0)
        df["ecb_deposit_rate"] = pd.to_numeric(df.get("ecb_deposit_rate"), errors="coerce").ffill().fillna(3.5)
        df["inventory_count"] = pd.to_numeric(df.get("inventory_count"), errors="coerce").fillna(0)

        area_data = self.area_intelligence.get_area_indicators(region_id)
        df["area_sentiment"] = area_data.get("sentiment_score", 0.5)
        df["area_development"] = area_data.get("future_development_score", 0.5)

        return df

    def _load_rent_time_series(self, region_id: str) -> pd.DataFrame:
        """Load rent index history joined with macro indicators and area intelligence."""
        conn = sqlite3.connect(self.db_path)
        query = """
            SELECT
                mi.month_date,
                mi.rent_index_sqm as index_value,
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
        finally:
            conn.close()

        if df.empty:
            return df

        df["month_date"] = pd.to_datetime(df["month_date"], format="mixed", errors="coerce")
        df = df.dropna(subset=["month_date"])
        df["index_value"] = pd.to_numeric(df.get("index_value"), errors="coerce")
        df = df.dropna(subset=["index_value"])
        df = df[df["index_value"] > 0]

        df["euribor_12m"] = pd.to_numeric(df.get("euribor_12m"), errors="coerce").ffill().fillna(3.0)
        df["ecb_deposit_rate"] = pd.to_numeric(df.get("ecb_deposit_rate"), errors="coerce").ffill().fillna(3.5)
        df["inventory_count"] = pd.to_numeric(df.get("inventory_count"), errors="coerce").fillna(0)

        area_data = self.area_intelligence.get_area_indicators(region_id)
        df["area_sentiment"] = area_data.get("sentiment_score", 0.5)
        df["area_development"] = area_data.get("future_development_score", 0.5)

        return df

    def _compute_regime(self, df: pd.DataFrame) -> Tuple[float, float]:
        if len(df) < self.min_history_months:
            raise ValueError("insufficient_history")

        df = df.copy()
        df["log_return"] = np.log(df["index_value"]).diff()
        df = df.dropna(subset=["log_return"])
        if len(df) < self.min_history_months:
            raise ValueError("insufficient_returns")

        window = df.tail(self.return_window_months)
        weights = np.exp(np.linspace(-1.5, 0.0, len(window)))
        weights = weights / weights.sum()

        base_drift = float(np.sum(weights * window["log_return"].values))
        centered = window["log_return"].values - base_drift
        vol = float(np.sqrt(np.sum(weights * centered * centered)))

        rate_trend = float(window["euribor_12m"].iloc[-1] - window["euribor_12m"].mean())
        macro_adj = -0.0025 * rate_trend
        sentiment = float(window["area_sentiment"].iloc[-1])
        development = float(window["area_development"].iloc[-1])
        sentiment_adj = (sentiment - 0.5) * 0.002
        development_adj = (development - 0.5) * 0.0015

        drift = base_drift + macro_adj + sentiment_adj + development_adj
        vol = max(vol, 1e-4)
        return drift, vol

    def _project(
        self,
        current_value: float,
        drift: float,
        vol: float,
        horizons_months: List[int],
        metric: str,
        scenario_name: str,
    ) -> List[ValuationProjection]:
        if current_value <= 0:
            raise ValueError("invalid_current_value")

        projections: List[ValuationProjection] = []
        for h in horizons_months:
            months = float(h)
            mean = drift * months
            sigma = vol * np.sqrt(months)

            q50 = current_value * float(np.exp(mean))
            q10 = current_value * float(np.exp(mean + Z_SCORES["0.1"] * sigma))
            q90 = current_value * float(np.exp(mean + Z_SCORES["0.9"] * sigma))

            spread = (q90 - q10) / max(q50, 1.0)
            confidence = max(0.1, 1.0 - spread)

            projections.append(
                ValuationProjection(
                    metric=metric,
                    months_future=h,
                    years_future=h / 12.0,
                    predicted_value=q50,
                    confidence_interval_low=q10,
                    confidence_interval_high=q90,
                    confidence_score=confidence,
                    scenario_name=scenario_name,
                )
            )

        return projections

    def forecast_property(
        self,
        region_id: str,
        current_value: float,
        horizons_months: List[int] = [12, 36, 60],
    ) -> List[ValuationProjection]:
        df = self._load_time_series(region_id)
        if df.empty:
            raise ValueError("missing_price_index")
        drift, vol = self._compute_regime(df)
        return self._project(
            current_value=current_value,
            drift=drift,
            vol=vol,
            horizons_months=horizons_months,
            metric="price",
            scenario_name=f"{self.index_source}_drift",
        )

    def forecast_rent(
        self,
        region_id: str,
        current_monthly_rent: float,
        horizons_months: List[int] = [12, 36, 60],
    ) -> List[ValuationProjection]:
        df = self._load_rent_time_series(region_id)
        if df.empty:
            raise ValueError("missing_rent_index")
        drift, vol = self._compute_regime(df)
        return self._project(
            current_value=current_monthly_rent,
            drift=drift,
            vol=vol,
            horizons_months=horizons_months,
            metric="rent_monthly",
            scenario_name="rent_drift",
        )
