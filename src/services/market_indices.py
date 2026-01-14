import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import structlog

logger = structlog.get_logger(__name__)

class MarketIndexService:
    """
    Data Engineering Service.
    Aggregates raw listings into monthly Time Series Indices.
    """
    def __init__(self, db_path: str = "data/listings.db"):
        self.db_path = db_path

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

    def recompute_indices(self, region_type="city"):
        """
        Full batch job: Recomputes ALL monthly indices from raw listings.
        """
        conn = sqlite3.connect(self.db_path, timeout=60.0)

        # Schema compatibility: older test DBs may not include listing_type.
        try:
            cols = [row[1] for row in conn.execute("PRAGMA table_info(listings)").fetchall()]
            has_listing_type = "listing_type" in cols
        except Exception:
            has_listing_type = False

        # Load all valid listings
        query = """
            SELECT id, city, price, surface_area_sqm, listed_at, updated_at, status
            {maybe_listing_type}
            FROM listings
            WHERE surface_area_sqm > 10 AND price > 1000
        """.format(maybe_listing_type=", listing_type" if has_listing_type else "")
        try:
            df = pd.read_sql(query, conn)
            # Use 'mixed' format to handle ISO and other string formats robustly
            df['listed_at'] = pd.to_datetime(df['listed_at'], format='mixed', errors='coerce')
            df['updated_at'] = pd.to_datetime(df['updated_at'], format='mixed', errors='coerce')
            df['price_sqm'] = df['price'] / df['surface_area_sqm']

            if has_listing_type:
                df['listing_type'] = (
                    df['listing_type']
                    .fillna("sale")
                    .astype(str)
                    .str.lower()
                    .str.strip()
                )
                df.loc[~df['listing_type'].isin(["sale", "rent"]), 'listing_type'] = "sale"
            else:
                df['listing_type'] = "sale"

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
            regions = df["region_id"].dropna().unique()
            
            # Time Range (e.g. last 24 months)
            min_date = df['listed_at'].min()
            if pd.isna(min_date): min_date = datetime.now() - timedelta(days=30)
            now = datetime.now()
            
            buckets = self._get_monthly_buckets(min_date, now)
            
            records = []
            
            for region in regions:
                if not region:
                    continue
                
                # Filter for region
                df_reg = df[df["region_id"] == region]
                
                for month_start in buckets:
                    month_end = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                    
                    # Active in this month?
                    # Created before end of month AND (Still active OR Updated after start of month)
                    # This is a heuristic reconstruction of history
                    active_mask = (df_reg['listed_at'] <= month_end) & (df_reg['updated_at'] >= month_start)
                    month_df = df_reg[active_mask]
                    
                    if month_df.empty:
                        # No data for this month
                        continue

                    # Split by listing type
                    sale_df = month_df[month_df['listing_type'] == "sale"]
                    rent_df = month_df[month_df['listing_type'] == "rent"]
                        
                    # Calculate Metrics
                    if not sale_df.empty:
                        price_index = sale_df['price_sqm'].median()
                        inventory = len(sale_df)
                    else:
                        # Backward-compatible fallback (older DBs without listing_type)
                        price_index = month_df['price_sqm'].median()
                        inventory = len(month_df)

                    rent_index = rent_df['price_sqm'].median() if not rent_df.empty else None
                    
                    # Listings listed THIS month
                    new_mask = (
                        (df_reg['listed_at'] >= month_start)
                        & (df_reg['listed_at'] <= month_end)
                        & (df_reg['listing_type'] == "sale")
                    )
                    new_count = len(df_reg[new_mask]) if has_listing_type else len(df_reg[(df_reg['listed_at'] >= month_start) & (df_reg['listed_at'] <= month_end)])
                    
                    # Absorption (proxy)
                    # Simple turnover rate: new / total
                    absorption = new_count / inventory if inventory > 0 else 0
                    
                    # Volatility (Std of price_sqm)
                    volatility = (sale_df['price_sqm'].std() if not sale_df.empty else month_df['price_sqm'].std())
                    if pd.isna(volatility): volatility = 0
                    
                    # DOM (approximate)
                    dom_days = (month_end - (sale_df['listed_at'] if not sale_df.empty else month_df['listed_at'])).dt.days
                    median_dom = dom_days.median()
                    
                    record = (
                        f"{region}|{month_start.strftime('%Y-%m')}",
                        region,
                        month_start.strftime("%Y-%m-%d"),
                        float(price_index),
                        float(rent_index) if rent_index is not None and not pd.isna(rent_index) else None,
                        int(inventory),
                        int(new_count),
                        0, # Sold count placeholder (need explicit sold status history)
                        float(absorption),
                        int(median_dom) if not pd.isna(median_dom) else 0,
                        0.0, # Price cut placeholder
                        float(volatility)
                    )
                    records.append(record)
            
            # Batch Upsert
            cursor = conn.cursor()
            cursor.executemany("""
                INSERT OR REPLACE INTO market_indices (
                    id, region_id, month_date, price_index_sqm, rent_index_sqm,
                    inventory_count, new_listings_count, sold_count, absorption_rate,
                    median_dom, price_cut_share, volatility_3m
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, records)
            conn.commit()
            
            logger.info("indices_recomputed", records_count=len(records))
            
        except Exception as e:
            logger.error("index_computation_failed", error=str(e))
        finally:
            conn.close()
