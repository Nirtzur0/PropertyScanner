from datetime import datetime
from pathlib import Path

import pytest

from tests.helpers.assertions import assert_unique
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


def test_shape_and_uniqueness__normalized_fixtures__ids_unique_and_locations_present():
    listings = _listings()
    assert len(listings) == 4

    assert_unique((l.id for l in listings), context="canonical_listing.id")

    for l in listings:
        assert l.location is not None
        assert l.location.city
