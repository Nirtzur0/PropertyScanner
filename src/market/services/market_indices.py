import pandas as pd
try:
    import polars as pl
except ImportError:  # pragma: no cover - optional dependency
    pl = None
from datetime import datetime, timedelta
from typing import List, Optional
import structlog
from src.platform.config import DEFAULT_DB_PATH
from src.platform.db.base import resolve_db_url
from src.listings.repositories.listings import ListingsRepository
from src.market.repositories.market_fundamentals import MarketFundamentalsRepository
from src.platform.settings import AppConfig
from src.platform.utils.config import load_app_config_safe
from src.platform.utils.time import utcnow

logger = structlog.get_logger(__name__)


class MarketIndexService:
    """
    Data Engineering Service.
    Aggregates raw listings into monthly Time Series Indices.
    """

    def __init__(
        self,
        db_path: str = str(DEFAULT_DB_PATH),
        db_url: Optional[str] = None,
        app_config: Optional[AppConfig] = None,
    ):
        self.db_url = resolve_db_url(db_url=db_url, db_path=db_path)
        self.listings_repo = ListingsRepository(db_url=self.db_url)
        self.market_repo = MarketFundamentalsRepository(db_url=self.db_url)
        self.app_config = app_config or load_app_config_safe()
        backend = self.app_config.dataframe.backend if self.app_config else "pandas"
        self._use_polars = backend == "polars"

    def _get_monthly_buckets(self, start_date: datetime, end_date: datetime) -> List[datetime]:
        """Generate first-of-month dates between start and end"""
        buckets = []
        curr = start_date.replace(day=1)
        while curr <= end_date:
            buckets.append(curr)
            # Add month
            if curr.month == 12:
                curr = curr.replace(year=curr.year + 1, month=1)
            else:
                curr = curr.replace(month=curr.month + 1)
        return buckets

    def recompute_indices(self, region_type: str = "city") -> None:
        """
        Full batch job: Recomputes ALL monthly indices from raw listings.
        """
        df, has_listing_type = self.listings_repo.load_listings_for_indices()
        if self._use_polars and pl is None:
            logger.warning("polars_unavailable_falling_back", backend="polars")
            self._use_polars = False
        try:
            # Use 'mixed' format to handle ISO and other string formats robustly
            df["listed_at"] = pd.to_datetime(df["listed_at"], format="mixed", errors="coerce")
            df["updated_at"] = pd.to_datetime(df["updated_at"], format="mixed", errors="coerce")
            if "sold_at" in df.columns:
                df["sold_at"] = pd.to_datetime(df["sold_at"], format="mixed", errors="coerce")
            sold_price = df.get("sold_price")
            if sold_price is not None:
                df["sold_price"] = pd.to_numeric(df["sold_price"], errors="coerce")
            df["price"] = pd.to_numeric(df["price"], errors="coerce")
            effective_price = df["price"]
            if "sold_price" in df.columns:
                sold_mask = df.get("status").astype(str).str.lower() == "sold"
                sold_override = sold_mask & df["sold_price"].notna() & (df["sold_price"] > 0)
                effective_price = effective_price.where(~sold_override, df["sold_price"])
            df["price_sqm"] = effective_price / df["surface_area_sqm"]

            if has_listing_type:
                df["listing_type"] = (
                    df["listing_type"]
                    .fillna("sale")
                    .astype(str)
                    .str.lower()
                    .str.strip()
                )
                df.loc[~df["listing_type"].isin(["sale", "rent"]), "listing_type"] = "sale"
            else:
                df["listing_type"] = "sale"

            # Normalize region IDs for stable joins downstream (valuation uses lowercase city IDs).
            region_series = df.get(region_type)
            if region_series is None:
                df["region_id"] = None
            else:
                region_norm = (
                    region_series.astype(str)
                    .str.strip()
                    .str.lower()
                )
                region_norm = region_norm.where(region_series.notna(), None)
                region_norm = region_norm.where(region_norm != "", None)
                df["region_id"] = region_norm

            # Define Regions
            regions = list(df["region_id"].dropna().unique())
            regions.append("all")

            # Time Range (e.g. last 24 months)
            min_date = df["listed_at"].min()
            if pd.isna(min_date):
                min_date = utcnow() - timedelta(days=30)
            now = utcnow()

            buckets = self._get_monthly_buckets(min_date, now)

            if self._use_polars:
                records = self._recompute_indices_polars(
                    df=df,
                    regions=regions,
                    buckets=buckets,
                    has_listing_type=has_listing_type,
                )
            else:
                records = self._recompute_indices_pandas(
                    df=df,
                    regions=regions,
                    buckets=buckets,
                    has_listing_type=has_listing_type,
                )

            # Batch Upsert
            self.market_repo.upsert_market_records(records)

            logger.info("indices_recomputed", records_count=len(records))

        except Exception as e:
            logger.error("index_computation_failed", error=str(e))

    def _recompute_indices_pandas(
        self,
        *,
        df: pd.DataFrame,
        regions: List[str],
        buckets: List[datetime],
        has_listing_type: bool,
    ) -> List[tuple]:
        records = []
        updated_at = utcnow().isoformat()

        for region in regions:
            if not region:
                continue

            if region == "all":
                df_reg = df
            else:
                df_reg = df[df["region_id"] == region]

            for month_start in buckets:
                month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

                active_mask = (df_reg["listed_at"] <= month_end) & (df_reg["updated_at"] >= month_start)
                month_df = df_reg[active_mask]

                if month_df.empty:
                    continue

                sale_df = month_df[month_df["listing_type"] == "sale"]
                rent_df = month_df[month_df["listing_type"] == "rent"]

                if not sale_df.empty:
                    price_index = sale_df["price_sqm"].median()
                    inventory = len(sale_df)
                else:
                    price_index = month_df["price_sqm"].median()
                    inventory = len(month_df)

                rent_index = rent_df["price_sqm"].median() if not rent_df.empty else None

                new_mask = (
                    (df_reg["listed_at"] >= month_start)
                    & (df_reg["listed_at"] <= month_end)
                    & (df_reg["listing_type"] == "sale")
                )
                new_count = len(df_reg[new_mask]) if has_listing_type else len(
                    df_reg[
                        (df_reg["listed_at"] >= month_start) & (df_reg["listed_at"] <= month_end)
                    ]
                )

                sold_count = 0
                if "sold_at" in df_reg.columns:
                    sold_at = df_reg["sold_at"]
                    sold_count = int(((sold_at >= month_start) & (sold_at <= month_end)).sum())

                absorption = new_count / inventory if inventory > 0 else 0

                volatility = sale_df["price_sqm"].std() if not sale_df.empty else month_df["price_sqm"].std()
                if pd.isna(volatility):
                    volatility = 0

                dom_days = (month_end - (sale_df["listed_at"] if not sale_df.empty else month_df["listed_at"])).dt.days
                median_dom = dom_days.median()

                record = (
                    f"{region}|{month_start.strftime('%Y-%m')}",
                    region,
                    month_start.strftime("%Y-%m-%d"),
                    float(price_index),
                    float(rent_index) if rent_index is not None and not pd.isna(rent_index) else None,
                    int(inventory),
                    int(new_count),
                    int(sold_count),
                    float(absorption),
                    int(median_dom) if not pd.isna(median_dom) else 0,
                    0.0,
                    float(volatility),
                    updated_at,
                )
                records.append(record)
        return records

    def _recompute_indices_polars(
        self,
        *,
        df: pd.DataFrame,
        regions: List[str],
        buckets: List[datetime],
        has_listing_type: bool,
    ) -> List[tuple]:
        records: List[tuple] = []
        updated_at = utcnow().isoformat()
        df_pl = pl.from_pandas(df)

        for region in regions:
            if not region:
                continue

            if region == "all":
                df_reg = df_pl
            else:
                df_reg = df_pl.filter(pl.col("region_id") == region)

            if df_reg.height == 0:
                continue

            for month_start in buckets:
                month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                month_df = df_reg.filter(
                    (pl.col("listed_at") <= pl.lit(month_end))
                    & (pl.col("updated_at") >= pl.lit(month_start))
                )
                if month_df.height == 0:
                    continue

                sale_df = month_df.filter(pl.col("listing_type") == "sale")
                rent_df = month_df.filter(pl.col("listing_type") == "rent")

                if sale_df.height > 0:
                    price_index = sale_df.select(pl.col("price_sqm").median()).item()
                    inventory = sale_df.height
                else:
                    price_index = month_df.select(pl.col("price_sqm").median()).item()
                    inventory = month_df.height

                rent_index = (
                    rent_df.select(pl.col("price_sqm").median()).item()
                    if rent_df.height > 0
                    else None
                )

                new_count = 0
                if has_listing_type:
                    new_count = (
                        df_reg.filter(
                            (pl.col("listed_at") >= pl.lit(month_start))
                            & (pl.col("listed_at") <= pl.lit(month_end))
                            & (pl.col("listing_type") == "sale")
                        ).height
                    )
                else:
                    new_count = (
                        df_reg.filter(
                            (pl.col("listed_at") >= pl.lit(month_start))
                            & (pl.col("listed_at") <= pl.lit(month_end))
                        ).height
                    )

                sold_count = 0
                if "sold_at" in df_reg.columns:
                    sold_count = (
                        df_reg.filter(
                            (pl.col("sold_at") >= pl.lit(month_start))
                            & (pl.col("sold_at") <= pl.lit(month_end))
                        ).height
                    )

                absorption = new_count / inventory if inventory > 0 else 0.0

                volatility = (
                    sale_df.select(pl.col("price_sqm").std()).item()
                    if sale_df.height > 0
                    else month_df.select(pl.col("price_sqm").std()).item()
                )
                if volatility is None or (isinstance(volatility, float) and pd.isna(volatility)):
                    volatility = 0.0

                dom_source = sale_df if sale_df.height > 0 else month_df
                median_dom = dom_source.select(
                    (pl.lit(month_end) - pl.col("listed_at")).dt.total_days().median()
                ).item()

                record = (
                    f"{region}|{month_start.strftime('%Y-%m')}",
                    region,
                    month_start.strftime("%Y-%m-%d"),
                    float(price_index),
                    float(rent_index) if rent_index is not None else None,
                    int(inventory),
                    int(new_count),
                    int(sold_count),
                    float(absorption),
                    int(median_dom) if median_dom is not None else 0,
                    0.0,
                    float(volatility),
                    updated_at,
                )
                records.append(record)
        return records
