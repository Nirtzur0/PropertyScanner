from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import structlog
import pandas as pd
import numpy as np
from src.platform.config import DEFAULT_DB_PATH
from src.platform.db.base import resolve_db_url
from src.market.repositories.eri_metrics import ERIMetricsRepository
from src.market.repositories.it_registry_metrics import ItalyRegistryMetricsRepository
from src.market.repositories.uk_registry_metrics import UKRegistryMetricsRepository
from src.market.repositories.registry_metrics import RegistryMetricsRepository
from src.market.repositories.market_indices import MarketIndicesRepository
from src.market.services.registry_canonical import RegistryCanonicalizer
from src.platform.settings import AppConfig
from src.platform.utils.config import load_app_config_safe
from src.platform.utils.time import utcnow

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class RegistryProvider:
    provider_id: str
    country_codes: Tuple[str, ...]
    repository: RegistryMetricsRepository
    lag_days: int


class ERISignalsService:
    """
    Provides lag-aware registry liquidity + price signals (ERI and equivalents).

    ERI data is lagged (~45 days); we treat it as a quarterly regime signal.
    """

    def __init__(
        self,
        db_path: str = str(DEFAULT_DB_PATH),
        db_url: Optional[str] = None,
        lag_days: int = 45,
        trailing_years: int = 3,
        default_provider_id: str = "eri_es",
        app_config: Optional[AppConfig] = None,
    ):
        self.db_url = resolve_db_url(db_url=db_url, db_path=db_path)
        self.lag_days = int(lag_days)
        self.trailing_years = int(trailing_years)
        self.market_repo = MarketIndicesRepository(db_url=self.db_url)
        self.app_config = app_config or load_app_config_safe()
        self.canonicalizer = RegistryCanonicalizer(app_config=self.app_config)
        self.providers = self._build_providers()
        if default_provider_id not in self.providers:
            default_provider_id = "eri_es"
        self.default_provider_id = default_provider_id

    def _build_providers(self) -> Dict[str, RegistryProvider]:
        return {
            "eri_es": RegistryProvider(
                provider_id="eri_es",
                country_codes=("ES",),
                repository=ERIMetricsRepository(db_url=self.db_url),
                lag_days=self.lag_days,
            ),
            "uk_land_registry": RegistryProvider(
                provider_id="uk_land_registry",
                country_codes=("GB", "UK"),
                repository=UKRegistryMetricsRepository(db_url=self.db_url),
                lag_days=90,
            ),
            "it_omi_registry": RegistryProvider(
                provider_id="it_omi_registry",
                country_codes=("IT",),
                repository=ItalyRegistryMetricsRepository(db_url=self.db_url),
                lag_days=90,
            ),
        }

    def _select_provider(self, *, provider_id: Optional[str], country_code: Optional[str]) -> RegistryProvider:
        if provider_id and provider_id in self.providers:
            return self.providers[provider_id]
        if country_code:
            code = str(country_code).upper().strip()
            for provider in self.providers.values():
                if code in provider.country_codes:
                    return provider
        return self.providers[self.default_provider_id]

    def _load_series(
        self,
        region_id: str,
        allow_proxy: bool,
        provider: RegistryProvider,
        proxy_region_id: Optional[str] = None,
    ) -> Tuple[pd.DataFrame, bool]:
        proxy_used = False
        # Priority 1: Official registry data
        try:
            provider.repository.ensure_schema()
            df = provider.repository.load_series(region_id)
        except Exception as e:
            logger.warning(
                "registry_load_failed",
                provider_id=provider.provider_id,
                error=str(e),
            )
            df = pd.DataFrame()

        if df.empty and allow_proxy:
            # Fallback to internal proxy
            try:
                proxy_key = proxy_region_id or region_id
                proxy = self.market_repo.fetch_series(proxy_key)
                if not proxy.empty:
                    df = proxy.rename(
                        columns={
                            "month_date": "period_date",
                            "new_listings_count": "txn_count",
                            "price_index_sqm": "price_sqm",
                        }
                    )
                    df["mortgage_count"] = 0
                    proxy_used = True
            except Exception as e:
                logger.warning(
                    "registry_proxy_failed",
                    provider_id=provider.provider_id,
                    error=str(e),
                )
                return pd.DataFrame(), proxy_used

        if df.empty:
            return df, proxy_used

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
        
        return df, proxy_used

    def _effective_date(self, as_of_date: Optional[datetime], provider: RegistryProvider) -> datetime:
        base = as_of_date or utcnow()
        return base - timedelta(days=provider.lag_days)

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
        allow_proxy: bool = True,
        country_code: Optional[str] = None,
        provider_id: Optional[str] = None,
    ) -> Dict[str, object]:
        provider = self._select_provider(provider_id=provider_id, country_code=country_code)
        region_key = self.canonicalizer.canonicalize(
            region_id,
            country_code=country_code,
            provider_id=provider.provider_id,
        ) or str(region_id).strip().lower()
        df, proxy_used = self._load_series(
            region_key,
            allow_proxy=allow_proxy,
            provider=provider,
            proxy_region_id=region_id,
        )
        if df.empty:
            return {}

        effective_date = self._effective_date(as_of_date, provider)
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
            "registry_provider": provider.provider_id,
            "txn_volume_z": txn_volume_z if txn_volume_z is not None else 0.0,
            "mortgage_share": mortgage_share if mortgage_share is not None else 0.0,
            "effective_date": effective_date.date().isoformat(),
            "proxy_used": proxy_used,
            "source_type": "proxy" if proxy_used else "registry",
        }
        if registral_change is not None:
            payload["registral_price_sqm_change"] = registral_change
        return payload
