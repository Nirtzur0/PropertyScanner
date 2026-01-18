
import pytest
import logging
from src.listings.agents.crawlers.spain.idealista import IdealistaCrawlerAgent
from src.platform.utils.compliance import ComplianceManager

@pytest.mark.integration
def test_idealista_real_search():
    """
    Test real network call to Idealista.com search.
    Note: Highly likely to be blocked (403).
    """
    compliance = ComplianceManager(user_agent="PropertyScanner/Test/1.0")
    config = {
        "base_url": "https://www.idealista.com",
        "rate_limit": {"period_seconds": 3},
        "id": "idealista",
        "prefer_browser": True
    }
    
    crawler = IdealistaCrawlerAgent(config=config, compliance_manager=compliance)
    
    payload = {
        "search_path": "/venta-viviendas/madrid-madrid/",
        "max_pages": 1,
    }
    
    response = crawler.run(payload)
    
    if response.status == "failure":
        error_msg = str(response.errors)
        if "403" in error_msg or "fetch_failed" in error_msg:
            logging.warning(f"Idealista blocked/failed as expected: {error_msg}")
            pytest.skip("Idealista blocked by anti-bot (403)")
        else:
            pytest.fail(f"Idealista failed with unexpected errors: {response.errors}")

    assert len(response.data) > 0 or response.status == "success"
