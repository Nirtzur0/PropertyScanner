import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import pandas as pd

from src.platform.config import DEFAULT_DB_PATH
from src.market.repositories.area_intelligence import AreaIntelligenceRepository
from src.platform.db.base import resolve_db_url
from src.market.repositories.eri_metrics import ERIMetricsRepository
from src.market.repositories.ine_ipv import IneIpvRepository
from src.market.services.eri_signals import ERISignalsService

logger = logging.getLogger(__name__)


class AreaIntelligenceService:
    """
    Service to fetch and manage external intelligence for areas (cities/neighborhoods).
    Uses official datasets (ERI, INE IPV) and tracks freshness + credibility.
    """

    def __init__(self, db_path: str = str(DEFAULT_DB_PATH), db_url: Optional[str] = None):
        self.db_url = resolve_db_url(db_url=db_url, db_path=db_path)
        self.repo = AreaIntelligenceRepository(db_url=self.db_url)
        self.eri_service = ERISignalsService(db_url=self.db_url)
        self.eri_repo = ERIMetricsRepository(db_url=self.db_url)
        self.ine_repo = IneIpvRepository(db_url=self.db_url)
        self.repo.ensure_table()

    def get_area_indicators(self, area_id: str) -> Dict[str, Any]:
        """
        Retrieve stored intelligence for an area.
        If data is stale or missing, attempts to refresh it.
        """
        area_id = area_id.lower().strip()
        data = self.repo.fetch_area(area_id)

        if not data or self._is_stale(data):
            self.refresh_area_data(area_id)
            data = self.repo.fetch_area(area_id)

        payload = dict(data or self._default_profile(area_id))
        sentiment_as_of = self._parse_dt(payload.get("sentiment_as_of"))
        development_as_of = self._parse_dt(payload.get("development_as_of"))
        sentiment_freshness = self._freshness_days(sentiment_as_of)
        development_freshness = self._freshness_days(development_as_of)
        payload["sentiment_freshness_days"] = sentiment_freshness
        payload["development_freshness_days"] = development_freshness
        payload["area_confidence"] = self._area_confidence(
            payload.get("sentiment_credibility"),
            sentiment_freshness,
            payload.get("development_credibility"),
            development_freshness,
        )
        return payload

    def refresh_area_data(self, area_id: str) -> None:
        """
        Fetches fresh data derived from official datasets (ERI + INE IPV).
        """
        try:
            area_id = area_id.lower().strip()
            now = datetime.utcnow()

            eri_signals = self.eri_service.get_signals(area_id, now, allow_proxy=False)
            eri_period = self.eri_repo.fetch_latest_period_date(area_id)
            eri_as_of = self._parse_dt(eri_period) or self._parse_dt(
                eri_signals.get("effective_date") if eri_signals else None
            )

            sentiment_score = 0.5
            sentiment_credibility = 0.2
            sentiment_as_of = None
            sources = set()
            summary_parts = []

            txn_z = self._coerce_float(eri_signals.get("txn_volume_z") if eri_signals else None)
            mortgage_share = self._coerce_float(eri_signals.get("mortgage_share") if eri_signals else None)

            if txn_z is not None:
                sentiment_score = self._score_from_z(txn_z)
                sentiment_credibility = 0.75
                sentiment_as_of = eri_as_of
                sources.add("official:eri_metrics")
                if mortgage_share is not None:
                    sentiment_score = self._clip(sentiment_score + (mortgage_share - 0.5) * 0.1, 0.0, 1.0)
                    sentiment_credibility = min(0.85, sentiment_credibility + 0.05)
            elif mortgage_share is not None:
                sentiment_score = self._clip(0.5 + (mortgage_share - 0.5) * 0.2, 0.0, 1.0)
                sentiment_credibility = 0.6
                sentiment_as_of = eri_as_of
                sources.add("official:eri_metrics")

            if sentiment_as_of:
                summary_parts.append(f"ERI liquidity as of {sentiment_as_of.date().isoformat()}")

            development_score = 0.5
            development_credibility = 0.2
            development_as_of = None
            growth_values = []
            dev_sources = set()

            registral_change = self._coerce_float(
                eri_signals.get("registral_price_sqm_change") if eri_signals else None
            )
            if registral_change is not None:
                growth_values.append(registral_change)
                dev_sources.add("official:eri_metrics")
                development_as_of = eri_as_of
                development_credibility = 0.75

            ine_value, ine_period, ine_region = self._fetch_ine_yoy(area_id)
            if ine_value is not None:
                growth_values.append(ine_value)
                if ine_region:
                    dev_sources.add(f"official:ine_ipv:{ine_region}")
                else:
                    dev_sources.add("official:ine_ipv")
                ine_dt = self._ine_period_to_date(ine_period) if ine_period else None
                if ine_dt and (development_as_of is None or ine_dt > development_as_of):
                    development_as_of = ine_dt
                base_cred = 0.7 if ine_region == area_id else 0.6
                development_credibility = max(development_credibility, base_cred)

            if growth_values:
                development_score = self._score_from_growth(sum(growth_values) / len(growth_values))
                if len(dev_sources) > 1:
                    development_credibility = min(0.9, development_credibility + 0.1)

            sources.update(dev_sources)

            if development_as_of:
                if "official:eri_metrics" in dev_sources and any(
                    s.startswith("official:ine_ipv") for s in dev_sources
                ):
                    label = "ERI + INE momentum"
                elif "official:eri_metrics" in dev_sources:
                    label = "ERI price momentum"
                else:
                    label = "INE IPV momentum"
                summary_parts.append(f"{label} as of {development_as_of.date().isoformat()}")

            if summary_parts:
                summary = "Official area signals: " + "; ".join(summary_parts) + "."
            else:
                summary = "No official area signals available; using neutral defaults."

            keywords = []
            if sources:
                keywords.append("official")
            if any("eri" in s for s in sources):
                keywords.extend(["eri", "registral", "liquidity"])
            if any("ine_ipv" in s for s in sources):
                keywords.extend(["ine", "ipv"])
            keywords = sorted(set(keywords))

            data = {
                "sentiment_score": float(sentiment_score),
                "sentiment_as_of": sentiment_as_of.isoformat() if sentiment_as_of else None,
                "sentiment_credibility": float(sentiment_credibility),
                "future_development_score": float(development_score),
                "development_as_of": development_as_of.isoformat() if development_as_of else None,
                "development_credibility": float(development_credibility),
                "news_summary": summary,
                "top_keywords": keywords,
                "source_urls": sorted(sources),
            }
            self.repo.save_area(area_id, data)
        except Exception as e:
            logger.error("area_intel_refresh_failed", area_id=area_id, error=str(e))

    def _is_stale(self, data: Dict[str, Any]) -> bool:
        if not data.get("last_updated"):
            return True
        last_upd = pd.to_datetime(data["last_updated"], format="mixed", errors="coerce")
        if pd.isna(last_upd):
            return True
        # Refresh if older than 30 days (official cadence is monthly/quarterly).
        return (datetime.utcnow() - last_upd).days > 30

    def _default_profile(self, area_id: str) -> Dict[str, Any]:
        return {
            "sentiment_score": 0.5,
            "sentiment_as_of": None,
            "sentiment_credibility": 0.2,
            "future_development_score": 0.5,
            "development_as_of": None,
            "development_credibility": 0.2,
            "news_summary": "No official data available.",
            "top_keywords": [],
            "source_urls": [],
        }

    def _fetch_ine_yoy(self, area_id: str) -> Tuple[Optional[float], Optional[str], Optional[str]]:
        candidates = [area_id, "national", "total nacional"]
        for region in candidates:
            record = self.ine_repo.fetch_latest_metric(region, housing_type="general", metric="yoy")
            if record:
                period, value = record
                return value, period, region
        return None, None, None

    def _parse_dt(self, value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, pd.Timestamp):
            return value.to_pydatetime()
        text = str(value).strip()
        if not text:
            return None
        dt = pd.to_datetime(text, format="mixed", errors="coerce")
        if pd.isna(dt):
            return None
        if isinstance(dt, pd.Timestamp):
            return dt.to_pydatetime()
        return dt

    def _ine_period_to_date(self, period: str) -> Optional[datetime]:
        text = str(period).strip()
        if not text:
            return None
        match = re.match(r"^(\d{4})-Q([1-4])$", text)
        if match:
            year = int(match.group(1))
            quarter = int(match.group(2))
            month = (quarter - 1) * 3 + 1
            return datetime(year, month, 1)
        return self._parse_dt(text)

    def _coerce_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            num = float(value)
        except (TypeError, ValueError):
            return None
        if pd.isna(num):
            return None
        return num

    def _clip(self, value: float, low: float, high: float) -> float:
        return float(max(low, min(high, value)))

    def _score_from_z(self, z: float, max_abs: float = 2.0) -> float:
        z = self._clip(z, -max_abs, max_abs)
        return float(0.5 + (z / (2.0 * max_abs)))

    def _score_from_growth(self, yoy: float, max_abs: float = 0.2) -> float:
        yoy = self._clip(yoy, -max_abs, max_abs)
        return float(0.5 + (yoy / (2.0 * max_abs)))

    def _freshness_days(self, as_of: Optional[datetime]) -> Optional[int]:
        if not as_of:
            return None
        return max(0, (datetime.utcnow().date() - as_of.date()).days)

    def _freshness_factor(self, days: Optional[int]) -> float:
        if days is None:
            return 0.6
        if days <= 60:
            return 1.0
        if days <= 120:
            return 0.85
        if days <= 240:
            return 0.7
        if days <= 365:
            return 0.5
        return 0.3

    def _signal_confidence(self, credibility: Optional[float], freshness_days: Optional[int]) -> float:
        base = 0.5 if credibility is None else float(credibility)
        return self._clip(base * self._freshness_factor(freshness_days), 0.0, 1.0)

    def _area_confidence(
        self,
        sentiment_credibility: Optional[float],
        sentiment_freshness: Optional[int],
        development_credibility: Optional[float],
        development_freshness: Optional[int],
    ) -> float:
        confidences = []
        if sentiment_credibility is not None or sentiment_freshness is not None:
            confidences.append(self._signal_confidence(sentiment_credibility, sentiment_freshness))
        if development_credibility is not None or development_freshness is not None:
            confidences.append(self._signal_confidence(development_credibility, development_freshness))
        if not confidences:
            return 0.5
        return float(min(confidences))
