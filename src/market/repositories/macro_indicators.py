from datetime import datetime
from typing import List, Optional, Tuple

import pandas as pd
from sqlalchemy import text

from src.platform.db.base import RepositoryBase
from src.platform.utils.time import utcnow


class MacroIndicatorsRepository(RepositoryBase):
    def upsert_records(self, records: List[Tuple]) -> None:
        if not records:
            return
        has_updated = self.has_column("macro_indicators", "updated_at")
        if has_updated:
            query = text(
                """
                INSERT OR REPLACE INTO macro_indicators
                (date, euribor_12m, ecb_deposit_rate, idealista_index_national, idealista_index_madrid, updated_at)
                VALUES (:date, :euribor_12m, :ecb_deposit_rate, :idealista_index_national, :idealista_index_madrid, :updated_at)
                """
            )
        else:
            query = text(
                """
                INSERT OR REPLACE INTO macro_indicators
                (date, euribor_12m, ecb_deposit_rate, idealista_index_national, idealista_index_madrid)
                VALUES (:date, :euribor_12m, :ecb_deposit_rate, :idealista_index_national, :idealista_index_madrid)
                """
            )
        now = utcnow().isoformat()
        payloads = []
        for record in records:
            month, euribor, ecb, ideal_nat, ideal_mad = record
            payload = {
                "date": month,
                "euribor_12m": euribor,
                "ecb_deposit_rate": ecb,
                "idealista_index_national": ideal_nat,
                "idealista_index_madrid": ideal_mad,
            }
            if has_updated:
                payload["updated_at"] = now
            payloads.append(payload)
        with self.engine.begin() as conn:
            conn.execute(query, payloads)

    def get_last_updated_at(self) -> Optional[pd.Timestamp]:
        query = text("SELECT MAX(updated_at) as last_updated FROM macro_indicators")
        with self.engine.connect() as conn:
            row = conn.execute(query).fetchone()
        last_updated = pd.to_datetime(row[0], format="mixed", errors="coerce") if row and row[0] else None
        if pd.isna(last_updated) or last_updated is None:
            fallback = text("SELECT MAX(date) as last_date FROM macro_indicators")
            with self.engine.connect() as conn:
                row = conn.execute(fallback).fetchone()
            last_date = pd.to_datetime(row[0], format="mixed", errors="coerce") if row and row[0] else None
            if pd.isna(last_date):
                return None
            return last_date
        return last_updated
