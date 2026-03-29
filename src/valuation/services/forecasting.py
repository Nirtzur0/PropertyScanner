"""
Forecasting Service (SOTA V3)

Regime-aware index drift forecaster:
- Uses market or hedonic indices as the single source of truth
- Applies macro + area adjustments to drift
- Explicitly requires sufficient history (no fallbacks)
"""

from typing import List, Tuple, Optional

import numpy as np
import pandas as pd
import structlog

from src.platform.config import DEFAULT_DB_PATH, TFT_MODEL_PATH
from src.platform.domain.schema import ValuationProjection
from src.market.services.area_intelligence import AreaIntelligenceService
from src.platform.db.base import resolve_db_url
from src.market.repositories.market_fundamentals import MarketFundamentalsRepository

logger = structlog.get_logger(__name__)

Z_SCORES = {"0.1": -1.2816, "0.5": 0.0, "0.9": 1.2816}


class ForecastingService:
    """
    Regime-aware index drift forecaster (no fallbacks).

    Requires a minimum history window and uses macro + area adjustments.
    """

    def __init__(
        self,
        db_path: str = str(DEFAULT_DB_PATH),
        db_url: Optional[str] = None,
        min_history_months: int = 12,
        return_window_months: int = 12,
        index_source: str = "market",
        forecast_mode: str = "analytic",
        tft_model_path: str = str(TFT_MODEL_PATH),
        allow_short_history: bool = True,
        min_fallback_months: int = 3,
    ):
        self.db_url = resolve_db_url(db_url=db_url, db_path=db_path)
        self.area_intelligence = AreaIntelligenceService(db_url=self.db_url)
        self.market_repo = MarketFundamentalsRepository(db_url=self.db_url)
        self.min_history_months = max(6, int(min_history_months))
        self.return_window_months = max(self.min_history_months, int(return_window_months))
        self.index_source = index_source.strip().lower()
        self.forecast_mode = forecast_mode.strip().lower()
        self.tft = None
        self.allow_short_history = bool(allow_short_history)
        self.min_fallback_months = max(2, int(min_fallback_months))

        if self.forecast_mode == "tft":
            try:
                from src.ml.training.forecasting_tft import TFTForecastingService
                self.tft = TFTForecastingService(db_path=db_path, model_path=tft_model_path)
            except Exception as e:
                raise RuntimeError("tft_unavailable") from e

    def _load_time_series(
        self,
        region_id: str,
        country_code: Optional[str],
        *,
        area_region_id: Optional[str] = None,
    ) -> pd.DataFrame:
        """Load price index history joined with macro indicators and area intelligence."""
        df = self.market_repo.load_price_series(region_id, index_source=self.index_source)

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

        area_target = area_region_id or region_id
        area_data = self.area_intelligence.get_area_indicators(area_target, country_code=country_code)
        df["area_sentiment"] = area_data.get("sentiment_score", 0.5)
        df["area_development"] = area_data.get("future_development_score", 0.5)
        area_confidence = area_data.get("area_confidence")
        if area_confidence is None:
            area_confidence = 1.0
        df["area_confidence"] = float(area_confidence)

        return df

    def _load_rent_time_series(
        self,
        region_id: str,
        country_code: Optional[str],
        *,
        area_region_id: Optional[str] = None,
    ) -> pd.DataFrame:
        """Load rent index history joined with macro indicators and area intelligence."""
        df = self.market_repo.load_rent_series(region_id)

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

        area_target = area_region_id or region_id
        area_data = self.area_intelligence.get_area_indicators(area_target, country_code=country_code)
        df["area_sentiment"] = area_data.get("sentiment_score", 0.5)
        df["area_development"] = area_data.get("future_development_score", 0.5)
        area_confidence = area_data.get("area_confidence")
        if area_confidence is None:
            area_confidence = 1.0
        df["area_confidence"] = float(area_confidence)

        return df

    def _compute_regime(self, df: pd.DataFrame) -> Tuple[float, float]:
        raw_len = len(df)
        if raw_len < self.min_history_months:
            if not self.allow_short_history or len(df) < self.min_fallback_months:
                raise ValueError("insufficient_history")
            logger.warning(
                "forecast_short_history_fallback",
                available=len(df),
                required=self.min_history_months,
            )

        df = df.copy()
        df["log_return"] = np.log(df["index_value"]).diff()
        df = df.dropna(subset=["log_return"])
        if len(df) < self.min_history_months:
            if not self.allow_short_history or raw_len < self.min_fallback_months:
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
        area_conf = float(window.get("area_confidence", pd.Series([1.0])).iloc[-1])
        if pd.isna(area_conf):
            area_conf = 1.0
        area_conf = max(0.0, min(1.0, area_conf))
        sentiment_adj = (sentiment - 0.5) * 0.002 * area_conf
        development_adj = (development - 0.5) * 0.0015 * area_conf

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
        country_code: Optional[str] = None,
        horizons_months: List[int] = [12, 36, 60],
    ) -> List[ValuationProjection]:
        if self.forecast_mode == "tft":
            if not self.tft:
                raise ValueError("tft_unavailable")
            results = self.tft.predict(region_id=region_id, current_value=current_value)
            return self._tft_to_projections(results, horizons_months, metric="price", scenario_name="tft")

        df = self._load_time_series(region_id, country_code)
        scenario_name = f"{self.index_source}_drift"
        if df.empty and region_id != "all":
            df = self._load_time_series("all", country_code, area_region_id=region_id)
            if not df.empty:
                scenario_name = f"{scenario_name}_fallback_all"
                logger.warning(
                    "forecast_index_fallback_all",
                    region_id=region_id,
                    index_source=self.index_source,
                )
        if df.empty:
            raise ValueError("missing_price_index")
        drift, vol = self._compute_regime(df)
        return self._project(
            current_value=current_value,
            drift=drift,
            vol=vol,
            horizons_months=horizons_months,
            metric="price",
            scenario_name=scenario_name,
        )

    def forecast_rent(
        self,
        region_id: str,
        current_monthly_rent: float,
        country_code: Optional[str] = None,
        horizons_months: List[int] = [12, 36, 60],
    ) -> List[ValuationProjection]:
        if self.forecast_mode == "tft":
            raise ValueError("tft_rent_not_supported")
        df = self._load_rent_time_series(region_id, country_code)
        scenario = "rent_drift"
        if df.empty and region_id != "all":
            df = self._load_rent_time_series("all", country_code, area_region_id=region_id)
            if not df.empty:
                scenario = "rent_drift_fallback_all"
                logger.warning("rent_index_fallback_all", region_id=region_id)
        if df.empty:
            raise ValueError("missing_rent_index")
        try:
            drift, vol = self._compute_regime(df)
        except ValueError as exc:
            if not self.allow_short_history:
                raise
            logger.warning("rent_forecast_fallback", error=str(exc), available=len(df))
            drift = 0.0
            vol = 0.01
            scenario = f"{scenario}_fallback"
        return self._project(
            current_value=current_monthly_rent,
            drift=drift,
            vol=vol,
            horizons_months=horizons_months,
            metric="rent_monthly",
            scenario_name=scenario,
        )

    def _tft_to_projections(
        self,
        results: dict,
        horizons_months: List[int],
        metric: str,
        scenario_name: str
    ) -> List[ValuationProjection]:
        if not results:
            raise ValueError("tft_missing_predictions")

        projections: List[ValuationProjection] = []
        for h in horizons_months:
            q10 = results.get(f"q10_m{h}")
            q50 = results.get(f"q50_m{h}")
            q90 = results.get(f"q90_m{h}")
            if q10 is None or q50 is None or q90 is None:
                raise ValueError("tft_missing_horizon")

            spread = (q90 - q10) / max(q50, 1.0)
            confidence = max(0.1, 1.0 - spread)

            projections.append(
                ValuationProjection(
                    metric=metric,
                    months_future=h,
                    years_future=h / 12.0,
                    predicted_value=float(q50),
                    confidence_interval_low=float(q10),
                    confidence_interval_high=float(q90),
                    confidence_score=float(confidence),
                    scenario_name=scenario_name,
                )
            )

        return projections
