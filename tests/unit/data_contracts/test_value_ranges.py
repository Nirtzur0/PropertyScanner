from datetime import datetime
from pathlib import Path

import pytest

from tests.helpers.assertions import assert_in_range
from tests.helpers.factories import make_raw_listing

from src.listings.agents.processors.idealista import IdealistaNormalizerAgent
from src.listings.agents.processors.rightmove import RightmoveNormalizerAgent
from src.listings.agents.processors.zoopla import ZooplaNormalizerAgent
from src.listings.agents.processors.immobiliare import ImmobiliareNormalizerAgent


def _fixed_now() -> datetime:
    return datetime(2024, 6, 1, 0, 0, 0)


@pytest.fixture(autouse=True)
def _no_geocode(monkeypatch):
    monkeypatch.setattr(
        "src.listings.services.geocoding_service.GeocodingService.geocode_address",
        lambda self, address: (40.4168, -3.7038),
    )


def _listings():
    cases = [
        ("idealista", "123456", "https://www.idealista.com/inmueble/123456/", "tests/resources/html/idealista.html", IdealistaNormalizerAgent),
        ("rightmove_uk", "12345678", "https://www.rightmove.co.uk/properties/12345678", "tests/resources/html/rightmove.html", RightmoveNormalizerAgent),
        ("zoopla_uk", "98765432", "https://www.zoopla.co.uk/for-sale/details/98765432/", "tests/resources/html/zoopla.html", ZooplaNormalizerAgent),
        ("immobiliare_it", "1357911", "https://www.immobiliare.it/annunci/1357911/", "tests/resources/html/immobiliare.html", ImmobiliareNormalizerAgent),
    ]
    out = []
    for source_id, external_id, url, path, cls in cases:
        html = Path(path).read_text(encoding="utf-8")
        raw = make_raw_listing(
            source_id=source_id,
            external_id=external_id,
            url=url,
            html_snippet=html,
            fetched_at=_fixed_now(),
        )
        out.append(cls()._parse_item(raw))
    return [l for l in out if l is not None]


def test_value_ranges__normalized_fixtures__numeric_ranges_sane():
    listings = _listings()
    assert listings

    assert_in_range((l.price for l in listings), min_value=1.0, context="price")
    assert_in_range((l.surface_area_sqm for l in listings), min_value=5.0, max_value=2000.0, context="surface_area_sqm")

    bedrooms = [l.bedrooms for l in listings]
    bathrooms = [l.bathrooms for l in listings]
    assert_in_range(bedrooms, min_value=0.0, max_value=30.0, allow_none=True, context="bedrooms")
    assert_in_range(bathrooms, min_value=0.0, max_value=30.0, allow_none=True, context="bathrooms")

    lats = [l.location.lat if l.location else None for l in listings]
    lons = [l.location.lon if l.location else None for l in listings]
    assert_in_range(lats, min_value=-90.0, max_value=90.0, allow_none=True, context="lat")
    assert_in_range(lons, min_value=-180.0, max_value=180.0, allow_none=True, context="lon")
