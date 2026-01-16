import pandas as pd
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from src.core.config import DEFAULT_DB_PATH
from src.repositories.area_intelligence import AreaIntelligenceRepository
from src.repositories.base import resolve_db_url
from src.repositories.market_indices import MarketIndicesRepository

logger = logging.getLogger(__name__)


class AreaIntelligenceService:
    """
    Service to fetch and manage external intelligence for areas (cities/neighborhoods).
    Simulates web crawling/scraping for news, sentiment, and development plans.
    """

    def __init__(self, db_path: str = str(DEFAULT_DB_PATH), db_url: Optional[str] = None):
        self.db_url = resolve_db_url(db_url=db_url, db_path=db_path)
        self.repo = AreaIntelligenceRepository(db_url=self.db_url)
        self.market_repo = MarketIndicesRepository(db_url=self.db_url)
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

        return data or self._default_profile(area_id)

    def refresh_area_data(self, area_id: str) -> None:
        """
        Fetches fresh data derived from internal Market Indices.
        Replaces simulation with data-driven signals.
        """
        try:
            latest = self.market_repo.fetch_latest_snapshot(area_id)
            if not latest:
                logger.warning("area_no_data", area_id=area_id)
                return

            price_sqm, inventory, new_listings = latest

            # Calculate simple Sentiment based on activity
            sentiment = 0.5
            if new_listings and inventory:
                turnover = new_listings / max(inventory, 1)
                sentiment = 0.5 + min(turnover, 0.4)

            dev_score = 0.5

            summary = (
                f"Market Data for {area_id.title()}: "
                f"Avg Price {price_sqm:.2f} €/m², "
                f"Active Listings: {inventory}, "
                f"New This Month: {new_listings}."
            )
            keywords = ["data-driven", "market-stats", "real-time"]

            data = {
                "sentiment_score": float(sentiment),
                "future_development_score": float(dev_score),
                "news_summary": summary,
                "top_keywords": keywords,
                "source_urls": ["internal:market_indices"],
            }
            self.repo.save_area(area_id, data)

        except Exception as e:
            logger.error(f"Failed to refresh area data for {area_id}: {e}")

    def _is_stale(self, data: Dict[str, Any]) -> bool:
        if not data.get("last_updated"):
            return True
        last_upd = pd.to_datetime(data["last_updated"])
        # Refresh if older than 7 days
        return (datetime.now() - last_upd).days > 7

    def _default_profile(self, area_id: str) -> Dict[str, Any]:
        return {
            "sentiment_score": 0.5,
            "future_development_score": 0.5,
            "news_summary": "No data available.",
            "top_keywords": [],
            "source_urls": [],
        }
