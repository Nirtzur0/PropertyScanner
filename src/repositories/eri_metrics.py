from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import text

from src.repositories.base import RepositoryBase


class ERIMetricsRepository(RepositoryBase):
    def ensure_schema(self) -> None:
        if self.has_table("eri_metrics"):
            return
        query = text(
            """
            CREATE TABLE IF NOT EXISTS eri_metrics (
                id TEXT PRIMARY KEY,
                region_id TEXT,
                period_date DATE,
                txn_count INT,
                mortgage_count INT,
                price_sqm FLOAT,
                price_sqm_yoy FLOAT,
                price_sqm_qoq FLOAT,
                updated_at DATETIME
            )
            """
        )
        with self.engine.begin() as conn:
            conn.execute(query)
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_eri_region_date ON eri_metrics (region_id, period_date)")
            )

    def upsert_records(self, records: List[Dict[str, object]]) -> int:
        if not records:
            return 0
        self.ensure_schema()
        query = text(
            """
            INSERT OR REPLACE INTO eri_metrics
            (id, region_id, period_date, txn_count, mortgage_count, price_sqm, updated_at)
            VALUES (:id, :region_id, :period_date, :txn_count, :mortgage_count, :price_sqm, CURRENT_TIMESTAMP)
            """
        )
        payloads = []
        for record in records:
            payloads.append(
                {
                    "id": record["id"],
                    "region_id": record["region_id"],
                    "period_date": record["period_date"],
                    "txn_count": record["txn_count"],
                    "mortgage_count": record["mortgage_count"],
                    "price_sqm": record["price_sqm"],
                }
            )
        with self.engine.begin() as conn:
            result = conn.execute(query, payloads)
        return int(result.rowcount or 0)

    def load_series(self, region_id: str) -> pd.DataFrame:
        query = text(
            """
            SELECT
                period_date,
                txn_count,
                mortgage_count,
                price_sqm,
                price_sqm_yoy,
                price_sqm_qoq
            FROM eri_metrics
            WHERE region_id = :region_id
            ORDER BY period_date ASC
            """
        )
        return pd.read_sql(query, self.engine, params={"region_id": region_id})

    def fetch_latest_period_date(self, region_id: str) -> Optional[pd.Timestamp]:
        query = text(
            """
            SELECT period_date
            FROM eri_metrics
            WHERE LOWER(region_id) = :region_id
            ORDER BY period_date DESC
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(query, {"region_id": region_id.lower().strip()}).fetchone()
        if not row or row[0] is None:
            return None
        dt = pd.to_datetime(row[0], format="mixed", errors="coerce")
        if pd.isna(dt):
            return None
        return dt
