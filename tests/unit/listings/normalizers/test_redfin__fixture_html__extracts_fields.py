from datetime import datetime
from pathlib import Path

from src.listings.agents.processors.redfin import RedfinNormalizerAgent
from src.platform.domain.schema import RawListing


def test_redfin_parse__fixture_html__extracts_core_fields() -> None:
    html = Path("tests/resources/html/redfin.html").read_text(encoding="utf-8")
    raw = RawListing(
        source_id="redfin_us",
        external_id="redfin-1",
        url="https://www.redfin.com/CA/San-Francisco/88-Dolores-St-94103/home/123456",
        raw_data={"html_snippet": html, "is_detail_page": True},
        fetched_at=datetime(2024, 6, 1, 0, 0, 0),
    )

    listing = RedfinNormalizerAgent()._parse_item(raw)

    assert listing is not None
    assert listing.price == 1495000.0
    assert listing.currency.value == "USD"
    assert listing.surface_area_sqm == 172.0
    assert listing.bedrooms == 4
    assert listing.location is not None
    assert listing.location.city == "San Francisco"
    assert len(listing.image_urls) == 1
