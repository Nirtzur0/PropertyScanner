"""Regression tests for quality gate fixes."""
import pytest

from src.listings.services.quality_gate import ListingQualityGate
from src.platform.domain.schema import CanonicalListing, GeoLocation, PropertyType
from src.platform.settings import QualityGateConfig


def _make_valid_listing(**overrides):
    defaults = dict(
        id="test-id",
        source_id="test",
        external_id="ext-001",
        url="https://example.com/test",
        title="Test Property",
        price=250000.0,
        surface_area_sqm=80.0,
        property_type=PropertyType.APARTMENT,
        location=GeoLocation(lat=40.4, lon=-3.7, address_full="x", city="madrid", country="ES"),
    )
    defaults.update(overrides)
    return CanonicalListing(**defaults)


class TestMaxSurfaceAreaRegression:
    """MAX_SURFACE_AREA was 1000 sqm, too strict for villas and commercial."""

    def test_large_villa_accepted(self):
        gate = ListingQualityGate()
        listing = _make_valid_listing(surface_area_sqm=2500.0)
        reasons = gate.validate_listing(listing)
        assert "surface_area_out_of_range" not in reasons

    def test_above_new_max_rejected(self):
        gate = ListingQualityGate()
        listing = _make_valid_listing(surface_area_sqm=6000.0)
        reasons = gate.validate_listing(listing)
        assert "surface_area_out_of_range" in reasons

    def test_boundary_at_5000_accepted(self):
        gate = ListingQualityGate()
        listing = _make_valid_listing(surface_area_sqm=5000.0)
        reasons = gate.validate_listing(listing)
        assert "surface_area_out_of_range" not in reasons


class TestRoomCountBoundaries:
    """Room count boundary validation."""

    @pytest.mark.parametrize("bedrooms", [0, 1, 10, 20])
    def test_valid_integer_bedrooms(self, bedrooms):
        gate = ListingQualityGate()
        listing = _make_valid_listing(bedrooms=bedrooms)
        reasons = gate.validate_listing(listing)
        assert "bedrooms_out_of_range" not in reasons

    def test_bedrooms_above_max_rejected(self):
        gate = ListingQualityGate()
        listing = _make_valid_listing(bedrooms=21)
        reasons = gate.validate_listing(listing)
        assert "bedrooms_out_of_range" in reasons

    def test_none_bedrooms_accepted(self):
        gate = ListingQualityGate()
        listing = _make_valid_listing(bedrooms=None)
        reasons = gate.validate_listing(listing)
        assert "bedrooms_out_of_range" not in reasons
