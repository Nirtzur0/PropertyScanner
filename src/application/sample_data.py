from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List

from src.listings.source_ids import canonicalize_source_id
from src.platform.domain.models import DBListing, SourceContractRun
from src.platform.storage import StorageService
from src.platform.utils.time import utcnow


@dataclass(frozen=True)
class SampleListing:
    id: str
    external_id: str
    title: str
    price: float
    bedrooms: int
    bathrooms: int
    surface_area_sqm: float
    lat: float
    lon: float
    url: str


_SAMPLE_LISTINGS: List[SampleListing] = [
    SampleListing(
        id="sample-pisos-target",
        external_id="sample-target",
        title="Sample Piso Near Retiro",
        price=315000.0,
        bedrooms=2,
        bathrooms=1,
        surface_area_sqm=78.0,
        lat=40.4153,
        lon=-3.6883,
        url="https://example.test/pisos/sample-target",
    ),
    SampleListing(
        id="sample-pisos-comp-1",
        external_id="sample-comp-1",
        title="Comparable Piso A",
        price=320000.0,
        bedrooms=2,
        bathrooms=1,
        surface_area_sqm=80.0,
        lat=40.4160,
        lon=-3.6900,
        url="https://example.test/pisos/sample-comp-1",
    ),
    SampleListing(
        id="sample-pisos-comp-2",
        external_id="sample-comp-2",
        title="Comparable Piso B",
        price=305000.0,
        bedrooms=2,
        bathrooms=1,
        surface_area_sqm=76.0,
        lat=40.4147,
        lon=-3.6875,
        url="https://example.test/pisos/sample-comp-2",
    ),
    SampleListing(
        id="sample-pisos-comp-3",
        external_id="sample-comp-3",
        title="Comparable Piso C",
        price=332000.0,
        bedrooms=3,
        bathrooms=2,
        surface_area_sqm=90.0,
        lat=40.4171,
        lon=-3.6891,
        url="https://example.test/pisos/sample-comp-3",
    ),
]


def seed_sample_data(*, storage: StorageService) -> Dict[str, Any]:
    now = utcnow()
    canonical_source_id = canonicalize_source_id("pisos")
    session = storage.get_session()
    inserted = 0
    updated = 0
    try:
        for sample in _SAMPLE_LISTINGS:
            row = session.query(DBListing).filter(DBListing.id == sample.id).first()
            payload = asdict(sample)
            if row is None:
                row = DBListing(
                    source_id=canonical_source_id,
                    description="Seeded sample listing for local-first smoke tests.",
                    currency="EUR",
                    property_type="apartment",
                    city="Madrid",
                    country="ES",
                    listing_type="sale",
                    image_urls=["https://example.test/images/sample.jpg"],
                    status="active",
                    fetched_at=now,
                    updated_at=now,
                    listed_at=now,
                    **payload,
                )
                session.add(row)
                inserted += 1
            else:
                for key, value in payload.items():
                    setattr(row, key, value)
                row.source_id = canonical_source_id
                row.description = "Seeded sample listing for local-first smoke tests."
                row.currency = "EUR"
                row.property_type = "apartment"
                row.city = "Madrid"
                row.country = "ES"
                row.listing_type = "sale"
                row.image_urls = ["https://example.test/images/sample.jpg"]
                row.status = "active"
                row.fetched_at = now
                row.updated_at = now
                row.listed_at = now
                updated += 1

        run = SourceContractRun(
            id=f"sample-contract-{now.strftime('%Y%m%d%H%M%S%f')}",
            source_id=canonical_source_id,
            status="supported",
            metrics={
                "seeded": True,
                "row_count": len(_SAMPLE_LISTINGS),
                "reason": "sample_seed",
            },
            created_at=now,
        )
        session.add(run)
        session.commit()
    finally:
        session.close()

    return {
        "status": "ok",
        "source_id": canonical_source_id,
        "inserted": inserted,
        "updated": updated,
        "listing_ids": [sample.id for sample in _SAMPLE_LISTINGS],
    }
