from typing import Dict, List

from sqlalchemy import text

from src.platform.db.base import RepositoryBase


class OfficialMetricsRepository(RepositoryBase):
    table_name = "official_metrics"

    def ensure_schema(self) -> None:
        if self.has_table(self.table_name):
            return
        query = text(
            """
            CREATE TABLE IF NOT EXISTS official_metrics (
                id TEXT PRIMARY KEY,
                provider_id TEXT,
                region_id TEXT,
                period TEXT,
                period_date DATE,
                housing_type TEXT,
                metric TEXT,
                value FLOAT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        with self.engine.begin() as conn:
            conn.execute(query)
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_official_metrics_provider_region_date "
                    "ON official_metrics (provider_id, region_id, period_date)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_official_metrics_provider_region_metric "
                    "ON official_metrics (provider_id, region_id, metric, housing_type, period_date)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_official_metrics_provider_metric "
                    "ON official_metrics (provider_id, metric)"
                )
            )

    def _upsert_rows(self, rows: List[Dict[str, object]]) -> int:
        if not rows:
            return 0
        self.ensure_schema()
        query = text(
            """
            INSERT OR REPLACE INTO official_metrics
            (id, provider_id, region_id, period, period_date, housing_type, metric, value, updated_at)
            VALUES (
                :id, :provider_id, :region_id, :period, :period_date, :housing_type, :metric, :value, CURRENT_TIMESTAMP
            )
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(query, rows)
        return int(result.rowcount or 0)
