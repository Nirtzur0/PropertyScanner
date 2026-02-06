from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.helpers.assertions import assert_required_fields
from tests.helpers.contracts import CANONICAL_LISTING_REQUIRED_FIELDS

from src.listings.agents.crawlers.uk.rightmove import RightmoveCrawlerAgent
from src.listings.agents.processors.rightmove import RightmoveNormalizerAgent
from src.listings.scraping.client import FetchResult


class DummyCompliance:
    def check_and_wait(self, url: str, rate_limit_seconds: float = 1.0) -> bool:
        return True


@pytest.mark.integration
def test_boundary_payload_contract__crawler_to_normalizer__raw_and_canonical_shapes(tmp_path):
    # Arrange
    search_html = Path("tests/resources/html/rightmove_search.html").read_text(encoding="utf-8")
    detail_html = Path("tests/resources/html/rightmove.html").read_text(encoding="utf-8")

    crawler = RightmoveCrawlerAgent(
        config={
            "id": "rightmove_uk",
            "base_url": "https://www.rightmove.co.uk",
            "rate_limit": {"period_seconds": 0},
        },
        compliance_manager=DummyCompliance(),
    )
    crawler.scrape_client.snapshot_service.save_snapshot = lambda **kwargs: None

    def fake_fetch_html(url, timeout_s=30.0, **_kwargs):
        if "find.html" in url:
            return search_html
        if "/properties/12345678" in url:
            return detail_html
        return None

    def fake_fetch_html_batch(urls, **_kwargs):
        results = []
        for url in urls:
            html = detail_html if "/properties/12345678" in url else fake_fetch_html(url)
            results.append(FetchResult(url=url, html=html))
        return results

    crawler.scrape_client.fetch_html = fake_fetch_html
    crawler.scrape_client.fetch_html_batch = fake_fetch_html_batch

    # Act
    result = crawler.run({"start_url": "https://www.rightmove.co.uk/property-for-sale/find.html?index=0"})

    # Assert (crawler boundary)
    assert result.status == "success"
    assert result.data
    raw = result.data[0]
    assert_required_fields(
        raw,
        ["source_id", "external_id", "url", "raw_data", "fetched_at"],
        context="rightmove:crawler_output",
    )
    assert raw.raw_data.get("html_snippet")

    # Act
    normalizer = RightmoveNormalizerAgent()
    normalized = normalizer.run({"raw_listings": result.data})

    # Assert (normalizer boundary)
    assert normalized.status == "success"
    assert normalized.data
    canonical = normalized.data[0]
    assert_required_fields(canonical, CANONICAL_LISTING_REQUIRED_FIELDS, context="rightmove:normalized")
    assert canonical.location is not None
    assert canonical.location.city
