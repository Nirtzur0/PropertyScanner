"""Consolidated repository for macro_context table.

Replaces MacroIndicatorsRepository and MacroScenariosRepository.
Stores both actual macro indicators and forecast scenarios in one table
distinguished by context_type ('actual' vs 'forecast').
"""

from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import text

from src.platform.db.base import RepositoryBase
from src.platform.utils.time import utcnow


class MacroContextRepository(RepositoryBase):
    """Unified access to macro indicators + scenarios."""

    # -- Actual indicators (replaces MacroIndicatorsRepository) --

    def upsert_actuals(self, records: List[tuple]) -> None:
        """Upsert actual macro indicator records.

        Each record is (month, euribor_12m, ecb_deposit_rate, idealista_national, idealista_madrid).
        """
        if not records:
            return
        query = text(
            """
            INSERT OR REPLACE INTO macro_context
            (id, date, context_type, euribor_12m, ecb_deposit_rate,
             idealista_index_national, idealista_index_madrid, updated_at)
            VALUES (:id, :date, 'actual', :euribor_12m, :ecb_deposit_rate,
                    :idealista_index_national, :idealista_index_madrid, :updated_at)
            """
        )
        now = utcnow().isoformat()
        payloads = []
        for record in records:
            month, euribor, ecb, ideal_nat, ideal_mad = record
            payloads.append({
                "id": f"actual|{month}",
                "date": month,
                "euribor_12m": euribor,
                "ecb_deposit_rate": ecb,
                "idealista_index_national": ideal_nat,
                "idealista_index_madrid": ideal_mad,
                "updated_at": now,
            })
        with self.engine.begin() as conn:
            conn.execute(query, payloads)

    def get_actuals_last_updated_at(self) -> Optional[pd.Timestamp]:
        query = text("SELECT MAX(updated_at) FROM macro_context WHERE context_type = 'actual'")
        with self.engine.connect() as conn:
            row = conn.execute(query).fetchone()
        ts = pd.to_datetime(row[0], format="mixed", errors="coerce") if row and row[0] else None
        if pd.isna(ts) or ts is None:
            fallback = text("SELECT MAX(date) FROM macro_context WHERE context_type = 'actual'")
            with self.engine.connect() as conn:
                row = conn.execute(fallback).fetchone()
            ts = pd.to_datetime(row[0], format="mixed", errors="coerce") if row and row[0] else None
            if pd.isna(ts):
                return None
        return ts

    # -- Forecast scenarios (replaces MacroScenariosRepository) --

    def upsert_forecasts(self, records: List[Dict[str, object]]) -> int:
        if not records:
            return 0
        query = text(
            """
            INSERT OR REPLACE INTO macro_context
            (id, date, context_type, scenario_name, source_id, source_url,
             horizon_year, euribor_12m, inflation, gdp_growth,
             confidence_text, updated_at)
            VALUES (:id, :date, 'forecast', :scenario_name, :source_id, :source_url,
                    :horizon_year, :euribor_12m, :inflation, :gdp_growth,
                    :confidence_text, :updated_at)
            """
        )
        payloads = []
        for record in records:
            source_id = record.get("source_id") or ""
            scenario_name = record.get("scenario_name") or ""
            horizon_year = record.get("horizon_year") or ""
            row_id = f"forecast|{source_id}|{scenario_name}|{horizon_year}"
            payloads.append({
                "id": row_id,
                "date": record.get("date"),
                "scenario_name": scenario_name,
                "source_id": source_id,
                "source_url": record.get("source_url"),
                "horizon_year": record.get("horizon_year"),
                "euribor_12m": record.get("euribor_12m_forecast"),
                "inflation": record.get("inflation_forecast"),
                "gdp_growth": record.get("gdp_growth_forecast"),
                "confidence_text": record.get("confidence_text"),
                "updated_at": record.get("retrieved_at") or utcnow().isoformat(),
            })
        with self.engine.begin() as conn:
            result = conn.execute(query, payloads)
        return int(result.rowcount or 0)
