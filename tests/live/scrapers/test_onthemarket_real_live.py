
import pytest
import logging
from src.listings.agents.crawlers.uk.onthemarket import OnTheMarketCrawlerAgent
from src.platform.utils.compliance import ComplianceManager

from src.listings.utils.seen_url_store import SeenUrlStore

@pytest.mark.live
@pytest.mark.network
def test_live_crawl__onthemarket__returns_listings_or_skips_when_blocked():
    """
    Test real network call to OnTheMarket search.
    Expected: Success (200 OK) + Listings found.
    """
    # Reset seen URLs so we can re-run this test repeatedly
    SeenUrlStore().reset_mode("fetch:onthemarket")

    compliance = ComplianceManager(user_agent="PropertyScanner/Test/1.0")
    config = {
        "base_url": "https://www.onthemarket.com",
        "rate_limit": {"period_seconds": 2},
        "id": "onthemarket",
        "prefer_browser": False,
        "prefer_playwright": True
    }
    
    crawler = OnTheMarketCrawlerAgent(config=config, compliance=compliance)
    
    # Use a broad search path
    payload = {
        "search_path": "/for-sale/property/london/",
        "max_pages": 1,
        "max_listings": 3
    }
    
    response = crawler.run(payload)

    if response.status in {"blocked", "policy_blocked", "fetch_failed", "no_listings_found"}:
        assert response.errors
        assert any(
            error.startswith("policy_blocked:") or error.startswith("blocked:") or error.startswith("fetch_failed:")
            for error in response.errors
        )
        return

    assert response.status == "success"
    assert len(response.data) > 0, "Should find at least one listing on OnTheMarket real search"
    assert response.data[0].url.startswith("https://www.onthemarket.com")
    assert response.data[0].raw_data.get("html_snippet") is not None

    # Normalization Check
    from src.listings.agents.processors.onthemarket import OnTheMarketNormalizerAgent
    normalizer = OnTheMarketNormalizerAgent()
    norm_response = normalizer.run({"raw_listings": response.data})
    assert norm_response.status == "success"
    assert len(norm_response.data) > 0
    first = norm_response.data[0]
    logging.info(f"Normalized listing: {first}")
    assert first.price > 0
    assert first.title
