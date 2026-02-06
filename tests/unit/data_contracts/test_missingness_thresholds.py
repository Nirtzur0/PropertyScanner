from datetime import datetime
from pathlib import Path

import pytest

from tests.helpers.assertions import assert_missing_rate
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


def _normalized_fixture_listings():
    fixtures = [
        (
            "idealista",
            "123456",
            "https://www.idealista.com/inmueble/123456/",
            "tests/resources/html/idealista.html",
            IdealistaNormalizerAgent,
        ),
        (
            "rightmove_uk",
            "12345678",
            "https://www.rightmove.co.uk/properties/12345678",
            "tests/resources/html/rightmove.html",
            RightmoveNormalizerAgent,
        ),
        (
            "zoopla_uk",
            "98765432",
            "https://www.zoopla.co.uk/for-sale/details/98765432/",
            "tests/resources/html/zoopla.html",
            ZooplaNormalizerAgent,
        ),
        (
            "immobiliare_it",
            "1357911",
            "https://www.immobiliare.it/annunci/1357911/",
            "tests/resources/html/immobiliare.html",
            ImmobiliareNormalizerAgent,
        ),
    ]

    out = []
    for source_id, external_id, url, path, cls in fixtures:
        html = Path(path).read_text(encoding="utf-8")
        raw = make_raw_listing(
            source_id=source_id,
            external_id=external_id,
            url=url,
            html_snippet=html,
            fetched_at=_fixed_now(),
        )
        agent = cls()
        out.append(agent._parse_item(raw))
    return out


def test_missingness_thresholds__normalized_fixtures__key_fields_non_missing():
    # Arrange
    listings = [l for l in _normalized_fixture_listings() if l is not None]
    assert listings

    # Act / Assert
    # For fixture-based normalizers, these should be fully populated.
    assert_missing_rate(listings, "title", 0.0, context="normalized_fixtures")
    assert_missing_rate(listings, "price", 0.0, context="normalized_fixtures")
    assert_missing_rate(listings, "surface_area_sqm", 0.0, context="normalized_fixtures")
    assert_missing_rate(listings, "property_type", 0.0, context="normalized_fixtures")
    assert_missing_rate(listings, "location", 0.0, context="normalized_fixtures")
