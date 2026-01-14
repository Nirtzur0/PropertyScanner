import sqlite3
import pandas as pd
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import json

logger = logging.getLogger(__name__)

class AreaIntelligenceService:
    """
    Service to fetch and manage external intelligence for areas (cities/neighborhoods).
    Simulates web crawling/scraping for news, sentiment, and development plans.
    """

    def __init__(self, db_path: str = "data/listings.db"):
        self.db_path = db_path
        self._ensure_table()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _ensure_table(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS area_intelligence (
                    area_id TEXT PRIMARY KEY,
                    last_updated DATETIME,
                    sentiment_score FLOAT,
                    future_development_score FLOAT,
                    news_summary TEXT,
                    top_keywords TEXT,
                    source_urls TEXT
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def get_area_indicators(self, area_id: str) -> Dict[str, Any]:
        """
        Retrieve stored intelligence for an area.
        If data is stale or missing, attempts to refresh it.
        """
        area_id = area_id.lower().strip()
        data = self._load_from_db(area_id)

        if not data or self._is_stale(data):
            self.refresh_area_data(area_id)
            data = self._load_from_db(area_id)

        return data or self._default_profile(area_id)

    def refresh_area_data(self, area_id: str):
        """
        Fetches fresh data (simulated crawling) and updates the database.
        """
        try:
            # In a real scenario, this would call external APIs or run a scraper
            crawled_data = self._simulate_crawl(area_id)
            self._save_to_db(area_id, crawled_data)
        except Exception as e:
            logger.error(f"Failed to refresh area data for {area_id}: {e}")

    def _simulate_crawl(self, area_id: str) -> Dict[str, Any]:
        """
        Simulate gathering data from the web.
        Logic:
        - Big cities (Madrid, Barcelona) get 'booming' stats.
        - Others get random or neutral stats.
        """
        # Heuristic rules for simulation
        is_major = any(c in area_id for c in ["madrid", "barcelona", "valencia", "malaga"])

        if is_major:
            sentiment = 0.7 + (hash(area_id) % 20) / 100.0 # 0.7 to 0.9
            dev_score = 0.6 + (hash(area_id) % 30) / 100.0 # 0.6 to 0.9
            summary = f"Strong economic indicators and high demand in {area_id.title()}."
            keywords = ["growth", "tourism", "tech hub", "infrastructure"]
        else:
            sentiment = 0.4 + (hash(area_id) % 20) / 100.0 # 0.4 to 0.6
            dev_score = 0.3 + (hash(area_id) % 30) / 100.0 # 0.3 to 0.6
            summary = f"Stable market conditions in {area_id.title()}."
            keywords = ["stable", "residential", "local market"]

        return {
            "sentiment_score": sentiment,
            "future_development_score": dev_score,
            "news_summary": summary,
            "top_keywords": keywords,
            "source_urls": [f"https://news.example.com/{area_id}", f"https://city-planning.example.com/{area_id}"]
        }

    def _load_from_db(self, area_id: str) -> Optional[Dict[str, Any]]:
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT sentiment_score, future_development_score, news_summary, top_keywords, source_urls, last_updated
                FROM area_intelligence WHERE area_id = ?
            """, (area_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "sentiment_score": row[0],
                    "future_development_score": row[1],
                    "news_summary": row[2],
                    "top_keywords": json.loads(row[3]) if row[3] else [],
                    "source_urls": json.loads(row[4]) if row[4] else [],
                    "last_updated": row[5]
                }
        except Exception as e:
            logger.error(f"db_load_error: {e}")
        finally:
            conn.close()
        return None

    def _save_to_db(self, area_id: str, data: Dict[str, Any]):
        conn = self._connect()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO area_intelligence
                (area_id, last_updated, sentiment_score, future_development_score, news_summary, top_keywords, source_urls)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                area_id,
                datetime.now().isoformat(),
                data["sentiment_score"],
                data["future_development_score"],
                data["news_summary"],
                json.dumps(data["top_keywords"]),
                json.dumps(data["source_urls"])
            ))
            conn.commit()
        except Exception as e:
            logger.error(f"db_save_error: {e}")
        finally:
            conn.close()

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
            "source_urls": []
        }
