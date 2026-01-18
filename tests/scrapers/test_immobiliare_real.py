
import pytest
import logging
from src.listings.agents.crawlers.italy.immobiliare import ImmobiliareCrawlerAgent
from src.platform.utils.compliance import ComplianceManager

@pytest.mark.integration
def test_immobiliare_real_search():
    """
    Test real network call to Immobiliare.it search.
    Note: Highly likely to be blocked (403).
    """
    compliance = ComplianceManager(user_agent="PropertyScanner/Test/1.0")
    config = {
        "base_url": "https://www.immobiliare.it",
        "rate_limit": {"period_seconds": 3},
        "id": "immobiliare",
        "prefer_browser": True
    }
    
    crawler = ImmobiliareCrawlerAgent(config=config, compliance_manager=compliance)
    
    payload = {
        "search_path": "/vendita-case/roma/?criterio=rilevanza",
        "max_pages": 1,
    }
    
    response = crawler.run(payload)
    
    # We assert status, but acknowledge it might be failure due to blocking
    if response.status == "failure":
        error_msg = str(response.errors)
        if "403" in error_msg or "fetch_failed" in error_msg:
            logging.warning(f"Immobiliare blocked/failed as expected: {error_msg}")
            pytest.skip("Immobiliare blocked by anti-bot (403)")
        else:
            pytest.fail(f"Immobiliare failed with unexpected errors: {response.errors}")
            
    assert len(response.data) > 0 or response.status == "success"
