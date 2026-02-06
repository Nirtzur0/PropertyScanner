
import pytest
import logging
from src.listings.agents.crawlers.uk.rightmove import RightmoveCrawlerAgent
from src.platform.utils.compliance import ComplianceManager

@pytest.mark.live
@pytest.mark.network
def test_rightmove_real_search():
    """
    Test real network call to Rightmove.co.uk search.
    Note: Uses default config (Pydoll preferred) to avoid hangs.
    """
    compliance = ComplianceManager(user_agent="PropertyScanner/Test/1.0")
    # Default config uses prefer_browser=True, enable_playwright=False (fixed default)
    config = {
        "base_url": "https://www.rightmove.co.uk",
        "rate_limit": {"period_seconds": 3},
        "id": "rightmove_uk",
    }
    
    crawler = RightmoveCrawlerAgent(config=config, compliance_manager=compliance)
    
    payload = {
        "start_url": "https://www.rightmove.co.uk/property-for-sale/find.html?searchType=SALE&locationIdentifier=REGION%5E87490&insId=1",
        "max_pages": 1,
        "max_listings": 1
    }
    
    response = crawler.run(payload)
    
    if response.status == "failure":
        error_msg = str(response.errors)
        # Rightmove blocks often result in empty listings or fetch errors
        if "no_listings_found" in error_msg or "fetch_failed" in error_msg:
             logging.warning(f"Rightmove blocked/failed as expected: {error_msg}")
             pytest.skip("Rightmove blocked/empty (likely 403 or captcha)")
        else:
             pytest.fail(f"Rightmove failed with unexpected errors: {response.errors}")

    assert len(response.data) > 0 or response.status == "success"
