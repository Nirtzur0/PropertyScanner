from datetime import datetime
from pathlib import Path

from src.listings.agents.processors.immobiliare import ImmobiliareNormalizerAgent
from src.platform.domain.schema import RawListing


def test_immobiliare_parse__fixture_html__extracts_core_fields():
    # Arrange
    html = Path("tests/resources/html/immobiliare.html").read_text(encoding="utf-8")
    raw = RawListing(
        source_id="immobiliare_it",
        external_id="1357911",
        url="https://www.immobiliare.it/annunci/1357911/",
        raw_data={"html_snippet": html, "is_detail_page": True},
        fetched_at=datetime(2024, 4, 10, 0, 0, 0),
    )
    agent = ImmobiliareNormalizerAgent()

    # Act
    listing = agent._parse_item(raw)

    # Assert
    assert listing is not None
    assert listing.price == 620000.0
    assert listing.currency.value == "EUR"
    assert listing.surface_area_sqm == 95.0
    assert listing.location is not None
