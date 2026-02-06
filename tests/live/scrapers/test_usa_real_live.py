import pytest
from src.platform.utils.compliance import ComplianceManager
from src.listings.agents.crawlers.usa.realtor import RealtorCrawlerAgent
from src.listings.agents.crawlers.usa.redfin import RedfinCrawlerAgent
from src.listings.agents.crawlers.usa.homes import HomesCrawlerAgent
from src.listings.utils.seen_url_store import SeenUrlStore

@pytest.fixture
def compliance():
    return ComplianceManager(user_agent="PropertyScanner/Test/1.0")

@pytest.mark.live
@pytest.mark.network
def test_live_crawl__realtor__returns_listings_or_skips_when_blocked(compliance):
    """Test Realtor.com real network call."""
    SeenUrlStore().reset_mode("fetch:realtor")
    config = {
        "base_url": "https://www.realtor.com",
        "rate_limit": {"period_seconds": 2},
        "id": "realtor",
        "prefer_browser": True,
        "browser_wait_s": 5.0,
        "maximize_stealth": True
    }
    crawler = RealtorCrawlerAgent(config=config, compliance=compliance)
    response = crawler.run({
        "search_path": "/realestateandhomes-search/San-Francisco_CA",
        "max_pages": 1, 
        "max_listings": 1
    })
    
    # Assert success and NOT blocked
    assert response.status == "success"
    if response.data:
        html = response.data[0].raw_data.get("html_snippet", "")
        assert "captcha" not in html.lower(), "Realtor blocked"
        assert "block" not in html.lower(), "Realtor blocked"

@pytest.mark.live
@pytest.mark.network
def test_live_crawl__redfin__returns_listings_or_skips_when_blocked(compliance):
    """Test Redfin.com real network call (Expect Success)."""
    SeenUrlStore().reset_mode("fetch:redfin")
    config = {
        "base_url": "https://www.redfin.com",
        "rate_limit": {"period_seconds": 2},
        "id": "redfin",
        "prefer_browser": True,
        "browser_wait_s": 5.0,
        "maximize_stealth": True
    }
    crawler = RedfinCrawlerAgent(config=config, compliance=compliance)
    response = crawler.run({
        "search_path": "/city/17151/CA/San-Francisco",
        "max_pages": 1,
        "max_listings": 1
    })
    
    assert response.status == "success"
    assert len(response.data) > 0
    # Redfin often returns 200 but with a captcha, checking content
    html = response.data[0].raw_data.get("html_snippet", "")
    assert "captcha" not in html.lower(), "Redfin blocked"

@pytest.mark.live
@pytest.mark.network
def test_live_crawl__homes__returns_listings_or_skips_when_blocked(compliance):
    """Test Homes.com real network call."""
    SeenUrlStore().reset_mode("fetch:homes")
    config = {
        "base_url": "https://www.homes.com",
        "rate_limit": {"period_seconds": 2},
        "id": "homes",
        "prefer_browser": True,
        "browser_wait_s": 5.0,
        "maximize_stealth": True
    }
    crawler = HomesCrawlerAgent(config=config, compliance=compliance)
    response = crawler.run({
        "search_path": "/san-francisco-ca/",
        "max_pages": 1,
        "max_listings": 1
    })
    
    assert response.status == "success"
    if response.data:
         html = response.data[0].raw_data.get("html_snippet", "")
         assert "captcha" not in html.lower(), "Homes blocked"
