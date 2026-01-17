from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import text

from src.platform.db.base import RepositoryBase


class RegistryMetricsRepository(RepositoryBase):
    table_name: str = ""
    provider_id: str = ""

    def ensure_schema(self) -> None:
        if not self.table_name:
            raise ValueError("registry_table_name_missing")
        if self.has_table(self.table_name):
            return
        query = text(
            f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
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
                text(
                    f"CREATE INDEX IF NOT EXISTS ix_{self.table_name}_region_date ON {self.table_name} (region_id, period_date)"
                )
            )

    def upsert_records(self, records: List[Dict[str, object]]) -> int:
        if not records:
            return 0
        self.ensure_schema()
        query = text(
            f"""
            INSERT OR REPLACE INTO {self.table_name}
            (id, region_id, period_date, txn_count, mortgage_count, price_sqm, price_sqm_yoy, price_sqm_qoq, updated_at)
            VALUES (
                :id, :region_id, :period_date, :txn_count, :mortgage_count, :price_sqm, :price_sqm_yoy, :price_sqm_qoq, CURRENT_TIMESTAMP
            )
            """
        )
        payloads = []
        for record in records:
            payloads.append(
                {
                    "id": record["id"],
                    "region_id": record["region_id"],
                    "period_date": record["period_date"],
                    "txn_count": record.get("txn_count"),
                    "mortgage_count": record.get("mortgage_count"),
                    "price_sqm": record.get("price_sqm"),
                    "price_sqm_yoy": record.get("price_sqm_yoy"),
                    "price_sqm_qoq": record.get("price_sqm_qoq"),
                }
            )
        with self.engine.begin() as conn:
            result = conn.execute(query, payloads)
        return int(result.rowcount or 0)

    def load_series(self, region_id: str) -> pd.DataFrame:
        query = text(
            f"""
            SELECT
                period_date,
                txn_count,
                mortgage_count,
                price_sqm,
                price_sqm_yoy,
                price_sqm_qoq
            FROM {self.table_name}
            WHERE region_id = :region_id
            ORDER BY period_date ASC
            """
        )
        return pd.read_sql(query, self.engine, params={"region_id": region_id})

    def fetch_latest_period_date(self, region_id: str) -> Optional[pd.Timestamp]:
        query = text(
            f"""
            SELECT period_date
            FROM {self.table_name}
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
