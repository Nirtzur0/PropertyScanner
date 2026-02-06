from datetime import datetime
from pathlib import Path

from src.listings.agents.processors.rightmove import RightmoveNormalizerAgent
from src.platform.domain.schema import RawListing


def test_rightmove_parse__fixture_html__extracts_core_fields():
    # Arrange
    html = Path("tests/resources/html/rightmove.html").read_text(encoding="utf-8")
    raw = RawListing(
        source_id="rightmove_uk",
        external_id="12345678",
        url="https://www.rightmove.co.uk/properties/12345678",
        raw_data={"html_snippet": html, "is_detail_page": True},
        fetched_at=datetime(2024, 6, 1, 0, 0, 0),
    )
    agent = RightmoveNormalizerAgent()

    # Act
    listing = agent._parse_item(raw)

    # Assert
    assert listing is not None
    assert listing.price == 850000.0
    assert listing.currency.value == "GBP"
    assert listing.bedrooms == 4
    assert listing.bathrooms == 2
    assert listing.location is not None
    assert listing.location.city.lower() == "london"
