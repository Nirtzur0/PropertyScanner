from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.listings.services.listing_adapter import db_listing_to_canonical
from src.platform.domain.models import DBListing
from src.platform.storage import StorageService
from src.platform.utils.serialize import model_to_dict


class ListingQueryService:
    def __init__(self, *, storage: StorageService) -> None:
        self.storage = storage

    def list_listings(
        self,
        *,
        source_id: Optional[str] = None,
        city: Optional[str] = None,
        listing_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        session = self.storage.get_session()
        try:
            query = session.query(DBListing).order_by(DBListing.updated_at.desc())
            if source_id:
                query = query.filter(DBListing.source_id == source_id)
            if city:
                query = query.filter(DBListing.city == city)
            if listing_type:
                query = query.filter(DBListing.listing_type == listing_type)
            total = query.count()
            rows = query.offset(max(offset, 0)).limit(max(1, min(limit, 200))).all()
            items: List[Dict[str, Any]] = []
            for row in rows:
                canonical = db_listing_to_canonical(row)
                items.append(model_to_dict(canonical))
            return {"total": total, "items": items}
        finally:
            session.close()

    def get_listing(self, listing_id: str) -> Optional[Dict[str, Any]]:
        session = self.storage.get_session()
        try:
            row = session.query(DBListing).filter(DBListing.id == listing_id).first()
            if row is None:
                return None
            return model_to_dict(db_listing_to_canonical(row))
        finally:
            session.close()
