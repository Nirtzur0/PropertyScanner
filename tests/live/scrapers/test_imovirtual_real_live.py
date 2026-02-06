
import pytest
import logging
from src.listings.agents.crawlers.portugal.imovirtual import ImovirtualCrawlerAgent
from src.platform.utils.compliance import ComplianceManager

@pytest.mark.live
@pytest.mark.network
def test_live_crawl__imovirtual__returns_listings_or_skips_when_blocked():
    """
    Test real network call to Imovirtual search.
    Expected: Success (200 OK) + Listings found.
    """
    compliance = ComplianceManager(user_agent="PropertyScanner/Test/1.0")
    config = {
        "base_url": "https://www.imovirtual.com",
        "rate_limit": {"period_seconds": 2},
        "id": "imovirtual_pt",
        "prefer_browser": False,
        "prefer_playwright": True
    }
    
    crawler = ImovirtualCrawlerAgent(config=config, compliance=compliance)
    
    # Use a broad search path
    payload = {
        "search_path": "/comprar/apartamento/lisboa/",
        "max_pages": 1,
        "max_listings": 3 # limit to avoid spamming
    }
    
    response = crawler.run(payload)
    
    assert response.status == "success"
    assert len(response.data) > 0, "Should find at least one listing on Imovirtual real search"
    assert response.data[0].url.startswith("https://www.imovirtual.com")
    assert response.data[0].raw_data.get("html_snippet") is not None

    # Normalization Check
    from src.listings.agents.processors.imovirtual import ImovirtualNormalizerAgent
    from src.platform.domain.schema import PropertyType
    
    normalizer = ImovirtualNormalizerAgent()
    norm_response = normalizer.run({"raw_listings": response.data})
    
    assert norm_response.status == "success"
    assert len(norm_response.data) > 0
    
    first = norm_response.data[0]
    logging.info(f"Normalized listing: {first}")
    
    assert first.source_id == "imovirtual"
    assert first.price > 0, f"Price should be extracted, got {first.price}"
    assert first.title, "Title should be extracted"
    assert str(first.url) == response.data[0].url
