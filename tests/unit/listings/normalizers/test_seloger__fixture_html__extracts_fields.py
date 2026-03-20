from datetime import datetime
from pathlib import Path

from src.listings.agents.processors.seloger import SeLogerNormalizerAgent
from src.platform.domain.schema import RawListing


def test_seloger_parse__fixture_html__extracts_core_fields() -> None:
    html = Path("tests/resources/html/seloger.html").read_text(encoding="utf-8")
    raw = RawListing(
        source_id="seloger_fr",
        external_id="seloger-1",
        url="https://www.seloger.com/annonces/achat/appartement/paris-11eme-75/seloger-1.htm",
        raw_data={"html_snippet": html, "is_detail_page": True},
        fetched_at=datetime(2024, 6, 1, 0, 0, 0),
    )

    listing = SeLogerNormalizerAgent()._parse_item(raw)

    assert listing is not None
    assert listing.price == 890000.0
    assert listing.currency.value == "EUR"
    assert listing.surface_area_sqm == 102.0
    assert listing.bathrooms == 2
    assert listing.location is not None
    assert listing.location.city == "Paris"
    assert len(listing.image_urls) == 2
