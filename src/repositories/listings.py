from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import text

from src.repositories.base import RepositoryBase


class ListingsRepository(RepositoryBase):
    def list_cities(self) -> List[str]:
        query = text("SELECT DISTINCT city FROM listings WHERE city IS NOT NULL AND city != ''")
        with self.engine.connect() as conn:
            rows = conn.execute(query).fetchall()
        cities: List[str] = []
        for row in rows:
            city = row[0]
            if not city:
                continue
            city_norm = str(city).strip().lower()
            if city_norm:
                cities.append(city_norm)
        return sorted(set(cities))

    def load_listings_df(self, city: Optional[str] = None) -> pd.DataFrame:
        query = "SELECT * FROM listings"
        params: Dict[str, str] = {}
        if city:
            query += " WHERE LOWER(city) = :city"
            params["city"] = city.strip().lower()
        return pd.read_sql(text(query), self.engine, params=params)

    def load_listings_for_hedonic(self, region_name: Optional[str] = None) -> pd.DataFrame:
        has_listing_type = self.has_column("listings", "listing_type")
        query = """
            SELECT
                id,
                price,
                surface_area_sqm,
                bedrooms,
                bathrooms,
                has_elevator,
                floor,
                geohash,
                city,
                listed_at,
                updated_at
            FROM listings
            WHERE price > 1000
              AND surface_area_sqm > 10
              AND surface_area_sqm < 500
        """
        params: Dict[str, str] = {}
        if has_listing_type:
            query += " AND listing_type = 'sale'"
        if region_name:
            query += " AND LOWER(city) = :city"
            params["city"] = region_name.strip().lower()
        return pd.read_sql(text(query), self.engine, params=params)

    def load_listings_for_indices(self) -> Tuple[pd.DataFrame, bool]:
        has_listing_type = self.has_column("listings", "listing_type")
        query = """
            SELECT id, city, price, surface_area_sqm, listed_at, updated_at, status
        """
        if has_listing_type:
            query = query.rstrip() + ", listing_type\n"
        query += """
            FROM listings
            WHERE surface_area_sqm > 10 AND price > 1000
        """
        df = pd.read_sql(text(query), self.engine)
        return df, has_listing_type

    def get_listing_snapshot(self) -> Dict[str, Optional[object]]:
        query = text(
            """
            SELECT
                COUNT(*) as listing_count,
                MAX(COALESCE(fetched_at, updated_at, listed_at)) as last_seen
            FROM listings
            """
        )
        with self.engine.connect() as conn:
            row = conn.execute(query).fetchone()
        if not row:
            return {"count": 0, "last_seen": None}
        count = int(row[0]) if row[0] is not None else 0
        last_seen = pd.to_datetime(row[1], format="mixed", errors="coerce") if row[1] else None
        if pd.isna(last_seen):
            last_seen = None
        return {"count": count, "last_seen": last_seen}

    def fix_missing_fetched_at(self, default_ts: Optional[datetime] = None) -> int:
        query = text(
            """
            UPDATE listings
            SET fetched_at = COALESCE(updated_at, :default_ts)
            WHERE fetched_at IS NULL
            """
        )
        default_value = (default_ts or datetime.utcnow()).isoformat()
        with self.engine.begin() as conn:
            result = conn.execute(query, {"default_ts": default_value})
        return int(result.rowcount or 0)

    def clear_invalid_coordinates(self) -> int:
        query = text(
            """
            UPDATE listings
            SET lat = NULL, lon = NULL, geohash = NULL
            WHERE geohash = 's00000' OR (lat = 0.0 AND lon = 0.0)
            """
        )
        with self.engine.begin() as conn:
            result = conn.execute(query)
        return int(result.rowcount or 0)
