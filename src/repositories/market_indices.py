from typing import List, Optional, Tuple

import pandas as pd
from sqlalchemy import text

from src.repositories.base import RepositoryBase


class MarketIndicesRepository(RepositoryBase):
    def fetch_index_value(self, region_id: str, month_date: str, index_type: str = "price") -> Optional[float]:
        index_type = str(index_type).strip().lower()
        if index_type not in {"price", "rent"}:
            raise ValueError("invalid_index_type")

        month_key = str(month_date).strip()
        if len(month_key) > 7:
            month_key = month_key[:7]

        column = "price_index_sqm" if index_type == "price" else "rent_index_sqm"
        query = text(
            f"""
            SELECT {column}
            FROM market_indices
            WHERE region_id = :region_id
              AND substr(month_date, 1, 7) = :month_key
            ORDER BY month_date DESC
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(query, {"region_id": region_id, "month_key": month_key}).fetchone()
        if not row:
            return None
        value = row[0]
        return float(value) if value is not None else None
    def fetch_latest_snapshot(self, region_id: str) -> Optional[Tuple[float, int, int]]:
        query = text(
            """
            SELECT price_index_sqm, inventory_count, new_listings_count
            FROM market_indices
            WHERE region_id = :region_id
            ORDER BY month_date DESC
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(query, {"region_id": region_id}).fetchone()
        if not row:
            return None
        return row[0], row[1], row[2]

    def fetch_series(self, region_id: str) -> pd.DataFrame:
        query = text(
            """
            SELECT month_date, price_index_sqm, rent_index_sqm, inventory_count, new_listings_count
            FROM market_indices
            WHERE region_id = :region_id
            ORDER BY month_date ASC
            """
        )
        return pd.read_sql(query, self.engine, params={"region_id": region_id})

    def get_last_updated_at(self) -> Optional[pd.Timestamp]:
        query = text("SELECT MAX(updated_at) as last_updated FROM market_indices")
        with self.engine.connect() as conn:
            row = conn.execute(query).fetchone()
        last_updated = pd.to_datetime(row[0], format="mixed", errors="coerce") if row and row[0] else None
        if pd.isna(last_updated) or last_updated is None:
            fallback = text("SELECT MAX(month_date) as last_month FROM market_indices")
            with self.engine.connect() as conn:
                row = conn.execute(fallback).fetchone()
            last_month = pd.to_datetime(row[0], format="mixed", errors="coerce") if row and row[0] else None
            if pd.isna(last_month):
                return None
            return last_month
        return last_updated

    def upsert_records(self, records: List[Tuple]) -> None:
        if not records:
            return
        has_updated = self.has_column("market_indices", "updated_at")
        if has_updated:
            query = text(
                """
                INSERT OR REPLACE INTO market_indices (
                    id, region_id, month_date, price_index_sqm, rent_index_sqm,
                    inventory_count, new_listings_count, sold_count, absorption_rate,
                    median_dom, price_cut_share, volatility_3m, updated_at
                ) VALUES (
                    :id, :region_id, :month_date, :price_index_sqm, :rent_index_sqm,
                    :inventory_count, :new_listings_count, :sold_count, :absorption_rate,
                    :median_dom, :price_cut_share, :volatility_3m, :updated_at
                )
                """
            )
        else:
            query = text(
                """
                INSERT OR REPLACE INTO market_indices (
                    id, region_id, month_date, price_index_sqm, rent_index_sqm,
                    inventory_count, new_listings_count, sold_count, absorption_rate,
                    median_dom, price_cut_share, volatility_3m
                ) VALUES (
                    :id, :region_id, :month_date, :price_index_sqm, :rent_index_sqm,
                    :inventory_count, :new_listings_count, :sold_count, :absorption_rate,
                    :median_dom, :price_cut_share, :volatility_3m
                )
                """
            )
        payloads = []
        for record in records:
            if has_updated:
                (
                    record_id,
                    region_id,
                    month_date,
                    price_index,
                    rent_index,
                    inventory,
                    new_count,
                    sold_count,
                    absorption,
                    median_dom,
                    price_cut_share,
                    volatility,
                    updated_at,
                ) = record
                payloads.append(
                    {
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
                    }
                )
            else:
                (
                    record_id,
                    region_id,
                    month_date,
                    price_index,
                    rent_index,
                    inventory,
                    new_count,
                    sold_count,
                    absorption,
                    median_dom,
                    price_cut_share,
                    volatility,
                ) = record
                payloads.append(
                    {
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
                    }
                )
        with self.engine.begin() as conn:
            conn.execute(query, payloads)
