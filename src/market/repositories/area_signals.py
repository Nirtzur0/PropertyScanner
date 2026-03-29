"""Repository for area_signals table.

Replaces AreaIntelligenceRepository. Same schema, new table name.
"""

import json
from typing import Any, Dict, Optional

from sqlalchemy import text

from src.platform.db.base import RepositoryBase
from src.platform.utils.time import utcnow


class AreaSignalsRepository(RepositoryBase):
    """Access to area sentiment/development signals."""

    def fetch_area(self, area_id: str) -> Optional[Dict[str, Any]]:
        query = text(
            """
            SELECT sentiment_score, sentiment_as_of, sentiment_credibility,
                   future_development_score, development_as_of, development_credibility,
                   news_summary, top_keywords, source_urls, last_updated
            FROM area_signals
            WHERE area_id = :area_id
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(query, {"area_id": area_id}).fetchone()
        if not row:
            return None
        return {
            "sentiment_score": row[0],
            "sentiment_as_of": row[1],
            "sentiment_credibility": row[2],
            "future_development_score": row[3],
            "development_as_of": row[4],
            "development_credibility": row[5],
            "news_summary": row[6],
            "top_keywords": json.loads(row[7]) if row[7] else [],
            "source_urls": json.loads(row[8]) if row[8] else [],
            "last_updated": row[9],
        }

    def save_area(self, area_id: str, data: Dict[str, Any]) -> None:
        query = text(
            """
            INSERT OR REPLACE INTO area_signals
            (area_id, last_updated, sentiment_score, sentiment_as_of, sentiment_credibility,
             future_development_score, development_as_of, development_credibility,
             news_summary, top_keywords, source_urls)
            VALUES (:area_id, :last_updated, :sentiment_score, :sentiment_as_of, :sentiment_credibility,
                    :future_development_score, :development_as_of, :development_credibility,
                    :news_summary, :top_keywords, :source_urls)
            """
        )
        payload = {
            "area_id": area_id,
            "last_updated": utcnow().isoformat(),
            "sentiment_score": data.get("sentiment_score"),
            "sentiment_as_of": data.get("sentiment_as_of"),
            "sentiment_credibility": data.get("sentiment_credibility"),
            "future_development_score": data.get("future_development_score"),
            "development_as_of": data.get("development_as_of"),
            "development_credibility": data.get("development_credibility"),
            "news_summary": data.get("news_summary"),
            "top_keywords": json.dumps(data.get("top_keywords", [])),
            "source_urls": json.dumps(data.get("source_urls", [])),
        }
        with self.engine.begin() as conn:
            conn.execute(query, payload)
