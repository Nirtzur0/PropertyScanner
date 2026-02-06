from pathlib import Path

import pytest

from tests.helpers.assertions import (
    assert_in_range,
    assert_missing_rate,
    assert_required_fields,
    assert_unique,
)
from tests.helpers.contracts import CANONICAL_LISTING_REQUIRED_FIELDS

from src.listings.agents.crawlers.italy.immobiliare import ImmobiliareCrawlerAgent
from src.listings.agents.crawlers.uk.rightmove import RightmoveCrawlerAgent
from src.listings.agents.crawlers.uk.zoopla import ZooplaCrawlerAgent
from src.listings.agents.processors.immobiliare import ImmobiliareNormalizerAgent
from src.listings.agents.processors.rightmove import RightmoveNormalizerAgent
from src.listings.agents.processors.zoopla import ZooplaNormalizerAgent
from src.listings.repositories.listings import ListingsRepository
from src.listings.scraping.client import FetchResult
from src.listings.services.listing_persistence import ListingPersistenceService


class DummyCompliance:
    def check_and_wait(self, url: str, rate_limit_seconds: float = 1.0) -> bool:
        return True


def _listing_store(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'listings.db'}"
    listings_repo = ListingsRepository(db_url=db_url)
    persistence = ListingPersistenceService(listings_repo)
    return listings_repo, persistence


@pytest.mark.e2e
def test_end_to_end_output_sanity__fixture_html__db_rows_sane(tmp_path):
    # Arrange
    rightmove_search = Path("tests/resources/html/rightmove_search.html").read_text(encoding="utf-8")
    rightmove_detail = Path("tests/resources/html/rightmove.html").read_text(encoding="utf-8")
    zoopla_search = Path("tests/resources/html/zoopla_search.html").read_text(encoding="utf-8")
    zoopla_detail = Path("tests/resources/html/zoopla.html").read_text(encoding="utf-8")
    immobiliare_detail = Path("tests/resources/html/immobiliare.html").read_text(encoding="utf-8")

    listings_repo, persistence = _listing_store(tmp_path)

    # Rightmove
    rm = RightmoveCrawlerAgent(
        config={"id": "rightmove_uk", "base_url": "https://www.rightmove.co.uk", "rate_limit": {"period_seconds": 0}},
        compliance_manager=DummyCompliance(),
    )
    rm.scrape_client.snapshot_service.save_snapshot = lambda **kwargs: None

    def rm_fetch(url, timeout_s=30.0, **_kwargs):
        if "find.html" in url:
            return rightmove_search
        if "/properties/12345678" in url:
            return rightmove_detail
        return None

    def rm_fetch_batch(urls, **_kwargs):
        return [FetchResult(url=u, html=(rightmove_detail if "/properties/12345678" in u else rm_fetch(u))) for u in urls]

    rm.scrape_client.fetch_html = rm_fetch
    rm.scrape_client.fetch_html_batch = rm_fetch_batch

    rm_raw = rm.run({"start_url": "https://www.rightmove.co.uk/property-for-sale/find.html?index=0"}).data
    rm_norm = RightmoveNormalizerAgent().run({"raw_listings": rm_raw}).data

    # Zoopla
    zp = ZooplaCrawlerAgent(
        config={"id": "zoopla_uk", "base_url": "https://www.zoopla.co.uk", "rate_limit": {"period_seconds": 0}},
        compliance_manager=DummyCompliance(),
    )
    zp.scrape_client.snapshot_service.save_snapshot = lambda **kwargs: None

    def zp_fetch(url, timeout_s=30.0, **_kwargs):
        if "/details/98765432" in url:
            return zoopla_detail
        if "property" in url or "for-sale" in url:
            return zoopla_search
        return None

    def zp_fetch_batch(urls, **_kwargs):
        return [FetchResult(url=u, html=(zoopla_detail if "/details/98765432" in u else zp_fetch(u))) for u in urls]

    zp.scrape_client.fetch_html = zp_fetch
    zp.scrape_client.fetch_html_batch = zp_fetch_batch

    zp_raw = zp.run({"start_url": "https://www.zoopla.co.uk/for-sale/property/manchester/"}).data
    zp_norm = ZooplaNormalizerAgent().run({"raw_listings": zp_raw}).data

    # Immobiliare (detail-only)
    im = ImmobiliareCrawlerAgent(
        config={"id": "immobiliare_it", "base_url": "https://www.immobiliare.it", "rate_limit": {"period_seconds": 0}},
        compliance_manager=DummyCompliance(),
    )
    im.scrape_client.snapshot_service.save_snapshot = lambda **kwargs: None

    def im_fetch_batch(urls, **_kwargs):
        return [FetchResult(url=u, html=(immobiliare_detail if "immobiliare.it/annunci/1357911" in u else None)) for u in urls]

    im.scrape_client.fetch_html_batch = im_fetch_batch

    im_raw = im.run({"listing_url": "https://www.immobiliare.it/annunci/1357911/"}).data
    im_norm = ImmobiliareNormalizerAgent().run({"raw_listings": im_raw}).data

    all_canonical = list(rm_norm) + list(zp_norm) + list(im_norm)

    # Act
    saved = persistence.save_listings(all_canonical)

    # Assert: shape + required fields
    assert saved == 3
    assert_unique((l.id for l in all_canonical), context="canonical_listing.id")

    for l in all_canonical:
        assert_required_fields(l, CANONICAL_LISTING_REQUIRED_FIELDS, context=f"normalized:{l.source_id}")

    # Assert: missingness
    assert_missing_rate(all_canonical, "location", 0.0, context="normalized")

    # Assert: value ranges
    assert_in_range((l.price for l in all_canonical), min_value=1.0, context="price")
    assert_in_range((l.surface_area_sqm for l in all_canonical), min_value=5.0, max_value=2000.0, context="surface_area_sqm")
    assert_in_range((l.location.lat for l in all_canonical), min_value=-90.0, max_value=90.0, allow_none=True, context="lat")
    assert_in_range((l.location.lon for l in all_canonical), min_value=-180.0, max_value=180.0, allow_none=True, context="lon")

    # Assert: persistence sanity
    df = listings_repo.load_listings_df()
    assert len(df) == 3
    assert df["id"].nunique() == 3
    assert (df["price"] > 0).all()
