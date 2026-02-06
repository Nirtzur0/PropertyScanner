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
        location=GeoLocation(address_full="x", city="madrid", country="ES"),
    )

    # Act
    reasons = gate.validate_listing(listing)

    # Assert
    assert set(reasons) == {"missing_title", "invalid_price", "invalid_surface_area"}


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
