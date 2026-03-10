from __future__ import annotations

from src.listings.services.quality_gate import ListingQualityGate
from src.platform.domain.schema import CanonicalListing, Currency, GeoLocation, PropertyType


def _listing(**overrides):
    payload = {
        "id": "listing-1",
        "source_id": "pisos",
        "external_id": "ext-1",
        "url": "https://example.com/listing-1",
        "title": "Apartment",
        "price": 250000.0,
        "currency": Currency.EUR,
        "listing_type": "sale",
        "property_type": PropertyType.APARTMENT,
        "bedrooms": 2,
        "bathrooms": 1,
        "surface_area_sqm": 80.0,
        "location": GeoLocation(
            lat=40.4,
            lon=-3.7,
            address_full="Street 1",
            city="Madrid",
            country="ES",
        ),
    }
    payload.update(overrides)
    return CanonicalListing(**payload)


def test_quality_gate__accepts_contract_valid_listing() -> None:
    gate = ListingQualityGate()
    assert gate.validate_listing(_listing()) == []


def test_quality_gate__rejects_missing_surface_and_invalid_ranges() -> None:
    gate = ListingQualityGate()
    listing = _listing(
        price=2.0,
        surface_area_sqm=None,
        bedrooms=99,
        bathrooms=-1,
    )
    reasons = gate.validate_listing(listing)
    assert "price_out_of_range" in reasons
    assert "missing_surface_area" in reasons
    assert "bedrooms_out_of_range" in reasons
    assert "bathrooms_out_of_range" in reasons


def test_quality_gate__rejects_missing_identifiers_and_location() -> None:
    gate = ListingQualityGate()
    listing = _listing(
        source_id="",
        external_id="",
        title="",
        location=None,
    )
    reasons = gate.validate_listing(listing)
    assert "missing_source_id" in reasons
    assert "missing_external_id" in reasons
    assert "missing_title" in reasons
    assert "missing_location" in reasons
