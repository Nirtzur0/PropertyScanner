import json
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import text

from src.repositories.base import RepositoryBase


class AreaIntelligenceRepository(RepositoryBase):
    def ensure_table(self) -> None:
        query = text(
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
        with self.engine.begin() as conn:
            conn.execute(query)

    def fetch_area(self, area_id: str) -> Optional[Dict[str, Any]]:
        query = text(
            """
            SELECT sentiment_score, future_development_score, news_summary,
                   top_keywords, source_urls, last_updated
            FROM area_intelligence
            WHERE area_id = :area_id
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(query, {"area_id": area_id}).fetchone()
        if not row:
            return None
        return {
            "sentiment_score": row[0],
            "future_development_score": row[1],
            "news_summary": row[2],
            "top_keywords": json.loads(row[3]) if row[3] else [],
            "source_urls": json.loads(row[4]) if row[4] else [],
            "last_updated": row[5],
        }

    def save_area(self, area_id: str, data: Dict[str, Any]) -> None:
        query = text(
            """
            INSERT OR REPLACE INTO area_intelligence
            (area_id, last_updated, sentiment_score, future_development_score,
             news_summary, top_keywords, source_urls)
            VALUES (:area_id, :last_updated, :sentiment_score, :future_development_score,
                    :news_summary, :top_keywords, :source_urls)
            """
        )
        payload = {
            "area_id": area_id,
            "last_updated": datetime.now().isoformat(),
            "sentiment_score": data.get("sentiment_score"),
            "future_development_score": data.get("future_development_score"),
            "news_summary": data.get("news_summary"),
            "top_keywords": json.dumps(data.get("top_keywords", [])),
            "source_urls": json.dumps(data.get("source_urls", [])),
        }
        with self.engine.begin() as conn:
            conn.execute(query, payload)
