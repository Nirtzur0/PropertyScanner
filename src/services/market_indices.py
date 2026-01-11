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
        
        # Load all valid listings
        query = """
            SELECT id, city, price, surface_area_sqm, listed_at, updated_at, status 
            FROM listings 
            WHERE surface_area_sqm > 10 AND price > 1000
        """
        try:
            df = pd.read_sql(query, conn)
            # Use 'mixed' format to handle ISO and other string formats robustly
            df['listed_at'] = pd.to_datetime(df['listed_at'], format='mixed', errors='coerce')
            df['updated_at'] = pd.to_datetime(df['updated_at'], format='mixed', errors='coerce')
            df['price_sqm'] = df['price'] / df['surface_area_sqm']
            
            # Define Regions
            regions = df[region_type].unique()
            
            # Time Range (e.g. last 24 months)
            min_date = df['listed_at'].min()
            if pd.isna(min_date): min_date = datetime.now() - timedelta(days=30)
            now = datetime.now()
            
            buckets = self._get_monthly_buckets(min_date, now)
            
            records = []
            
            for region in regions:
                if not region: continue
                
                # Filter for region
                df_reg = df[df[region_type] == region]
                
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
                        
                    # Calculate Metrics
                    price_index = month_df['price_sqm'].median()
                    inventory = len(month_df)
                    
                    # Listings listed THIS month
                    new_mask = (df_reg['listed_at'] >= month_start) & (df_reg['listed_at'] <= month_end)
                    new_count = len(df_reg[new_mask])
                    
                    # Absorption (proxy)
                    # Simple turnover rate: new / total
                    absorption = new_count / inventory if inventory > 0 else 0
                    
                    # Volatility (Std of price_sqm)
                    volatility = month_df['price_sqm'].std()
                    if pd.isna(volatility): volatility = 0
                    
                    # DOM (approximate)
                    dom_days = (month_end - month_df['listed_at']).dt.days
                    median_dom = dom_days.median()
                    
                    record = (
                        f"{region}|{month_start.strftime('%Y-%m')}",
                        region,
                        month_start.strftime("%Y-%m-%d"),
                        float(price_index),
                        0.0, # Rent index placeholder
                        int(inventory),
                        int(new_count),
                        0, # Sold count placeholder (need explicit sold status history)
                        float(absorption),
                        int(median_dom),
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
