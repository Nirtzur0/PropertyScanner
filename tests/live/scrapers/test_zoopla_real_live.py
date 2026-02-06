
import pytest
import logging
from src.listings.agents.crawlers.uk.zoopla import ZooplaCrawlerAgent
from src.platform.utils.compliance import ComplianceManager

@pytest.mark.live
@pytest.mark.network
def test_live_crawl__zoopla__returns_listings_or_skips_when_blocked():
    """
    Test real network call to Zoopla.co.uk search.
    Note: Highly likely to be blocked (403).
    """
    compliance = ComplianceManager(user_agent="PropertyScanner/Test/1.0")
    config = {
        "base_url": "https://www.zoopla.co.uk",
        "rate_limit": {"period_seconds": 3},
        "id": "zoopla",
        "prefer_browser": True
    }
    
    crawler = ZooplaCrawlerAgent(config=config, compliance_manager=compliance)
    
    payload = {
        "search_path": "/for-sale/property/london/?q=London&results_sort=newest_listings&search_source=home",
        "max_pages": 1,
    }
    
    response = crawler.run(payload)
    
    if response.status == "failure":
        error_msg = str(response.errors)
        if "403" in error_msg or "fetch_failed" in error_msg:
             logging.warning(f"Zoopla blocked/failed as expected: {error_msg}")
             pytest.skip("Zoopla blocked by anti-bot (403)")
        else:
             pytest.fail(f"Zoopla failed with unexpected errors: {response.errors}")

    assert len(response.data) > 0 or response.status == "success"
