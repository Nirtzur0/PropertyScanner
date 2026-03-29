"""Consolidated repository for market_fundamentals table.

Replaces MarketIndicesRepository and HedonicIndicesRepository.
Stores both market indices and hedonic indices in a single table
keyed on (region_id, month_date, source).
"""

from typing import List, Optional, Tuple

import pandas as pd
from sqlalchemy import text

from src.platform.db.base import RepositoryBase


class MarketFundamentalsRepository(RepositoryBase):
    """Unified access to market + hedonic index data."""

    # -- Market index reads (replaces MarketIndicesRepository) --

    def fetch_index_value(self, region_id: str, month_date: str, index_type: str = "price") -> Optional[float]:
        index_type = str(index_type).strip().lower()
        if index_type not in {"price", "rent"}:
            raise ValueError("invalid_index_type")

        month_key = str(month_date).strip()[:7]
        column = "price_index_sqm" if index_type == "price" else "rent_index_sqm"
        query = text(
            f"""
            SELECT {column}
            FROM market_fundamentals
            WHERE source = 'market'
              AND region_id = :region_id
              AND substr(month_date, 1, 7) = :month_key
            ORDER BY month_date DESC
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(query, {"region_id": region_id, "month_key": month_key}).fetchone()
        if not row:
            return None
        return float(row[0]) if row[0] is not None else None

    def fetch_latest_market_snapshot(self, region_id: str) -> Optional[Tuple[float, int, int]]:
        query = text(
            """
            SELECT price_index_sqm, inventory_count, new_listings_count
            FROM market_fundamentals
            WHERE source = 'market' AND region_id = :region_id
            ORDER BY month_date DESC
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(query, {"region_id": region_id}).fetchone()
        if not row:
            return None
        return row[0], row[1], row[2]

    def fetch_market_series(self, region_id: str) -> pd.DataFrame:
        query = text(
            """
            SELECT month_date, price_index_sqm, rent_index_sqm, inventory_count, new_listings_count
            FROM market_fundamentals
            WHERE source = 'market' AND region_id = :region_id
            ORDER BY month_date ASC
            """
        )
        return pd.read_sql(query, self.engine, params={"region_id": region_id})

    def get_market_last_updated_at(self) -> Optional[pd.Timestamp]:
        query = text("SELECT MAX(updated_at) FROM market_fundamentals WHERE source = 'market'")
        with self.engine.connect() as conn:
            row = conn.execute(query).fetchone()
        ts = pd.to_datetime(row[0], format="mixed", errors="coerce") if row and row[0] else None
        if pd.isna(ts) or ts is None:
            fallback = text("SELECT MAX(month_date) FROM market_fundamentals WHERE source = 'market'")
            with self.engine.connect() as conn:
                row = conn.execute(fallback).fetchone()
            ts = pd.to_datetime(row[0], format="mixed", errors="coerce") if row and row[0] else None
            if pd.isna(ts):
                return None
        return ts

    def upsert_market_records(self, records: List[Tuple]) -> None:
        if not records:
            return
        query = text(
            """
            INSERT OR REPLACE INTO market_fundamentals (
                id, region_id, month_date, source,
                price_index_sqm, rent_index_sqm,
                inventory_count, new_listings_count, sold_count, absorption_rate,
                median_dom, price_cut_share, volatility_3m, updated_at
            ) VALUES (
                :id, :region_id, :month_date, 'market',
                :price_index_sqm, :rent_index_sqm,
                :inventory_count, :new_listings_count, :sold_count, :absorption_rate,
                :median_dom, :price_cut_share, :volatility_3m, :updated_at
            )
            """
        )
        payloads = []
        for record in records:
            (
                record_id, region_id, month_date,
                price_index, rent_index, inventory, new_count,
                sold_count, absorption, median_dom,
                price_cut_share, volatility, updated_at,
            ) = record
            payloads.append({
                "id": record_id,
                "region_id": region_id,
                "month_date": month_date,
                "price_index_sqm": price_index,
                "rent_index_sqm": rent_index,
                "inventory_count": inventory,
                "new_listings_count": new_count,
                "sold_count": sold_count,
                "absorption_rate": absorption,
                "median_dom": median_dom,
                "price_cut_share": price_cut_share,
                "volatility_3m": volatility,
                "updated_at": updated_at,
            })
        with self.engine.begin() as conn:
            conn.execute(query, payloads)

    # -- Hedonic index reads (replaces HedonicIndicesRepository) --

    def fetch_hedonic_index(self, region_id: str, month_prefix: str) -> Optional[Tuple[float, float, int]]:
        query = text(
            """
            SELECT hedonic_index_sqm, r_squared, n_observations
            FROM market_fundamentals
            WHERE source = 'hedonic'
              AND region_id = :region_id
              AND month_date LIKE :month_prefix
            ORDER BY month_date DESC
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(query, {"region_id": region_id, "month_prefix": f"{month_prefix}%"}).fetchone()
        if not row:
            return None
        return float(row[0]), float(row[1] or 0.0), int(row[2] or 0)

    def fetch_latest_hedonic_index(self, region_id: str) -> Optional[Tuple[float, float, int, str]]:
        query = text(
            """
            SELECT hedonic_index_sqm, r_squared, n_observations, month_date
            FROM market_fundamentals
            WHERE source = 'hedonic' AND region_id = :region_id
            ORDER BY month_date DESC
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(query, {"region_id": region_id}).fetchone()
        if not row:
            return None
        return float(row[0]), float(row[1] or 0.0), int(row[2] or 0), str(row[3])

    def fetch_hedonic_series(self, region_id: str, start_month: str, end_month: str) -> pd.DataFrame:
        query = text(
            """
            SELECT month_date, hedonic_index_sqm
            FROM market_fundamentals
            WHERE source = 'hedonic'
              AND region_id = :region_id
              AND month_date >= :start_month
              AND month_date <= :end_month
            ORDER BY month_date ASC
            """
        )
        return pd.read_sql(
            query, self.engine,
            params={"region_id": region_id, "start_month": start_month, "end_month": end_month},
        )

    def get_hedonic_last_updated_at(self) -> Optional[pd.Timestamp]:
        query = text("SELECT MAX(updated_at) FROM market_fundamentals WHERE source = 'hedonic'")
        with self.engine.connect() as conn:
            row = conn.execute(query).fetchone()
        ts = pd.to_datetime(row[0], format="mixed", errors="coerce") if row and row[0] else None
        if pd.isna(ts):
            return None
        return ts

    def upsert_hedonic_records(self, records: List[Tuple]) -> None:
        if not records:
            return
        query = text(
            """
            INSERT OR REPLACE INTO market_fundamentals (
                id, region_id, month_date, source,
                hedonic_index_sqm, raw_median_sqm, r_squared,
                n_observations, n_neighborhoods, coefficients, updated_at
            ) VALUES (
                :id, :region_id, :month_date, 'hedonic',
                :hedonic_index_sqm, :raw_median_sqm, :r_squared,
                :n_observations, :n_neighborhoods, :coefficients, :updated_at
            )
            """
        )
        payloads = []
        for record in records:
            (
                record_id, region_id, month_date,
                hedonic_index, raw_median, r_squared,
                n_obs, n_neighborhoods, coefficients, updated_at,
            ) = record
            payloads.append({
                "id": record_id,
                "region_id": region_id,
                "month_date": month_date,
                "hedonic_index_sqm": hedonic_index,
                "raw_median_sqm": raw_median,
                "r_squared": r_squared,
                "n_observations": n_obs,
                "n_neighborhoods": n_neighborhoods,
                "coefficients": coefficients,
                "updated_at": updated_at,
            })
        with self.engine.begin() as conn:
            conn.execute(query, payloads)

    # -- Combined queries (replaces MarketDataRepository JOINs) --

    def load_price_series(self, region_id: str, index_source: str = "market") -> pd.DataFrame:
        """Load price index history joined with macro context."""
        if index_source == "hedonic":
            query = text(
                """
                SELECT
                    h.month_date,
                    h.hedonic_index_sqm as index_value,
                    m.inventory_count,
                    mc.euribor_12m,
                    mc.ecb_deposit_rate
                FROM market_fundamentals h
                LEFT JOIN market_fundamentals m
                    ON h.region_id = m.region_id AND h.month_date = m.month_date AND m.source = 'market'
                LEFT JOIN macro_context mc
                    ON h.month_date = mc.date AND mc.context_type = 'actual'
                WHERE h.source = 'hedonic' AND h.region_id = :region_id
                ORDER BY h.month_date ASC
                """
            )
        else:
            query = text(
                """
                SELECT
                    m.month_date,
                    m.price_index_sqm as index_value,
                    m.inventory_count,
                    mc.euribor_12m,
                    mc.ecb_deposit_rate
                FROM market_fundamentals m
                LEFT JOIN macro_context mc
                    ON m.month_date = mc.date AND mc.context_type = 'actual'
                WHERE m.source = 'market' AND m.region_id = :region_id
                ORDER BY m.month_date ASC
                """
            )
        return pd.read_sql(query, self.engine, params={"region_id": region_id})

    def load_rent_series(self, region_id: str) -> pd.DataFrame:
        query = text(
            """
            SELECT
                m.month_date,
                m.rent_index_sqm as index_value,
                m.inventory_count,
                mc.euribor_12m,
                mc.ecb_deposit_rate
            FROM market_fundamentals m
            LEFT JOIN macro_context mc
                ON m.month_date = mc.date AND mc.context_type = 'actual'
            WHERE m.source = 'market' AND m.region_id = :region_id
            ORDER BY m.month_date ASC
            """
        )
        return pd.read_sql(query, self.engine, params={"region_id": region_id})

    def fetch_ine_benchmark(self, region_id: str, period: str) -> Optional[float]:
        """Fetch official INE IPV benchmark from official_metrics table."""
        if not self.has_table("official_metrics"):
            return None

        def period_variants(value: str) -> List[str]:
            text_val = str(value).strip()
            if not text_val:
                return []
            variants = {text_val}
            if "-Q" in text_val:
                variants.add(text_val.replace("-Q", "Q"))
            elif "Q" in text_val:
                variants.add(text_val.replace("Q", "-Q"))
            return list(variants)

        query = text(
            """
            SELECT value FROM official_metrics
            WHERE provider_id = 'ine_ipv'
              AND period = :period
              AND LOWER(region_id) = :region_id
              AND housing_type = 'general'
              AND metric = 'index'
            LIMIT 1
            """
        )
        query_national = text(
            """
            SELECT value FROM official_metrics
            WHERE provider_id = 'ine_ipv'
              AND period = :period
              AND region_id LIKE '%Nacional%'
              AND housing_type = 'general'
              AND metric = 'index'
            LIMIT 1
            """
        )
        region_key = region_id.lower().strip()
        with self.engine.connect() as conn:
            for candidate in period_variants(period):
                row = conn.execute(query, {"period": candidate, "region_id": region_key}).fetchone()
                if row:
                    return float(row[0])
            for candidate in period_variants(period):
                row = conn.execute(query_national, {"period": candidate}).fetchone()
                if row:
                    return float(row[0])
        return None

    def load_tft_training_data(self) -> pd.DataFrame:
        """Load training data for TFT model (hedonic + market + macro joined)."""
        query = text(
            """
            SELECT
                LOWER(h.region_id) as region_id,
                h.month_date,
                h.hedonic_index_sqm,
                m.inventory_count,
                mc.euribor_12m,
                COALESCE(mc.inflation, 2.5) as inflation
            FROM market_fundamentals h
            LEFT JOIN market_fundamentals m
                ON h.region_id = m.region_id AND h.month_date = m.month_date AND m.source = 'market'
            LEFT JOIN macro_context mc
                ON h.month_date = mc.date AND mc.context_type = 'actual'
            WHERE h.source = 'hedonic'
            ORDER BY h.region_id, h.month_date
            """
        )
        return pd.read_sql(query, self.engine)

    def load_tft_official_data(self) -> pd.DataFrame:
        """Load official metrics data for TFT training."""
        if not self.has_table("official_metrics"):
            return pd.DataFrame()
        query = text(
            """
            SELECT
                LOWER(om.region_id) as region_id,
                om.period_date as month_date,
                om.value as hedonic_index_sqm,
                NULL as inventory_count,
                mc.euribor_12m,
                COALESCE(mc.inflation, 2.5) as inflation
            FROM official_metrics om
            LEFT JOIN macro_context mc
                ON om.period_date = mc.date AND mc.context_type = 'actual'
            WHERE om.provider_id = 'ine_ipv'
              AND om.metric = 'index'
              AND om.housing_type = 'general'
              AND om.period_date IS NOT NULL
              AND om.region_id IS NOT NULL
            ORDER BY region_id, month_date
            """
        )
        return pd.read_sql(query, self.engine)
