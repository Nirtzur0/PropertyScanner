import pytest
from src.platform.utils.compliance import ComplianceManager
from src.listings.agents.crawlers.germany.immowelt import ImmoweltCrawlerAgent
from src.listings.utils.seen_url_store import SeenUrlStore

@pytest.mark.live
@pytest.mark.network
def test_immowelt_real_search():
    """
    Test real network call to Immowelt search.
    Expected: Success (200 OK) + Listings found.
    """
    # Reset seen URLs
    SeenUrlStore().reset_mode("fetch:immowelt")

    compliance = ComplianceManager(user_agent="PropertyScanner/Test/1.0")
    config = {
        "base_url": "https://www.immowelt.de",
        "rate_limit": {"period_seconds": 2},
        "id": "immowelt",
        "prefer_browser": True, 
        "browser_wait_s": 5.0,
        "maximize_stealth": True 
    }
    
    crawler = ImmoweltCrawlerAgent(config=config, compliance=compliance)
    
    # Use a broad search path
    payload = {
        "search_path": "/liste/berlin/kaufen",
        "max_pages": 1,
        "max_listings": 3 
    }
    
    response = crawler.run(payload)
    
    assert response.status == "success"
    assert len(response.data) > 0, "Should find at least one listing on Immowelt real search"
    assert response.data[0].url.startswith("https://www.immowelt.de")
    
    # Check for obvious block (DataDome)
    html = response.data[0].raw_data.get("html_snippet", "")
    assert "captcha-delivery.com" not in html, "Blocked by DataDome"
