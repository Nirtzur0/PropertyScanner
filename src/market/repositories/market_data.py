from typing import Literal

import pandas as pd
from sqlalchemy import text

from src.platform.db.base import RepositoryBase


class MarketDataRepository(RepositoryBase):
    def load_tft_training_data(self) -> pd.DataFrame:
        if not self.has_table("hedonic_indices"):
            return pd.DataFrame()

        has_market = self.has_table("market_indices")
        has_macro = self.has_table("macro_indicators")
        has_cpi = self.has_column("macro_indicators", "spain_cpi") if has_macro else False

        joins = []
        select_fields = [
            "LOWER(hi.region_id) as region_id",
            "hi.month_date",
            "hi.hedonic_index_sqm",
        ]

        if has_market:
            select_fields.append("mi.inventory_count")
            joins.append("LEFT JOIN market_indices mi ON hi.region_id = mi.region_id AND hi.month_date = mi.month_date")
        else:
            select_fields.append("NULL as inventory_count")

        if has_macro:
            select_fields.append("mac.euribor_12m")
            if has_cpi:
                select_fields.append("COALESCE(mac.spain_cpi, 2.5) as inflation")
            else:
                select_fields.append("2.5 as inflation")
            joins.append("LEFT JOIN macro_indicators mac ON hi.month_date = mac.date")
        else:
            select_fields.append("NULL as euribor_12m")
            select_fields.append("2.5 as inflation")

        query = f"""
            SELECT {", ".join(select_fields)}
            FROM hedonic_indices hi
            {" ".join(joins)}
            ORDER BY hi.region_id, hi.month_date
        """
        return pd.read_sql(text(query), self.engine)

    def load_tft_official_data(self) -> pd.DataFrame:
        if not self.has_table("official_metrics"):
            return pd.DataFrame()

        has_macro = self.has_table("macro_indicators")
        has_cpi = self.has_column("macro_indicators", "spain_cpi") if has_macro else False

        joins = []
        select_fields = [
            "LOWER(om.region_id) as region_id",
            "om.period_date as month_date",
            "om.value as hedonic_index_sqm",
            "NULL as inventory_count",
        ]

        if has_macro:
            select_fields.append("mac.euribor_12m")
            if has_cpi:
                select_fields.append("COALESCE(mac.spain_cpi, 2.5) as inflation")
            else:
                select_fields.append("2.5 as inflation")
            joins.append("LEFT JOIN macro_indicators mac ON om.period_date = mac.date")
        else:
            select_fields.append("NULL as euribor_12m")
            select_fields.append("2.5 as inflation")

        query = f"""
            SELECT {", ".join(select_fields)}
            FROM official_metrics om
            {" ".join(joins)}
            WHERE om.provider_id = 'ine_ipv'
              AND om.metric = 'index'
              AND om.housing_type = 'general'
              AND om.period_date IS NOT NULL
              AND om.region_id IS NOT NULL
            ORDER BY region_id, month_date
        """
        return pd.read_sql(text(query), self.engine)

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
