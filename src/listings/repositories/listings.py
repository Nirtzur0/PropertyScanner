from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import text

from src.platform.domain.listing_updates import ListingUpsertPayload
from src.platform.domain.models import DBListing
from src.platform.db.base import RepositoryBase
from src.platform.utils.time import utcnow


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

    def load_listings_df(
        self,
        city: Optional[str] = None,
        listing_type: Optional[str] = None,
    ) -> pd.DataFrame:
        query = "SELECT * FROM listings"
        params: Dict[str, str] = {}
        filters: List[str] = []
        if city:
            filters.append("LOWER(city) = :city")
            params["city"] = city.strip().lower()
        if listing_type and self.has_column("listings", "listing_type"):
            listing_norm = listing_type.strip().lower()
            if listing_norm in ("sale", "rent"):
                filters.append("LOWER(listing_type) = :listing_type")
                params["listing_type"] = listing_norm
        if filters:
            query += " WHERE " + " AND ".join(filters)
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
        has_sold_price = self.has_column("listings", "sold_price")
        has_sold_at = self.has_column("listings", "sold_at")
        query = """
            SELECT id, city, price, surface_area_sqm, listed_at, updated_at, status
        """
        if has_sold_price:
            query = query.rstrip() + ", sold_price\n"
        if has_sold_at:
            query = query.rstrip() + ", sold_at\n"
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

    def get_listing_by_id(self, listing_id: str) -> Optional[DBListing]:
        if not listing_id:
            return None
        session = self.storage.get_session()
        try:
            return session.query(DBListing).filter_by(id=listing_id).first()
        finally:
            session.close()

    def fetch_listing_states(self, listing_ids: List[str]) -> Dict[str, Dict[str, object]]:
        if not listing_ids:
            return {}
        session = self.storage.get_session()
        try:
            rows = (
                session.query(
                    DBListing.id,
                    DBListing.price,
                    DBListing.listed_at,
                    DBListing.status,
                    DBListing.sold_at,
                    DBListing.geohash,
                    DBListing.property_type,
                    DBListing.currency,
                )
                .filter(DBListing.id.in_(listing_ids))
                .all()
            )
            return {
                row.id: {
                    "price": row.price,
                    "listed_at": row.listed_at,
                    "status": row.status,
                    "sold_at": row.sold_at,
                    "geohash": row.geohash,
                    "property_type": row.property_type,
                    "currency": row.currency,
                }
                for row in rows
            }
        finally:
            session.close()

    def upsert_listings(self, payloads: List[ListingUpsertPayload]) -> int:
        if not payloads:
            return 0
        session = self.storage.get_session()
        try:
            listing_ids = [payload.listing_id for payload in payloads if payload]
            existing_rows = (
                session.query(DBListing).filter(DBListing.id.in_(listing_ids)).all()
                if listing_ids
                else []
            )
            existing = {row.id: row for row in existing_rows}
            created = 0

            for payload in payloads:
                if not payload:
                    continue
                db_item = existing.get(payload.listing_id)
                if db_item is None:
                    db_item = DBListing(id=payload.listing_id)
                    session.add(db_item)
                    created += 1
                for field, value in payload.fields.items():
                    setattr(db_item, field, value)
                if payload.listed_at is not None:
                    db_item.listed_at = payload.listed_at
                if payload.sold_at is not None:
                    db_item.sold_at = payload.sold_at
                if payload.geohash is not None:
                    db_item.geohash = payload.geohash

            session.commit()
            return created
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def fix_missing_fetched_at(self, default_ts: Optional[datetime] = None) -> int:
        query = text(
            """
            UPDATE listings
            SET fetched_at = COALESCE(updated_at, :default_ts)
            WHERE fetched_at IS NULL
            """
        )
        default_value = (default_ts or utcnow()).isoformat()
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

    def load_listings_for_training(
        self,
        *,
        listing_type: str = "sale",
        label_source: str = "auto",
    ) -> List[Dict[str, Any]]:
        extra_cols = []
        if self.has_column("listings", "plot_area_sqm"):
            extra_cols.append("plot_area_sqm")
        if self.has_column("listings", "image_embeddings"):
            extra_cols.append("image_embeddings")

        base_cols = [
            "id",
            "source_id",
            "external_id",
            "url",
            "title",
            "description",
            "price",
            "sold_price",
            "city",
            "bedrooms",
            "bathrooms",
            "surface_area_sqm",
            "floor",
            "lat",
            "lon",
            "image_urls",
            "vlm_description",
            "property_type",
            "listed_at",
            "updated_at",
            "text_sentiment",
            "image_sentiment",
            "has_elevator",
            "listing_type",
            "status",
            "sold_at",
        ]
        select_cols = base_cols + extra_cols

        query = f"""
            SELECT {", ".join(select_cols)}
            FROM listings
            WHERE price > 0
        """
        params: Dict[str, Any] = {}
        if listing_type and listing_type != "all" and self.has_column("listings", "listing_type"):
            query += " AND listing_type = :listing_type"
            params["listing_type"] = listing_type
        if label_source == "sold" and self.has_column("listings", "status"):
            query += " AND status = 'sold'"

        with self.engine.connect() as conn:
            rows = conn.execute(text(query), params).fetchall()
        return [dict(row._mapping) for row in rows]

    def fetch_vlm_candidates(self, *, override: bool = False) -> List[Dict[str, Any]]:
        if not self.has_column("listings", "image_urls"):
            return []

        query = """
            SELECT id, image_urls
            FROM listings
            WHERE image_urls IS NOT NULL AND image_urls != '[]' AND image_urls != ''
        """
        if not override and self.has_column("listings", "vlm_description"):
            query += " AND (vlm_description IS NULL OR vlm_description = '')"

        with self.engine.connect() as conn:
            rows = conn.execute(text(query)).fetchall()
        return [dict(row._mapping) for row in rows]

    def update_vlm_descriptions(self, updates: List[Tuple[str, str]]) -> int:
        if not updates or not self.has_column("listings", "vlm_description"):
            return 0
        query = text("UPDATE listings SET vlm_description = :desc WHERE id = :listing_id")
        payloads = [{"desc": desc, "listing_id": listing_id} for listing_id, desc in updates]
        with self.engine.begin() as conn:
            result = conn.execute(query, payloads)
        return int(result.rowcount or 0)
