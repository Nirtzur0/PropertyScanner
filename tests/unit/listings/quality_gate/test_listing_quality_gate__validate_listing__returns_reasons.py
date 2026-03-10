import pytest

from src.listings.services.quality_gate import ListingQualityGate
from src.platform.domain.schema import CanonicalListing, GeoLocation, PropertyType
from src.platform.settings import QualityGateConfig


def test_validate_listing__missing_title_and_price_and_surface_area__returns_reasons():
    # Arrange
    gate = ListingQualityGate(config=QualityGateConfig())
    listing = CanonicalListing(
        id="x",
        source_id="test",
        external_id="ext",
        url="https://example.com/x",
        title="",
        price=0.0,
        surface_area_sqm=0.0,
        property_type=PropertyType.APARTMENT,
        location=GeoLocation(lat=40.4, lon=-3.7, address_full="x", city="madrid", country="ES"),
    )

    # Act
    reasons = gate.validate_listing(listing)

    # Assert
    assert set(reasons) == {"missing_title", "invalid_price", "surface_area_out_of_range"}


def test_validate_listing__missing_coordinates__returns_reason():
    gate = ListingQualityGate(config=QualityGateConfig())
    listing = CanonicalListing(
        id="x",
        source_id="test",
        external_id="ext",
        url="https://example.com/x",
        title="Apartment",
        price=250000.0,
        surface_area_sqm=80.0,
        property_type=PropertyType.APARTMENT,
        location=GeoLocation(address_full="x", city="madrid", country="ES"),
    )

    reasons = gate.validate_listing(listing)

    assert reasons == ["missing_coordinates"]


def test_validate_listing__missing_surface_area_vs_out_of_range__use_distinct_codes():
    gate = ListingQualityGate(config=QualityGateConfig())

    missing_surface = CanonicalListing(
        id="missing-surface",
        source_id="test",
        external_id="ext-1",
        url="https://example.com/missing-surface",
        title="Apartment",
        price=250000.0,
        surface_area_sqm=None,
        property_type=PropertyType.APARTMENT,
        location=GeoLocation(lat=40.4, lon=-3.7, address_full="x", city="madrid", country="ES"),
    )
    out_of_range_surface = CanonicalListing(
        id="out-of-range-surface",
        source_id="test",
        external_id="ext-2",
        url="https://example.com/out-of-range-surface",
        title="Apartment",
        price=250000.0,
        surface_area_sqm=1.0,
        property_type=PropertyType.APARTMENT,
        location=GeoLocation(lat=40.4, lon=-3.7, address_full="x", city="madrid", country="ES"),
    )

    assert "missing_surface_area" in gate.validate_listing(missing_surface)
    assert "surface_area_out_of_range" in gate.validate_listing(out_of_range_surface)


@pytest.mark.parametrize(
    "invalid_count,total_count,expected",
    [
        (0, 0, False),
        (1, 10, False),  # below min_samples
        (3, 20, True),
        (2, 20, False),
    ],
)
def test_should_halt__invalid_ratio_and_min_samples__matches_policy(invalid_count, total_count, expected):
    # Arrange
    gate = ListingQualityGate(config=QualityGateConfig(max_invalid_ratio=0.1, min_samples=20))

    # Act
    should = gate.should_halt(invalid_count=invalid_count, total_count=total_count)

    # Assert
    assert should is expected
