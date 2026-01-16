from typing import List, Optional, Tuple

from sqlalchemy import text

from src.repositories.base import RepositoryBase


class IneIpvRepository(RepositoryBase):
    def ensure_schema(self) -> None:
        if self.has_table("ine_ipv"):
            return
        query = text(
            """
            CREATE TABLE IF NOT EXISTS ine_ipv (
                period TEXT,
                region_id TEXT,
                housing_type TEXT,
                metric TEXT,
                value FLOAT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (period, region_id, housing_type, metric)
            )
            """
        )
        with self.engine.begin() as conn:
            conn.execute(query)

    def upsert_records(self, records: List[Tuple[str, str, str, str, float]]) -> int:
        if not records:
            return 0
        self.ensure_schema()
        query = text(
            """
            INSERT OR REPLACE INTO ine_ipv
            (period, region_id, housing_type, metric, value)
            VALUES (:period, :region_id, :housing_type, :metric, :value)
            """
        )
        payloads = [
            {
                "period": period,
                "region_id": region_id,
                "housing_type": housing_type,
                "metric": metric,
                "value": value,
            }
            for period, region_id, housing_type, metric, value in records
        ]
        with self.engine.begin() as conn:
            result = conn.execute(query, payloads)
        return int(result.rowcount or 0)

    def fetch_latest_metric(
        self,
        region_id: str,
        housing_type: str = "general",
        metric: str = "yoy",
    ) -> Optional[Tuple[str, float]]:
        query = text(
            """
            SELECT period, value
            FROM ine_ipv
            WHERE LOWER(region_id) = :region_id
              AND housing_type = :housing_type
              AND metric = :metric
            ORDER BY period DESC
            LIMIT 1
            """
        )
        params = {
            "region_id": region_id.lower().strip(),
            "housing_type": housing_type,
            "metric": metric,
        }
        with self.engine.connect() as conn:
            row = conn.execute(query, params).fetchone()
        if not row or row[1] is None:
            return None
        return str(row[0]), float(row[1])
