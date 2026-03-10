from __future__ import annotations

from datetime import datetime
from typing import Callable, Dict, List, Optional

import structlog
import geolib.geohash

from src.platform.domain.listing_updates import ListingUpsertPayload
from src.platform.domain.schema import CanonicalListing
from src.listings.repositories.listings import ListingsRepository
from src.listings.source_ids import canonicalize_source_id
from src.listings.services.feature_sanitizer import sanitize_listing_features
from src.platform.utils.time import utcnow

logger = structlog.get_logger(__name__)


class ListingPersistenceService:
    """
    Applies ingestion rules and persists listings via ListingsRepository.
    Keeps business rules out of StorageService and DB access inside repositories.
    """

    def __init__(
        self,
        listings_repo: ListingsRepository,
        *,
        now_fn: Callable[[], datetime] = utcnow,
    ) -> None:
        self.listings_repo = listings_repo
        self.now_fn = now_fn

    def save_listings(self, listings: List[CanonicalListing]) -> int:
        if not listings:
            return 0

        listing_ids = [item.id for item in listings if item and item.id]
        states = self.listings_repo.fetch_listing_states(listing_ids)
        now = self.now_fn()

        payloads: List[ListingUpsertPayload] = []
        for item in listings:
            if not item or not getattr(item, "id", None):
                logger.warning("listing_missing_id")
                continue

            raw_price = item.price
            try:
                sanitize_listing_features(item)
                price_valid = item.price is not None and item.price > 0
                state = states.get(item.id)

                if not price_valid:
                    logger.warning(
                        "listing_price_outlier",
                        id=item.id,
                        price=raw_price,
                        listing_type=getattr(item, "listing_type", None),
                    )
                    if state is None or state.get("price") is None:
                        continue

                fields = self._build_fields(item, state, price_valid, now)
                listed_at = self._resolve_listed_at(item, state, now)
                sold_at = self._resolve_sold_at(item, state, now)
                geohash = self._resolve_geohash(item, state)

                payloads.append(
                    ListingUpsertPayload(
                        listing_id=item.id,
                        fields=fields,
                        listed_at=listed_at,
                        sold_at=sold_at,
                        geohash=geohash,
                    )
                )
            except Exception as exc:
                logger.error("listing_persist_failed", id=item.id, error=str(exc))
                continue

        return self.listings_repo.upsert_listings(payloads)

    def _build_fields(
        self,
        item: CanonicalListing,
        state: Optional[Dict[str, object]],
        price_valid: bool,
        now: datetime,
    ) -> Dict[str, object]:
        fields: Dict[str, object] = {
            "source_id": canonicalize_source_id(item.source_id),
            "external_id": item.external_id,
            "url": str(item.url),
            "title": item.title,
            "fetched_at": now,
            "bedrooms": item.bedrooms,
            "surface_area_sqm": item.surface_area_sqm,
            "updated_at": item.updated_at,
        }

        status_value = self._normalize_enum(item.status)
        if status_value:
            fields["status"] = status_value

        if price_valid:
            fields["price"] = item.price

        if item.vlm_description:
            fields["vlm_description"] = item.vlm_description
        if item.description:
            fields["description"] = item.description
        if item.analysis_meta:
            fields["analysis_meta"] = item.analysis_meta
        if item.text_sentiment is not None:
            fields["text_sentiment"] = item.text_sentiment
        if item.image_sentiment is not None:
            fields["image_sentiment"] = item.image_sentiment
        if item.tags is not None:
            fields["tags"] = item.tags

        if item.bathrooms is not None:
            fields["bathrooms"] = item.bathrooms
        if item.plot_area_sqm is not None:
            fields["plot_area_sqm"] = item.plot_area_sqm
        if item.floor is not None:
            fields["floor"] = item.floor
        if item.has_elevator is not None:
            fields["has_elevator"] = item.has_elevator

        if item.listing_type:
            fields["listing_type"] = item.listing_type

        currency = self._normalize_enum(item.currency)
        if currency and (state is None or not state.get("currency")):
            fields["currency"] = currency

        if state is None or not state.get("property_type"):
            prop_type = self._normalize_enum(item.property_type)
            if prop_type:
                fields["property_type"] = prop_type

        if item.location:
            fields["address_full"] = item.location.address_full
            if item.location.city:
                fields["city"] = item.location.city
            if item.location.zip_code:
                fields["zip_code"] = item.location.zip_code
            if item.location.country:
                fields["country"] = item.location.country
            fields["lat"] = item.location.lat
            fields["lon"] = item.location.lon

        if item.image_urls:
            fields["image_urls"] = [str(u) for u in item.image_urls]
        if item.image_embeddings:
            fields["image_embeddings"] = item.image_embeddings

        if item.estimated_rent is not None:
            fields["estimated_rent"] = item.estimated_rent
        if item.gross_yield is not None:
            fields["gross_yield"] = item.gross_yield
        if item.sold_price is not None:
            fields["sold_price"] = item.sold_price

        return fields

    def _resolve_listed_at(
        self,
        item: CanonicalListing,
        state: Optional[Dict[str, object]],
        now: datetime,
    ) -> Optional[datetime]:
        if state is None:
            if item.listed_at and item.listed_at < now:
                return item.listed_at
            return now

        if item.listed_at:
            existing = state.get("listed_at")
            if existing is None or item.listed_at < existing:
                return item.listed_at
        return None

    def _resolve_sold_at(
        self,
        item: CanonicalListing,
        state: Optional[Dict[str, object]],
        now: datetime,
    ) -> Optional[datetime]:
        incoming_status = self._normalize_enum(item.status)
        existing_status = (state or {}).get("status")
        sold_at = None

        if state is not None and existing_status == "active" and incoming_status == "sold":
            sold_at = now

        if incoming_status == "sold" and item.sold_at:
            if state is None or state.get("sold_at") is None:
                if sold_at is None:
                    sold_at = item.sold_at

        return sold_at

    def _resolve_geohash(
        self,
        item: CanonicalListing,
        state: Optional[Dict[str, object]],
    ) -> Optional[str]:
        if item.location and item.location.lat is not None and item.location.lon is not None:
            if state is None or not state.get("geohash"):
                try:
                    return geolib.geohash.encode(item.location.lat, item.location.lon, 9)
                except Exception as exc:
                    logger.warning("geohash_failed", id=item.id, error=str(exc))
        return None

    @staticmethod
    def _normalize_enum(value: object) -> Optional[str]:
        if value is None:
            return None
        if hasattr(value, "value"):
            return str(value.value)
        return str(value)
