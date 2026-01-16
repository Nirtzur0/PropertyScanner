from typing import Optional

import pandas as pd
from sqlalchemy import text

from src.repositories.base import RepositoryBase


class ERIMetricsRepository(RepositoryBase):
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
