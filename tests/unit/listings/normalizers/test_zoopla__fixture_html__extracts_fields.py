from datetime import datetime
from pathlib import Path

from src.listings.agents.processors.zoopla import ZooplaNormalizerAgent
from src.platform.domain.schema import RawListing


def test_zoopla_parse__fixture_html__extracts_core_fields():
    # Arrange
    html = Path("tests/resources/html/zoopla.html").read_text(encoding="utf-8")
    raw = RawListing(
        source_id="zoopla_uk",
        external_id="98765432",
        url="https://www.zoopla.co.uk/for-sale/details/98765432/",
        raw_data={"html_snippet": html, "is_detail_page": True},
        fetched_at=datetime(2024, 5, 15, 0, 0, 0),
    )
    agent = ZooplaNormalizerAgent()

    # Act
    listing = agent._parse_item(raw)

    # Assert
    assert listing is not None
    assert listing.price == 450000.0
    assert listing.currency.value == "GBP"
    assert listing.bedrooms == 2
    assert listing.bathrooms == 1
    assert listing.location is not None
    assert listing.location.city.lower() == "manchester"
