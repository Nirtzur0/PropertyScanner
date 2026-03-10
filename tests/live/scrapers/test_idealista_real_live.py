import pytest
from src.platform.utils.compliance import ComplianceManager
from src.listings.agents.crawlers.spain.idealista import IdealistaCrawlerAgent
from src.listings.utils.seen_url_store import SeenUrlStore

@pytest.mark.live
@pytest.mark.network
def test_live_crawl__idealista__returns_listings_or_skips_when_blocked():
    """
    Test real network call to Idealista search.
    Expected: Success (200 OK) + Listings found.
    """
    # Reset seen URLs
    SeenUrlStore().reset_mode("fetch:idealista")

    compliance = ComplianceManager(user_agent="PropertyScanner/Test/1.0")
    config = {
        "base_url": "https://www.idealista.com",
        "rate_limit": {"period_seconds": 2},
        "id": "idealista",
        "prefer_browser": True, # Essential for anti-bot
        "browser_wait_s": 5.0,
        "maximize_stealth": True 
    }
    
    crawler = IdealistaCrawlerAgent(config=config, compliance_manager=compliance)
    
    # Use a broad search path
    payload = {
        "search_path": "/venta-viviendas/madrid/centro/",
        "max_pages": 1,
        "max_listings": 3 # Limit to avoid excessive crawling
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
    assert len(response.data) > 0, "Should find at least one listing on Idealista real search"
    assert response.data[0].url.startswith("https://www.idealista.com")
    
    # Check for obvious block
    html = response.data[0].raw_data.get("html_snippet", "")
    assert "captcha-delivery.com" not in html, "Blocked by DataDome/Anti-bot"
