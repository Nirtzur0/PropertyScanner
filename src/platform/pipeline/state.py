from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
import os

from src.platform.settings import AppConfig, PathsConfig
from src.listings.repositories.listings import ListingsRepository
from src.market.repositories.market_fundamentals import MarketFundamentalsRepository
from src.market.repositories.macro_context import MacroContextRepository
from src.platform.db.base import resolve_db_url
from src.platform.utils.time import utcfromtimestamp, utcnow


@dataclass
class PipelinePolicy:
    max_listing_age_days: int = 7
    max_market_data_age_days: int = 30
    min_listings_for_training: int = 200


@dataclass
class PipelineState:
    listings_count: int
    listings_last_seen: Optional[datetime]
    market_data_at: Optional[datetime]
    index_at: Optional[datetime]
    model_at: Optional[datetime]
    needs_crawl: bool
    needs_market_data: bool
    needs_index: bool
    needs_training: bool
    needs_refresh: bool
    reasons: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "listings_count": self.listings_count,
            "listings_last_seen": self._serialize_dt(self.listings_last_seen),
            "market_data_at": self._serialize_dt(self.market_data_at),
            "index_at": self._serialize_dt(self.index_at),
            "model_at": self._serialize_dt(self.model_at),
            "needs_crawl": self.needs_crawl,
            "needs_market_data": self.needs_market_data,
            "needs_index": self.needs_index,
            "needs_training": self.needs_training,
            "needs_refresh": self.needs_refresh,
            "reasons": self.reasons,
        }

    @staticmethod
    def _serialize_dt(value: Optional[datetime]) -> Optional[str]:
        if not value:
            return None
        return value.isoformat()


class PipelineStateService:
    def __init__(
        self,
        *,
        db_url: Optional[str] = None,
        db_path: Optional[str] = None,
        policy: Optional[PipelinePolicy] = None,
        paths: Optional[PathsConfig] = None,
        app_config: Optional[AppConfig] = None,
    ) -> None:
        self.paths = paths or (app_config.paths if app_config is not None else PathsConfig())
        self.app_config = app_config
        if db_path is None:
            db_path = str(self.paths.default_db_path)
        resolved = resolve_db_url(db_url=db_url, db_path=db_path)
        self.listings_repo = ListingsRepository(db_url=resolved)
        self.market_repo = MarketFundamentalsRepository(db_url=resolved)
        self.macro_repo = MacroContextRepository(db_url=resolved)
        self.policy = policy or PipelinePolicy()

    def snapshot(self) -> PipelineState:
        listing_snapshot = self.listings_repo.get_listing_snapshot()
        listings_count = listing_snapshot["count"]
        listings_last_seen = listing_snapshot["last_seen"]

        market_data_at = self._market_data_timestamp()
        index_paths = [self.paths.vector_metadata_path, self.paths.lancedb_path]
        index_at = self._file_timestamp(index_paths, use_oldest=True)
        model_at = self._file_timestamp([self.paths.fusion_model_path], use_oldest=False)

        now = utcnow()
        reasons: List[str] = []

        needs_crawl = listings_count == 0
        if listings_last_seen and not needs_crawl:
            age_days = (now - listings_last_seen).days
            if age_days > self.policy.max_listing_age_days:
                needs_crawl = True
                reasons.append("listings_stale")
        if listings_count == 0:
            reasons.append("no_listings")

        needs_market_data = market_data_at is None
        if market_data_at is None:
            reasons.append("market_data_missing")
        else:
            if listings_last_seen and market_data_at < listings_last_seen:
                needs_market_data = True
                reasons.append("market_data_behind_listings")
            if (now - market_data_at).days > self.policy.max_market_data_age_days:
                needs_market_data = True
                reasons.append("market_data_stale")

        needs_index = False
        if listings_count > 0:
            needs_index = index_at is None
            if index_at is None:
                reasons.append("index_missing")
            elif listings_last_seen and index_at < listings_last_seen:
                needs_index = True
                reasons.append("index_behind_listings")

        needs_training = False
        if listings_count >= self.policy.min_listings_for_training:
            needs_training = model_at is None
            if model_at is None:
                reasons.append("model_missing")
            elif listings_last_seen and model_at < listings_last_seen:
                needs_training = True
                reasons.append("model_behind_listings")
        else:
            reasons.append("insufficient_listings_for_training")

        needs_refresh = any([needs_crawl, needs_market_data, needs_index, needs_training])

        return PipelineState(
            listings_count=listings_count,
            listings_last_seen=listings_last_seen,
            market_data_at=market_data_at,
            index_at=index_at,
            model_at=model_at,
            needs_crawl=needs_crawl,
            needs_market_data=needs_market_data,
            needs_index=needs_index,
            needs_training=needs_training,
            needs_refresh=needs_refresh,
            reasons=reasons,
        )

    def _market_data_timestamp(self) -> Optional[datetime]:
        timestamps = [
            self.market_repo.get_market_last_updated_at(),
            self.market_repo.get_hedonic_last_updated_at(),
            self.macro_repo.get_actuals_last_updated_at(),
        ]
        timestamps = [t for t in timestamps if t is not None]
        if not timestamps:
            return None
        return max(timestamps)

    @staticmethod
    def _file_timestamp(paths: List[os.PathLike], *, use_oldest: bool) -> Optional[datetime]:
        times = []
        for path in paths:
            if path and os.path.exists(path):
                times.append(utcfromtimestamp(os.path.getmtime(path)))
        if not times:
            return None
        return min(times) if use_oldest else max(times)
