
import pytest
import logging
from src.listings.agents.crawlers.italy.casa_it import CasaItCrawlerAgent
from src.platform.utils.compliance import ComplianceManager
from src.listings.agents.processors.casa_it import CasaItNormalizerAgent

@pytest.mark.integration
def test_casait_real_search():
    """
    Test real network call to Casa.it search and normalization.
    """
    compliance = ComplianceManager(user_agent="PropertyScanner/Test/1.0")
    config = {
        "base_url": "https://www.casa.it",
        "rate_limit": {"period_seconds": 2},
        "id": "casa_it",
        "period_seconds": 5,
        "browser_wait_s": 5,
        "browser_config": {
            "headless": False, 
            "maximize_stealth": True
        }
    }
    
    crawler = CasaItCrawlerAgent(config=config, compliance=compliance)
    
    # Use a broad search path
    payload = {
        "search_path": "/vendita/residenziale/milano/",
        "max_pages": 1,
        "max_listings": 3
    }
    
    response = crawler.run(payload)
    
    assert response.status == "success"
    assert len(response.data) > 0
    assert response.data[0].url.startswith("https://www.casa.it")
    assert response.data[0].raw_data.get("html_snippet") is not None
    
    # Verify Normalization
    normalizer = CasaItNormalizerAgent()
    norm_res = normalizer.run({"raw_listings": response.data})
    
    assert norm_res.status == "success"
    assert len(norm_res.data) > 0
    
    first = norm_res.data[0]
    logging.info(f"Normalized CasaIt listing: {first}")
    
    assert first.source_id == "casa_it"
    assert first.price > 0
    assert first.title
