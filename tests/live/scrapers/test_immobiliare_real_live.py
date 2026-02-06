import pytest
from src.platform.utils.compliance import ComplianceManager
from src.listings.agents.crawlers.italy.immobiliare import ImmobiliareCrawlerAgent

@pytest.mark.live
@pytest.mark.network
def test_immobiliare_real_search():
    """
    Test real network call to Immobiliare.it search.
    Expected: Success (200 OK) + Listings found.
    """
    compliance = ComplianceManager(user_agent="PropertyScanner/Test/1.0")
    config = {
        "base_url": "https://www.immobiliare.it",
        "rate_limit": {"period_seconds": 2},
        "id": "immobiliare_it",
        "prefer_browser": True, # Essential for DataDome
        "browser_wait_s": 5.0
    }
    
    crawler = ImmobiliareCrawlerAgent(config=config, compliance_manager=compliance)
    
    # Use a broad search path
    payload = {
        "city": "milano",
        "max_pages": 1,
        "max_listings": 3 # Limit to avoid excessive crawling
    }
    
    response = crawler.run(payload)
    
    assert response.status == "success"
    assert len(response.data) > 0, "Should find at least one listing on Immobiliare real search"
    assert response.data[0].url.startswith("https://www.immobiliare.it")
    assert response.data[0].raw_data.get("html_snippet") is not None
    
    # Simple check for DataDome block in content
    html = response.data[0].raw_data["html_snippet"]
    assert "captcha-delivery.com" not in html, "Blocked by DataDome"
