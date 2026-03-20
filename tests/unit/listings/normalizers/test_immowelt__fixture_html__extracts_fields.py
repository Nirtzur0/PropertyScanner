from datetime import datetime
from pathlib import Path

from src.listings.agents.processors.immowelt import ImmoweltNormalizerAgent
from src.platform.domain.schema import RawListing


def test_immowelt_parse__fixture_html__extracts_core_fields() -> None:
    html = Path("tests/resources/html/immowelt.html").read_text(encoding="utf-8")
    raw = RawListing(
        source_id="immowelt_de",
        external_id="immowelt-1",
        url="https://www.immowelt.de/expose/immowelt-1",
        raw_data={"html_snippet": html, "is_detail_page": True},
        fetched_at=datetime(2024, 6, 1, 0, 0, 0),
    )

    listing = ImmoweltNormalizerAgent()._parse_item(raw)

    assert listing is not None
    assert listing.price == 640000.0
    assert listing.currency.value == "EUR"
    assert listing.surface_area_sqm == 84.0
    assert listing.bedrooms == 3
    assert listing.location is not None
    assert listing.location.city == "Berlin"
    assert len(listing.image_urls) == 1
