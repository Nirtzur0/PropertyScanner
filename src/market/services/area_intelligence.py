import logging
import math
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import pandas as pd
from sqlalchemy import text

from src.platform.config import DEFAULT_DB_PATH
from src.market.repositories.area_intelligence import AreaIntelligenceRepository
from src.platform.db.base import resolve_db_url
from src.market.repositories.eri_metrics import ERIMetricsRepository
from src.market.repositories.ine_ipv import IneIpvRepository
from src.market.services.eri_signals import ERISignalsService
from src.market.services.registry_canonical import RegistryCanonicalizer
from src.platform.settings import AppConfig
from src.platform.utils.config import load_app_config_safe

logger = logging.getLogger(__name__)

_GEOHASH_PRECISION = 6
_GEO_LOOKBACK_DAYS = 365
_GEO_HALF_LIFE_DAYS = 120
_GEO_MIN_SAMPLE = 6


class AreaIntelligenceService:
    """
    Service to fetch and manage external intelligence for areas (cities/neighborhoods).
    Uses official registry datasets (ERI and equivalents) plus INE IPV for Spain.
    """

    def __init__(
        self,
        db_path: str = str(DEFAULT_DB_PATH),
        db_url: Optional[str] = None,
        app_config: Optional[AppConfig] = None,
    ):
        self.app_config = app_config or load_app_config_safe()
        self.db_url = resolve_db_url(db_url=db_url, db_path=db_path)
        self.repo = AreaIntelligenceRepository(db_url=self.db_url)
        self.eri_service = ERISignalsService(db_url=self.db_url, app_config=self.app_config)
        self.eri_repo = ERIMetricsRepository(db_url=self.db_url)
        self.ine_repo = IneIpvRepository(db_url=self.db_url)
        self.canonicalizer = RegistryCanonicalizer(app_config=self.app_config)
        self.repo.ensure_table()

    def get_area_indicators(self, area_id: str, country_code: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieve stored intelligence for an area.
        If data is stale or missing, attempts to refresh it.
        """
        area_key = self._area_key(area_id, country_code)
        data = self.repo.fetch_area(area_key)
        if not data:
            legacy_key = area_id.lower().strip()
            if legacy_key != area_key:
                data = self.repo.fetch_area(legacy_key)

        if not data or self._is_stale(data):
            self.refresh_area_data(area_id, country_code=country_code, area_key=area_key)
            data = self.repo.fetch_area(area_key)

        payload = dict(data or self._default_profile(area_key))
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

    def refresh_area_data(
        self,
        area_id: str,
        *,
        country_code: Optional[str] = None,
        area_key: Optional[str] = None,
    ) -> None:
        """
        Fetches fresh data derived from official datasets (ERI + INE IPV).
        """
        try:
            area_key = area_key or self._area_key(area_id, country_code)
            geohash = self._extract_geohash(area_key)
            if geohash:
                data = self._build_geohash_profile(geohash)
                if data:
                    self.repo.save_area(area_key, data)
                return
            now = datetime.utcnow()

            eri_signals = self.eri_service.get_signals(
                area_key,
                now,
                allow_proxy=False,
                country_code=country_code,
            )
            eri_period = None
            if self._allow_ine(country_code):
                eri_period = self.eri_repo.fetch_latest_period_date(area_key)
            eri_as_of = self._parse_dt(eri_period) or self._parse_dt(
                eri_signals.get("effective_date") if eri_signals else None
            )

            sentiment_score = 0.5
            sentiment_credibility = 0.2
            sentiment_as_of = None
            sources = set()
            summary_parts = []

            registry_provider = eri_signals.get("registry_provider") if eri_signals else None
            registry_label = "ERI" if registry_provider == "eri_es" else "Registry"
            registry_source = "official:eri_metrics" if registry_provider == "eri_es" else "official:registry"
            if registry_provider and registry_provider != "eri_es":
                registry_source = f"official:registry:{registry_provider}"

            txn_z = self._coerce_float(eri_signals.get("txn_volume_z") if eri_signals else None)
            mortgage_share = self._coerce_float(eri_signals.get("mortgage_share") if eri_signals else None)

            if txn_z is not None:
                sentiment_score = self._score_from_z(txn_z)
                sentiment_credibility = 0.75
                sentiment_as_of = eri_as_of
                sources.add(registry_source)
                if mortgage_share is not None:
                    sentiment_score = self._clip(sentiment_score + (mortgage_share - 0.5) * 0.1, 0.0, 1.0)
                    sentiment_credibility = min(0.85, sentiment_credibility + 0.05)
            elif mortgage_share is not None:
                sentiment_score = self._clip(0.5 + (mortgage_share - 0.5) * 0.2, 0.0, 1.0)
                sentiment_credibility = 0.6
                sentiment_as_of = eri_as_of
                sources.add(registry_source)

            if sentiment_as_of:
                summary_parts.append(f"{registry_label} liquidity as of {sentiment_as_of.date().isoformat()}")

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
                dev_sources.add(registry_source)
                development_as_of = eri_as_of
                development_credibility = 0.75

            if self._allow_ine(country_code):
                ine_area_id = self._strip_country_prefix(area_key)
                ine_value, ine_period, ine_region = self._fetch_ine_yoy(ine_area_id)
                if ine_value is not None:
                    growth_values.append(ine_value)
                    if ine_region:
                        dev_sources.add(f"official:ine_ipv:{ine_region}")
                    else:
                        dev_sources.add("official:ine_ipv")
                    ine_dt = self._ine_period_to_date(ine_period) if ine_period else None
                    if ine_dt and (development_as_of is None or ine_dt > development_as_of):
                        development_as_of = ine_dt
                    base_cred = 0.7 if ine_region == ine_area_id else 0.6
                    development_credibility = max(development_credibility, base_cred)

            if growth_values:
                development_score = self._score_from_growth(sum(growth_values) / len(growth_values))
                if len(dev_sources) > 1:
                    development_credibility = min(0.9, development_credibility + 0.1)

            sources.update(dev_sources)

            if development_as_of:
                if registry_provider == "eri_es" and any(
                    s.startswith("official:ine_ipv") for s in dev_sources
                ):
                    label = "ERI + INE momentum"
                elif registry_provider == "eri_es":
                    label = "ERI price momentum"
                else:
                    label = "Registry price momentum"
                summary_parts.append(f"{label} as of {development_as_of.date().isoformat()}")

            if summary_parts:
                summary = "Official area signals: " + "; ".join(summary_parts) + "."
            else:
                summary = "No official area signals available; using neutral defaults."

            keywords = []
            if sources:
                keywords.append("official")
            if registry_provider == "eri_es":
                keywords.extend(["eri", "registral", "liquidity"])
            elif registry_provider:
                keywords.extend(["registry", "liquidity"])
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
            self.repo.save_area(area_key, data)
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

    def _area_key(self, area_id: str, country_code: Optional[str]) -> str:
        geohash = self._extract_geohash(area_id)
        if geohash:
            return f"geo:{geohash}"
        area_key = self.canonicalizer.canonicalize(area_id, country_code=country_code)
        if not area_key:
            area_key = area_id.lower().strip()
        return area_key

    @staticmethod
    def _allow_ine(country_code: Optional[str]) -> bool:
        if not country_code:
            return True
        return str(country_code).upper().strip() == "ES"

    def _fetch_ine_yoy(self, area_id: str) -> Tuple[Optional[float], Optional[str], Optional[str]]:
        candidates = [area_id, "national", "total nacional"]
        for region in candidates:
            record = self.ine_repo.fetch_latest_metric(region, housing_type="general", metric="yoy")
            if record:
                period, value = record
                return value, period, region
        return None, None, None

    @staticmethod
    def _strip_country_prefix(area_id: str) -> str:
        if ":" in area_id:
            return area_id.split(":", 1)[1]
        return area_id

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
        match = re.match(r"^(\d{4})-?Q([1-4])$", text)
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

    def _extract_geohash(self, area_id: Optional[str]) -> Optional[str]:
        if not area_id:
            return None
        text = str(area_id).strip().lower()
        candidate = None
        for prefix in ("geohash:", "geo:"):
            if prefix in text:
                candidate = text.split(prefix, 1)[1]
                break
        if candidate is None:
            candidate = text.split(":")[-1]
        if not re.fullmatch(r"[0-9b-hjkmnp-z]{4,}", candidate or ""):
            return None
        return candidate[:_GEOHASH_PRECISION]

    def _build_geohash_profile(self, geohash: str) -> Optional[Dict[str, Any]]:
        if not self.repo.has_table("listings"):
            return None
        if not self.repo.has_column("listings", "geohash"):
            return None
        prefix = f"{geohash}%"
        query = text(
            """
            SELECT
                price,
                surface_area_sqm,
                text_sentiment,
                image_sentiment,
                COALESCE(fetched_at, updated_at, listed_at) AS seen_at,
                city
            FROM listings
            WHERE geohash LIKE :prefix
              AND price > 0
              AND surface_area_sqm > 0
            """
        )
        df = pd.read_sql(query, self.repo.engine, params={"prefix": prefix})
        if df.empty:
            return None

        df["seen_at"] = pd.to_datetime(df["seen_at"], format="mixed", errors="coerce")
        cutoff = datetime.utcnow() - timedelta(days=_GEO_LOOKBACK_DAYS)
        df = df[df["seen_at"].isna() | (df["seen_at"] >= cutoff)]
        if df.empty:
            return None

        df["psqm"] = df["price"] / df["surface_area_sqm"]
        df = df[df["psqm"].between(200, 50000)]
        if df.empty or len(df) < _GEO_MIN_SAMPLE:
            return None

        def normalize_sentiment(value: Any) -> Optional[float]:
            if value is None or pd.isna(value):
                return None
            return self._clip(0.5 + 0.5 * float(value), 0.0, 1.0)

        def combine_sentiment(row: pd.Series) -> Optional[float]:
            values = []
            text_score = normalize_sentiment(row.get("text_sentiment"))
            image_score = normalize_sentiment(row.get("image_sentiment"))
            if text_score is not None:
                values.append(text_score)
            if image_score is not None:
                values.append(image_score)
            if not values:
                return None
            return float(sum(values) / len(values))

        def age_weight(ts: Any) -> float:
            if ts is None or pd.isna(ts):
                return 0.35
            age_days = max(0, (datetime.utcnow() - ts).days)
            return math.exp(-age_days / _GEO_HALF_LIFE_DAYS)

        df["local_sentiment"] = df.apply(combine_sentiment, axis=1)
        df["weight"] = df["seen_at"].apply(age_weight)

        sentiment_score = None
        sentiment_samples = 0
        sentiment_df = df[df["local_sentiment"].notna()]
        if not sentiment_df.empty:
            weight_sum = float(sentiment_df["weight"].sum())
            if weight_sum > 0:
                sentiment_score = float(
                    (sentiment_df["local_sentiment"] * sentiment_df["weight"]).sum() / weight_sum
                )
                sentiment_samples = int(len(sentiment_df))

        area_psqm = float(df["psqm"].median()) if df["psqm"].notna().any() else None
        city = self._infer_city(df)
        city_psqm = self._load_city_median_psqm(city, cutoff) if city else None
        premium_score = None
        premium_pct = None
        if area_psqm and city_psqm:
            premium_pct = self._clip((area_psqm / city_psqm) - 1.0, -0.2, 0.2)
            premium_score = self._clip(0.5 + premium_pct / 0.4, 0.0, 1.0)

        combined_score = sentiment_score
        if combined_score is None:
            combined_score = premium_score
        elif premium_score is not None:
            combined_score = (combined_score * 0.7) + (premium_score * 0.3)
        if combined_score is None:
            combined_score = 0.5
        combined_score = self._clip(combined_score, 0.0, 1.0)

        latest_seen = df["seen_at"].max()
        sentiment_as_of = None
        if latest_seen is not None and not pd.isna(latest_seen):
            sentiment_as_of = latest_seen.to_pydatetime()

        sample_size = max(sentiment_samples, int(len(df)))
        base_cred = min(0.85, 0.2 + 0.15 * math.log1p(sample_size))
        sentiment_freshness = self._freshness_days(sentiment_as_of)
        sentiment_credibility = self._clip(
            base_cred * self._freshness_factor(sentiment_freshness), 0.0, 1.0
        )

        summary_parts = [
            f"Local listing sentiment from {sample_size} listings in geohash {geohash}."
        ]
        if premium_pct is not None and city:
            summary_parts.append(f"Price premium {premium_pct * 100:+.1f}% vs {city}.")

        return {
            "sentiment_score": float(combined_score),
            "sentiment_as_of": sentiment_as_of.isoformat() if sentiment_as_of else None,
            "sentiment_credibility": float(sentiment_credibility),
            "future_development_score": 0.5,
            "development_as_of": None,
            "development_credibility": None,
            "news_summary": " ".join(summary_parts),
            "top_keywords": ["geohash", "listings", "local"],
            "source_urls": ["internal:listings"],
        }

    @staticmethod
    def _infer_city(df: pd.DataFrame) -> Optional[str]:
        if "city" not in df.columns:
            return None
        series = df["city"].dropna().astype(str).str.strip().str.lower()
        if series.empty:
            return None
        counts = series.value_counts()
        top_city = counts.index[0]
        top_count = int(counts.iloc[0])
        if top_count < max(3, int(len(series) * 0.4)):
            return None
        return top_city

    def _load_city_median_psqm(self, city: str, cutoff: datetime) -> Optional[float]:
        if not city:
            return None
        query = text(
            """
            SELECT
                price,
                surface_area_sqm,
                COALESCE(fetched_at, updated_at, listed_at) AS seen_at
            FROM listings
            WHERE LOWER(city) = :city
              AND price > 0
              AND surface_area_sqm > 0
            """
        )
        df = pd.read_sql(query, self.repo.engine, params={"city": city})
        if df.empty:
            return None
        df["seen_at"] = pd.to_datetime(df["seen_at"], format="mixed", errors="coerce")
        df = df[df["seen_at"].isna() | (df["seen_at"] >= cutoff)]
        if df.empty:
            return None
        df["psqm"] = df["price"] / df["surface_area_sqm"]
        df = df[df["psqm"].between(200, 50000)]
        if df.empty:
            return None
        median = df["psqm"].median()
        if pd.isna(median):
            return None
        return float(median)
