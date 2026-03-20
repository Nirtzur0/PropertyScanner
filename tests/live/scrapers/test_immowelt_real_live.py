import pytest
import os
from src.platform.utils.compliance import ComplianceManager
from src.listings.agents.crawlers.germany.immowelt import ImmoweltCrawlerAgent
from src.listings.utils.seen_url_store import SeenUrlStore

def _proxy_available() -> bool:
    return any(
        os.getenv(name, "").strip()
        for name in (
            "PROPERTY_SCANNER_IMMOWELT_DE_PROXY_URL",
            "PROPERTY_SCANNER_IMMOWELT_DE_REMOTE_BROWSER_WS",
            "PROPERTY_SCANNER_PROXY_URL",
            "PROPERTY_SCANNER_REMOTE_BROWSER_WS",
        )
    )


@pytest.mark.live
@pytest.mark.network
def test_live_crawl__immowelt__returns_listings_or_skips_when_blocked():
    """
    Test real network call to Immowelt search.
    Expected: Success (200 OK) + Listings found.
    """
    if not _proxy_available():
        pytest.skip("Immowelt live crawl requires proxy or remote browser configuration")
    # Reset seen URLs
    SeenUrlStore().reset_mode("fetch:immowelt")

    compliance = ComplianceManager(user_agent="PropertyScanner/Test/1.0")
    config = {
        "base_url": "https://www.immowelt.de",
        "rate_limit": {"period_seconds": 2},
        "id": "immowelt",
        "prefer_browser": True, 
        "browser_wait_s": 5.0,
        "maximize_stealth": True,
        "browser_config": {"proxy_required": True},
    }
    
    crawler = ImmoweltCrawlerAgent(config=config, compliance=compliance)
    
    # Use a broad search path
    payload = {
        "search_path": "/liste/berlin/kaufen",
        "max_pages": 1,
        "max_listings": 3 
    }
    
    response = crawler.run(payload)
    
    if response.status in {"blocked", "policy_blocked", "fetch_failed"}:
        pytest.skip(f"Immowelt blocked under current live conditions: {response.errors}")
    assert response.status == "success"
    assert len(response.data) > 0, "Should find at least one listing on Immowelt real search"
    assert response.data[0].url.startswith("https://www.immowelt.de")
    
    # Check for obvious block (DataDome)
    html = response.data[0].raw_data.get("html_snippet", "")
    assert "captcha-delivery.com" not in html, "Blocked by DataDome"
