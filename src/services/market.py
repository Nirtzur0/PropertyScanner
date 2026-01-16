import sqlite3
import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
import structlog
from src.core.domain.schema import MarketProfile, CanonicalListing
from src.services.eri_signals import ERISignalsService

logger = structlog.get_logger(__name__)

class MarketService:
    """
    Consolidated Market Service.
    Handles:
    1. Analysis of individual listings (Momentum, Liquidity, etc.)
    2. Computation of aggregated market indices (Time Series)
    """
    def __init__(self, db_path: str = "data/listings.db"):
        self.db_path = db_path
        self.eri = ERISignalsService(db_path=db_path)

    # =========================================================================
    # PART 1: Listing Analysis (formerly MarketAnalyticsService)
    # =========================================================================

    def _get_listings_df(self, city: str = None) -> pd.DataFrame:
        """Load listings into a DataFrame for vectorized analysis"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        query = "SELECT * FROM listings"
        if city:
            query += f" WHERE city = '{city}'"

        try:
            df = pd.read_sql(query, conn)
            # Ensure types
            df['price'] = pd.to_numeric(df['price'], errors='coerce')
            df['surface_area_sqm'] = pd.to_numeric(df['surface_area_sqm'], errors='coerce')
            df['listed_at'] = pd.to_datetime(df['listed_at'])

            # Derived
            df['price_sqm'] = df['price'] / df['surface_area_sqm']

            return df
        except Exception as e:
            logger.error("dataframe_load_failed", error=str(e))
            return pd.DataFrame()
        finally:
            conn.close()

    def calculate_momentum(self, df_zone: pd.DataFrame) -> Tuple[float, float]:
        """
        Signal A: Temporal Trend.
        Returns (Annual_Growth_Rate, Confidence)
        Using simple linear regression on price_sqm ~ time.
        """
        if len(df_zone) < 5:
            return 0.0, 0.0

        df_clean = df_zone.dropna(subset=['price_sqm', 'listed_at']).sort_values('listed_at')
        if df_clean.empty:
             return 0.0, 0.0

        # Convert dates to ordinal for regression
        df_clean['date_ord'] = df_clean['listed_at'].map(datetime.toordinal)

        X = df_clean['date_ord'].values.reshape(-1, 1)
        y = df_clean['price_sqm'].values

        if len(y) < 5 or np.std(y) < 1e-6 or np.std(X) < 1e-6:
            return 0.0, 0.0

        # Simple Linear Regression
        # Slope = change in price per day
        try:
            # Center X to avoid large numbers
            X_mean = X.mean()
            slope, intercept = np.polyfit((X - X_mean).flatten(), y, 1)

            # Annualize
            annual_change_sqm = slope * 365
            current_avg = y.mean()
            growth_rate = annual_change_sqm / current_avg if current_avg > 0 else 0

            # Confidence based on R-squared or just sample size for now
            confidence = min(len(df_clean) / 50.0, 0.9) # Max 0.9 confidence if > 50 samples

            return growth_rate, confidence
        except:
            return 0.0, 0.0

    def calculate_liquidity(self, df_zone: pd.DataFrame) -> float:
        """
        Signal C: Liquidity Score (0.0 - 1.0)
        Based on Days on Market (proxy: time since listed for active, or actual DOM if we tracked sold).
        For now, we use 'age of active listings' as inverse proxy.
        Older active listings = Lower Liquidity.
        """
        if df_zone.empty:
            return 0.5

        now = datetime.now()
        df_zone['age_days'] = (now - df_zone['listed_at']).dt.days
        median_age = df_zone['age_days'].median()

        # Heuristic:
        # < 30 days med age = High Liquidity (1.0)
        # > 180 days med age = Low Liquidity (0.0)
        if pd.isna(median_age): return 0.5

        score = max(0.0, min(1.0, 1.0 - (median_age - 30) / 150.0))
        return score

    def analyze_listing(self, listing: CanonicalListing) -> MarketProfile:
        """
        Main entry point. Analyzes market for a specific listing.
        """
        # 1. Define Zone (Cluster)
        # For now, simple clustering by City + approx Latitude (primitive tiling)
        # In prod, use H3 or Geohash
        df = self._get_listings_df(city=listing.location.city if listing.location else None)

        if df.empty:
            return MarketProfile(
                zone_id="unknown", momentum_score=0, liquidity_score=0, catchup_potential=0, avg_price_sqm=0, inventory_trend="stable"
            )

        # Filter by proximity (simulated by lat/lon box if available, else city wide)
        # Using a simplistic "zone" for now
        zone_df = df # entire city for now to ensure data volume

        # 2. Calculate Signals
        growth_rate, confidence = self.calculate_momentum(zone_df)
        liquidity = self.calculate_liquidity(zone_df)

        eri_signals = {}
        if listing.location and listing.location.city:
            eri_signals = self.eri.get_signals(
                listing.location.city.lower(),
                listing.updated_at if listing.updated_at else datetime.now()
            )

        if eri_signals:
            txn_z = eri_signals.get("txn_volume_z", 0.0)
            eri_liquidity = 1.0 / (1.0 + np.exp(-txn_z))
            liquidity = 0.5 * liquidity + 0.5 * eri_liquidity

            registral_change = eri_signals.get("registral_price_sqm_change")
            if registral_change is not None:
                growth_rate = 0.6 * registral_change + 0.4 * growth_rate

        # 3. Calculate Ripple (Simplistic: compare to city avg)
        # If this listing is in a cheaper zone but city is booming
        avg_price_sqm = zone_df['price_sqm'].mean()
        catchup = 0.0
        if listing.surface_area_sqm and listing.price:
            l_price_sqm = listing.price / listing.surface_area_sqm
            if l_price_sqm < avg_price_sqm * 0.8 and growth_rate > 0.02:
                # Cheaper than avg in a growing market -> High Catchup
                catchup = 0.8

        # 4. Projections (Handled by MarketDynamicsAgent via ForecastingService)
        projections = []

        return MarketProfile(
            zone_id=listing.location.city if listing.location else "unknown",
            momentum_score=growth_rate,
            liquidity_score=liquidity,
            catchup_potential=catchup,
            avg_price_sqm=float(avg_price_sqm) if not pd.isna(avg_price_sqm) else 0.0,
            median_dom=int(zone_df['age_days'].median()) if 'age_days' in zone_df else 0,
            inventory_trend="stable", # placeholder
            projections=projections
        )

    # =========================================================================
    # PART 2: Index Computation (formerly MarketIndexService)
    # =========================================================================

    def get_market_index_value(self, region_id: str, month_key: str, column: str) -> float:
        """
        Get value from market_indices table.
        """
        allowed = {"price_index_sqm", "rent_index_sqm"}
        if column not in allowed:
            raise ValueError("unsupported_market_index_column")

        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT {column}
                FROM market_indices
                WHERE region_id = ? AND month_date LIKE ?
                ORDER BY month_date DESC
                LIMIT 1
            """, (region_id, f"{month_key}%"))
            row = cursor.fetchone()

            if not row or row[0] is None:
                raise ValueError("missing_market_index")

            value = float(row[0])
            if value <= 0:
                raise ValueError("invalid_market_index")

            return value
        finally:
            conn.close()

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
