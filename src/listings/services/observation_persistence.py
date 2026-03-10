from __future__ import annotations

import hashlib
from typing import Any, Dict, Iterable, List

from src.platform.domain.models import ListingEntity, ListingObservation
from src.platform.domain.schema import CanonicalListing, RawListing
from src.platform.storage import StorageService
from src.platform.utils.time import utcnow


def _stable_id(*parts: object) -> str:
    payload = "|".join(str(part or "") for part in parts)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def _field_confidence_for_listing(listing: CanonicalListing) -> Dict[str, float]:
    confidence: Dict[str, float] = {
        "title": 1.0 if listing.title else 0.0,
        "price": 1.0 if listing.price else 0.0,
        "listing_type": 1.0 if listing.listing_type else 0.0,
        "currency": 1.0 if listing.currency else 0.0,
    }
    if listing.surface_area_sqm is not None:
        confidence["surface_area_sqm"] = 1.0
    if listing.bedrooms is not None:
        confidence["bedrooms"] = 1.0
    if listing.bathrooms is not None:
        confidence["bathrooms"] = 1.0
    if listing.location is not None:
        confidence["city"] = 1.0 if listing.location.city else 0.0
        confidence["country"] = 1.0 if listing.location.country else 0.0
        confidence["coordinates"] = 1.0 if listing.location.lat is not None and listing.location.lon is not None else 0.0
    return confidence


class ObservationPersistenceService:
    def __init__(self, *, storage: StorageService) -> None:
        self.storage = storage

    def record_raw_observations(self, raw_listings: Iterable[RawListing]) -> int:
        rows = list(raw_listings)
        if not rows:
            return 0
        session = self.storage.get_session()
        try:
            created = 0
            for item in rows:
                observed_at = item.fetched_at or utcnow()
                row_id = _stable_id(item.source_id, item.external_id, observed_at.isoformat(), "bronze_raw")
                existing = session.query(ListingObservation).filter(ListingObservation.id == row_id).first()
                if existing is not None:
                    continue
                session.add(
                    ListingObservation(
                        id=row_id,
                        source_id=str(item.source_id),
                        external_id=str(item.external_id),
                        listing_id=None,
                        observed_at=observed_at,
                        raw_payload=item.model_dump(mode="json"),
                        normalized_payload={},
                        status="bronze_raw",
                        field_confidence={},
                    )
                )
                created += 1
            session.commit()
            return created
        finally:
            session.close()

    def record_normalized_observations(
        self,
        listings: Iterable[CanonicalListing],
        *,
        status: str,
        rejection_reasons: Dict[str, List[str]] | None = None,
    ) -> int:
        rows = list(listings)
        if not rows:
            return 0
        rejection_reasons = rejection_reasons or {}
        session = self.storage.get_session()
        try:
            created = 0
            for item in rows:
                observed_at = item.updated_at or item.listed_at or utcnow()
                row_id = _stable_id(item.source_id, item.external_id, observed_at.isoformat(), status)
                existing = session.query(ListingObservation).filter(ListingObservation.id == row_id).first()
                if existing is not None:
                    continue
                normalized_payload = item.model_dump(mode="json")
                if rejection_reasons.get(item.id):
                    normalized_payload["rejection_reasons"] = list(rejection_reasons[item.id])
                session.add(
                    ListingObservation(
                        id=row_id,
                        source_id=str(item.source_id),
                        external_id=str(item.external_id),
                        listing_id=str(item.id),
                        observed_at=observed_at,
                        raw_payload={},
                        normalized_payload=normalized_payload,
                        status=status,
                        field_confidence=_field_confidence_for_listing(item),
                    )
                )
                created += 1
            session.commit()
            return created
        finally:
            session.close()

    def upsert_listing_entities(self, listings: Iterable[CanonicalListing]) -> int:
        rows = list(listings)
        if not rows:
            return 0
        session = self.storage.get_session()
        try:
            created = 0
            for item in rows:
                entity_id = _stable_id("entity", item.id)
                entity = session.query(ListingEntity).filter(ListingEntity.id == entity_id).first()
                source_link = {
                    "source_id": str(item.source_id),
                    "external_id": str(item.external_id),
                    "url": str(item.url),
                }
                attributes: Dict[str, Any] = {
                    "title": item.title,
                    "listing_type": item.listing_type,
                    "currency": str(item.currency),
                    "price": item.price,
                    "surface_area_sqm": item.surface_area_sqm,
                    "bedrooms": item.bedrooms,
                    "bathrooms": item.bathrooms,
                }
                if item.location is not None:
                    attributes["city"] = item.location.city
                    attributes["country"] = item.location.country
                    attributes["lat"] = item.location.lat
                    attributes["lon"] = item.location.lon
                if entity is None:
                    session.add(
                        ListingEntity(
                            id=entity_id,
                            canonical_listing_id=str(item.id),
                            attributes=attributes,
                            source_links=[source_link],
                        )
                    )
                    created += 1
                    continue
                entity.canonical_listing_id = str(item.id)
                entity.attributes = attributes
                links = list(entity.source_links or [])
                if source_link not in links:
                    links.append(source_link)
                entity.source_links = links
                entity.updated_at = utcnow()
            session.commit()
            return created
        finally:
            session.close()
