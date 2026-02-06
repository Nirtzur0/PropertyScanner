
import pytest
import logging
from src.listings.agents.crawlers.spain.pisos import PisosCrawlerAgent
from src.platform.utils.compliance import ComplianceManager

@pytest.mark.live
@pytest.mark.network
def test_live_crawl__pisos__returns_listings_or_skips_when_blocked():
    """
    Test real network call to Pisos.com search.
    Expected: Success (200 OK) + Listings found.
    """
    compliance = ComplianceManager(user_agent="PropertyScanner/Test/1.0")
    config = {
        "base_url": "https://www.pisos.com",
        "rate_limit": {"period_seconds": 2},
        "id": "pisos",
        "prefer_browser": False,
        "prefer_playwright": True
    }
    
    crawler = PisosCrawlerAgent(config=config, compliance_manager=compliance)
    
    # Use a broad search path that is likely to have results
    payload = {
        "search_path": "/venta/pisos-madrid_capital_centro/",
        "max_pages": 1,
    }
    
    response = crawler.run(payload)
    
    assert response.status == "success"
    assert len(response.data) > 0, "Should find at least one listing on Pisos real search"
    assert response.data[0].url.startswith("https://www.pisos.com")
    assert response.data[0].raw_data.get("html_snippet") is not None
