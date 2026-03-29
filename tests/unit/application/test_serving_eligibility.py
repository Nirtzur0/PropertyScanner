"""Tests for serving eligibility and valuation readiness evaluation."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.application.serving import (
    MAX_PRICE,
    MAX_ROOM_COUNT,
    MAX_SURFACE_AREA,
    MIN_PRICE,
    MIN_SURFACE_AREA,
    evaluate_serving_eligibility,
    evaluate_valuation_readiness,
)


def _make_row(**overrides):
    defaults = dict(
        price=250_000.0,
        surface_area_sqm=80.0,
        bedrooms=2,
        bathrooms=1,
        lat=40.4168,
        lon=-3.7038,
        city="Madrid",
        sold_price=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# --- evaluate_serving_eligibility ---


class TestServingEligibility:
    def test_blocked_source(self):
        row = _make_row()
        result = evaluate_serving_eligibility(row, source_status="blocked")
        assert not result.eligible
        assert result.code == "blocked_source"

    def test_price_missing(self):
        row = _make_row(price=None)
        result = evaluate_serving_eligibility(row, source_status="operational")
        assert not result.eligible
        assert result.code == "price_missing"

    def test_price_below_min(self):
        row = _make_row(price=MIN_PRICE - 1)
        result = evaluate_serving_eligibility(row, source_status="operational")
        assert not result.eligible
        assert result.code == "price_out_of_range"

    def test_price_above_max(self):
        row = _make_row(price=MAX_PRICE + 1)
        result = evaluate_serving_eligibility(row, source_status="operational")
        assert not result.eligible
        assert result.code == "price_out_of_range"

    def test_surface_area_out_of_range(self):
        row = _make_row(surface_area_sqm=MAX_SURFACE_AREA + 1)
        result = evaluate_serving_eligibility(row, source_status="operational")
        assert not result.eligible
        assert result.code == "surface_area_out_of_range"

    def test_surface_area_none_is_allowed(self):
        row = _make_row(surface_area_sqm=None)
        result = evaluate_serving_eligibility(row, source_status="operational")
        assert result.eligible

    def test_bedrooms_out_of_range(self):
        row = _make_row(bedrooms=MAX_ROOM_COUNT + 1)
        result = evaluate_serving_eligibility(row, source_status="operational")
        assert not result.eligible
        assert result.code == "bedrooms_out_of_range"

    def test_bedrooms_float_handled(self):
        """Regression: float bedrooms should not crash with int()."""
        row = _make_row(bedrooms=2.5)
        result = evaluate_serving_eligibility(row, source_status="operational")
        assert result.eligible

    def test_bathrooms_out_of_range(self):
        row = _make_row(bathrooms=MAX_ROOM_COUNT + 1)
        result = evaluate_serving_eligibility(row, source_status="operational")
        assert not result.eligible
        assert result.code == "bathrooms_out_of_range"

    def test_invalid_coordinates(self):
        row = _make_row(lat=None, lon=None)
        result = evaluate_serving_eligibility(row, source_status="operational")
        assert not result.eligible
        assert result.code == "invalid_coordinates"

    def test_coordinates_out_of_range(self):
        row = _make_row(lat=91.0, lon=0.0)
        result = evaluate_serving_eligibility(row, source_status="operational")
        assert not result.eligible
        assert result.code == "invalid_coordinates"

    def test_eligible_listing(self):
        row = _make_row()
        result = evaluate_serving_eligibility(row, source_status="operational")
        assert result.eligible
        assert result.reason is None

    def test_eligible_with_experimental_source(self):
        row = _make_row()
        result = evaluate_serving_eligibility(row, source_status="experimental")
        assert result.eligible

    def test_large_surface_area_now_accepted(self):
        """Regression: MAX_SURFACE_AREA was 1000, now 5000."""
        row = _make_row(surface_area_sqm=2500.0)
        result = evaluate_serving_eligibility(row, source_status="operational")
        assert result.eligible


# --- evaluate_valuation_readiness ---


class TestValuationReadiness:
    def test_price_missing(self):
        row = _make_row(price=None)
        result = evaluate_valuation_readiness(row)
        assert not result.ready
        assert result.reason == "target_price_required"

    def test_price_zero(self):
        row = _make_row(price=0)
        result = evaluate_valuation_readiness(row)
        assert not result.ready

    def test_surface_area_missing(self):
        row = _make_row(surface_area_sqm=None)
        result = evaluate_valuation_readiness(row)
        assert not result.ready
        assert result.reason == "target_surface_area_required"

    def test_city_missing(self):
        row = _make_row(city="")
        result = evaluate_valuation_readiness(row)
        assert not result.ready
        assert result.reason == "target_city_required"

    def test_coordinates_missing(self):
        row = _make_row(lat=None, lon=None)
        result = evaluate_valuation_readiness(row)
        assert not result.ready
        assert result.reason == "target_coordinates_required"

    def test_ready(self):
        row = _make_row()
        result = evaluate_valuation_readiness(row)
        assert result.ready
