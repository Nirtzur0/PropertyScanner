from datetime import datetime
from pathlib import Path

from src.listings.agents.processors.realtor import RealtorNormalizerAgent
from src.platform.domain.schema import RawListing


def test_realtor_parse__fixture_html__extracts_core_fields() -> None:
    html = Path("tests/resources/html/realtor.html").read_text(encoding="utf-8")
    raw = RawListing(
        source_id="realtor_us",
        external_id="realtor-1",
        url="https://www.realtor.com/realestateandhomes-detail/123-Market-St_San-Francisco_CA_94105",
        raw_data={"html_snippet": html, "is_detail_page": True},
        fetched_at=datetime(2024, 6, 1, 0, 0, 0),
    )

    listing = RealtorNormalizerAgent()._parse_item(raw)

    assert listing is not None
    assert listing.price == 1250000.0
    assert listing.currency.value == "USD"
    assert listing.surface_area_sqm == 145.0
    assert listing.bedrooms == 3
    assert listing.location is not None
    assert listing.location.city == "San Francisco"
    assert len(listing.image_urls) == 2
