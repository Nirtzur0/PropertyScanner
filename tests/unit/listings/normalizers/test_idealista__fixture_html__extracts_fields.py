from datetime import datetime
from pathlib import Path

import pytest

from src.listings.agents.processors.idealista import IdealistaNormalizerAgent
from src.platform.domain.schema import RawListing


@pytest.fixture(autouse=True)
def _no_geocode(monkeypatch):
    monkeypatch.setattr(
        "src.listings.services.geocoding_service.GeocodingService.geocode_address",
        lambda self, address: (40.411798, -3.697245),
    )


def test_idealista_parse__fixture_html__extracts_core_fields():
    # Arrange
    html = Path("tests/resources/html/idealista.html").read_text(encoding="utf-8")
    raw = RawListing(
        source_id="idealista",
        external_id="123456",
        url="https://www.idealista.com/inmueble/123456/",
        raw_data={"html_snippet": html},
        fetched_at=datetime(2024, 6, 1, 0, 0, 0),
    )
    agent = IdealistaNormalizerAgent()

    # Act
    listing = agent._parse_item(raw)

    # Assert
    assert listing is not None
    assert listing.price == 450000.0
    assert listing.title == "Piso en venta en Calle de Alcalá, Madrid"
    assert listing.surface_area_sqm == 120.0
    assert listing.bedrooms == 3
    assert listing.bathrooms == 2
    assert listing.has_elevator is True
    assert listing.floor == 4

    assert listing.location is not None
    assert listing.location.city.lower() == "madrid"
    assert listing.location.lat == 40.411798
    assert listing.location.lon == -3.697245
