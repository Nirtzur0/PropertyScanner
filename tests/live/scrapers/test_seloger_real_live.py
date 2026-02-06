import pytest
from src.platform.utils.compliance import ComplianceManager
from src.listings.agents.crawlers.france.seloger import SeLogerCrawlerAgent
from src.listings.utils.seen_url_store import SeenUrlStore

@pytest.mark.live
@pytest.mark.network
def test_live_crawl__seloger__returns_listings_or_skips_when_blocked():
    """
    Test real network call to SeLoger search.
    Expected: Success (200 OK) + Listings found.
    """
    # Reset seen URLs
    SeenUrlStore().reset_mode("fetch:seloger")

    compliance = ComplianceManager(user_agent="PropertyScanner/Test/1.0")
    config = {
        "base_url": "https://www.seloger.com",
        "rate_limit": {"period_seconds": 2},
        "id": "seloger",
        "prefer_browser": True, 
        "browser_wait_s": 5.0,
        "maximize_stealth": True 
    }
    
    crawler = SeLogerCrawlerAgent(config=config, compliance=compliance)
    
    # Use a simpler search path
    payload = {
        "search_path": "/achat/immobilier/paris-75/?projects=2",
        "max_pages": 1,
        "max_listings": 3 
    }
    
    response = crawler.run(payload)
    
    assert response.status == "success"
    assert len(response.data) > 0, "Should find at least one listing on SeLoger real search"
    assert response.data[0].url.startswith("https://www.seloger.com")
    
    # Check for obvious block (DataDome)
    html = response.data[0].raw_data.get("html_snippet", "")
    assert "captcha-delivery.com" not in html, "Blocked by DataDome"
