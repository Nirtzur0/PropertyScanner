import pytest
from src.platform.utils.compliance import ComplianceManager
from src.listings.agents.crawlers.netherlands.funda import FundaCrawlerAgent
from src.listings.utils.seen_url_store import SeenUrlStore

@pytest.mark.live
@pytest.mark.network
def test_live_crawl__funda__returns_listings_or_skips_when_blocked():
    """
    Test real network call to Funda search.
    Expected: Success (200 OK) + Listings found.
    """
    # Reset seen URLs
    SeenUrlStore().reset_mode("fetch:funda")

    compliance = ComplianceManager(user_agent="PropertyScanner/Test/1.0")
    config = {
        "base_url": "https://www.funda.nl",
        "rate_limit": {"period_seconds": 2},
        "id": "funda",
        "prefer_browser": True, 
        "browser_wait_s": 5.0,
        "maximize_stealth": True 
    }
    
    crawler = FundaCrawlerAgent(config=config, compliance=compliance)
    
    # Use a broad search path
    payload = {
        "search_path": "/koop/amsterdam/",
        "max_pages": 1,
        "max_listings": 3 # Limit to avoid excessive crawling
    }
    
    response = crawler.run(payload)
    
    assert response.status == "success"
    assert len(response.data) > 0, "Should find at least one listing on Funda real search"
    assert response.data[0].url.startswith("https://www.funda.nl")
    
    # Check for obvious block (Captcha title)
    html = response.data[0].raw_data.get("html_snippet", "")
    assert "Je bent bijna op de pagina" not in html, "Blocked by reCAPTCHA"
