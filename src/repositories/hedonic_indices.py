from typing import List, Optional, Tuple

import pandas as pd
from sqlalchemy import text

from src.repositories.base import RepositoryBase


class HedonicIndicesRepository(RepositoryBase):
    def fetch_index(self, region_id: str, month_prefix: str) -> Optional[Tuple[float, float, int]]:
        query = text(
            """
            SELECT hedonic_index_sqm, r_squared, n_observations
            FROM hedonic_indices
            WHERE region_id = :region_id AND month_date LIKE :month_prefix
            ORDER BY month_date DESC
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(query, {"region_id": region_id, "month_prefix": f"{month_prefix}%"}).fetchone()
        if not row:
            return None
        return float(row[0]), float(row[1] or 0.0), int(row[2] or 0)

    def fetch_ine_benchmark(self, region_id: str, period: str) -> Optional[float]:
        query = text(
            """
            SELECT value FROM ine_ipv
            WHERE period = :period AND region_id = :region_id
              AND housing_type = 'general' AND metric = 'index'
            LIMIT 1
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(query, {"period": period, "region_id": region_id}).fetchone()
            if row:
                return float(row[0])
            row = conn.execute(
                text(
                    """
                    SELECT value FROM ine_ipv
                    WHERE period = :period AND region_id LIKE '%Nacional%'
                      AND housing_type = 'general' AND metric = 'index'
                    LIMIT 1
                    """
                ),
                {"period": period},
            ).fetchone()
        if row:
            return float(row[0])
        return None

    def fetch_index_series(self, region_id: str, start_month: str, end_month: str) -> pd.DataFrame:
        query = text(
            """
            SELECT month_date, hedonic_index_sqm
            FROM hedonic_indices
            WHERE region_id = :region_id
              AND month_date >= :start_month
              AND month_date <= :end_month
            ORDER BY month_date ASC
            """
        )
        return pd.read_sql(
            query,
            self.engine,
            params={"region_id": region_id, "start_month": start_month, "end_month": end_month},
        )

    def get_last_updated_at(self) -> Optional[pd.Timestamp]:
        query = text("SELECT MAX(updated_at) as last_updated FROM hedonic_indices")
        with self.engine.connect() as conn:
            row = conn.execute(query).fetchone()
        last_updated = pd.to_datetime(row[0], format="mixed", errors="coerce") if row and row[0] else None
        if pd.isna(last_updated):
            return None
        return last_updated

    def upsert_indices(self, records: List[Tuple]) -> None:
        has_nh = self.has_column("hedonic_indices", "n_neighborhoods")
        if has_nh:
            query = text(
                """
                INSERT OR REPLACE INTO hedonic_indices
                (id, region_id, month_date, hedonic_index_sqm, raw_median_sqm,
                 r_squared, n_observations, n_neighborhoods, coefficients, updated_at)
                VALUES (:id, :region_id, :month_date, :hedonic_index_sqm, :raw_median_sqm,
                        :r_squared, :n_observations, :n_neighborhoods, :coefficients, :updated_at)
                """
            )
        else:
            query = text(
                """
                INSERT OR REPLACE INTO hedonic_indices
                (id, region_id, month_date, hedonic_index_sqm, raw_median_sqm,
                 r_squared, n_observations, coefficients, updated_at)
                VALUES (:id, :region_id, :month_date, :hedonic_index_sqm, :raw_median_sqm,
                        :r_squared, :n_observations, :coefficients, :updated_at)
                """
            )
        payloads = []
        for record in records:
            if has_nh:
                (
                    record_id,
                    region_id,
                    month_date,
                    hedonic_index,
                    raw_median,
                    r_squared,
                    n_obs,
                    n_neighborhoods,
                    coefficients,
                    updated_at,
                ) = record
                payloads.append(
                    {
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
                    }
                )
            else:
                (
                    record_id,
                    region_id,
                    month_date,
                    hedonic_index,
                    raw_median,
                    r_squared,
                    n_obs,
                    coefficients,
                    updated_at,
                ) = record
                payloads.append(
                    {
                        "id": record_id,
                        "region_id": region_id,
                        "month_date": month_date,
                        "hedonic_index_sqm": hedonic_index,
                        "raw_median_sqm": raw_median,
                        "r_squared": r_squared,
                        "n_observations": n_obs,
                        "coefficients": coefficients,
                        "updated_at": updated_at,
                    }
                )
        if not payloads:
            return
        with self.engine.begin() as conn:
            conn.execute(query, payloads)
