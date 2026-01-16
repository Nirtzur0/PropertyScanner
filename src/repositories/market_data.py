from typing import Literal

import pandas as pd
from sqlalchemy import text

from src.repositories.base import RepositoryBase


class MarketDataRepository(RepositoryBase):
    def load_price_series(self, region_id: str, index_source: Literal["market", "hedonic"] = "market") -> pd.DataFrame:
        if index_source == "hedonic":
            query = text(
                """
                SELECT
                    hi.month_date,
                    hi.hedonic_index_sqm as index_value,
                    mi.inventory_count,
                    mac.euribor_12m,
                    mac.ecb_deposit_rate
                FROM hedonic_indices hi
                LEFT JOIN market_indices mi
                    ON hi.region_id = mi.region_id AND hi.month_date = mi.month_date
                LEFT JOIN macro_indicators mac
                    ON hi.month_date = mac.date
                WHERE hi.region_id = :region_id
                ORDER BY hi.month_date ASC
                """
            )
        else:
            query = text(
                """
                SELECT
                    mi.month_date,
                    mi.price_index_sqm as index_value,
                    mi.inventory_count,
                    mac.euribor_12m,
                    mac.ecb_deposit_rate
                FROM market_indices mi
                LEFT JOIN macro_indicators mac
                    ON mi.month_date = mac.date
                WHERE mi.region_id = :region_id
                ORDER BY mi.month_date ASC
                """
            )
        return pd.read_sql(query, self.engine, params={"region_id": region_id})

    def load_rent_series(self, region_id: str) -> pd.DataFrame:
        query = text(
            """
            SELECT
                mi.month_date,
                mi.rent_index_sqm as index_value,
                mi.inventory_count,
                mac.euribor_12m,
                mac.ecb_deposit_rate
            FROM market_indices mi
            LEFT JOIN macro_indicators mac
                ON mi.month_date = mac.date
            WHERE mi.region_id = :region_id
            ORDER BY mi.month_date ASC
            """
        )
        return pd.read_sql(query, self.engine, params={"region_id": region_id})
