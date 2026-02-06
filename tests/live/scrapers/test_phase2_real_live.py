import pytest
import time
from src.listings.scraping.client import ScrapeClient
from src.platform.utils.compliance import ComplianceManager
from src.listings.utils.seen_url_store import SeenUrlStore

@pytest.fixture
def compliance():
    return ComplianceManager(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36")

@pytest.mark.live
@pytest.mark.network
def test_rightmove_real(compliance):
    """Test Rightmove (GB) blocking status."""
    client = ScrapeClient(
        source_id="rightmove_uk",
        base_url="https://www.rightmove.co.uk",
        compliance_manager=compliance,
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        rate_limit_seconds=2,
        browser_wait_s=5,
        browser_config={"headless": True, "stealth": True},
        seen_mode="test"
    )
    html = client.fetch_html("https://www.rightmove.co.uk/property-for-sale.html", timeout_s=45)
    
    assert html is not None, "Rightmove returned None (blocked/timeout)"
    lower_html = html.lower()
    assert "captcha" not in lower_html, "Rightmove blocked by CAPTCHA"
    assert "access denied" not in lower_html, "Rightmove blocked by Access Denied"
    assert "property-for-sale" in lower_html or "div" in lower_html, "Rightmove content suspicious"

@pytest.mark.live
@pytest.mark.network
def test_zoopla_real(compliance):
    """Test Zoopla (GB) blocking status."""
    client = ScrapeClient(
        source_id="zoopla_uk",
        base_url="https://www.zoopla.co.uk",
        compliance_manager=compliance,
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        rate_limit_seconds=2,
        browser_wait_s=5,
        browser_config={"headless": True, "stealth": True},
        seen_mode="test"
    )
    html = client.fetch_html("https://www.zoopla.co.uk/for-sale/property/london/", timeout_s=45)
    
    assert html is not None, "Zoopla returned None (blocked/timeout)"
    lower_html = html.lower()
    assert "captcha" not in lower_html, "Zoopla blocked by CAPTCHA"
    assert "cloudfare" not in lower_html, "Zoopla blocked by Cloudflare"

@pytest.mark.live
@pytest.mark.network
def test_daft_real(compliance):
    """Test Daft.ie (IE) blocking status."""
    client = ScrapeClient(
        source_id="daft_ie",
        base_url="https://www.daft.ie",
        compliance_manager=compliance,
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        rate_limit_seconds=2,
        browser_wait_s=5,
        browser_config={"headless": True, "stealth": True},
        seen_mode="test"
    )
    html = client.fetch_html("https://www.daft.ie/property-for-sale/ireland", timeout_s=45)
    
    assert html is not None, "Daft.ie returned None"
    lower_html = html.lower()
    assert "captcha" not in lower_html, "Daft.ie blocked by CAPTCHA"
    assert "datadome" not in lower_html, "Daft.ie blocked by DataDome"
    
@pytest.mark.live
@pytest.mark.network
def test_pararius_real(compliance):
    """Test Pararius (NL) blocking status."""
    client = ScrapeClient(
        source_id="pararius_nl",
        base_url="https://www.pararius.com",
        compliance_manager=compliance,
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        rate_limit_seconds=2,
        browser_wait_s=5,
        browser_config={"headless": True, "stealth": True},
        seen_mode="test"
    )
    # Use a simpler path to avoid 404s if 'nederland' isn't valid
    html = client.fetch_html("https://www.pararius.com/apartments/amsterdam", timeout_s=45)
    
    assert html is not None
    lower_html = html.lower()
    assert "captcha" not in lower_html
    assert "shield" not in lower_html

@pytest.mark.live
@pytest.mark.network
def test_sreality_real(compliance):
    """Test Sreality (CZ) blocking status."""
    client = ScrapeClient(
        source_id="sreality_cz",
        base_url="https://www.sreality.cz",
        compliance_manager=compliance,
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        rate_limit_seconds=2,
        browser_wait_s=5,
        browser_config={"headless": True, "stealth": True},
        seen_mode="test"
    )
    html = client.fetch_html("https://www.sreality.cz/en/search/for-sale/apartments", timeout_s=45)
    
    assert html is not None
    lower_html = html.lower()
    assert "captcha" not in lower_html

@pytest.mark.live
@pytest.mark.network
def test_otodom_real(compliance):
    """Test Otodom (PL) blocking status."""
    client = ScrapeClient(
        source_id="otodom_pl",
        base_url="https://www.otodom.pl",
        compliance_manager=compliance,
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        rate_limit_seconds=2,
        browser_wait_s=5,
        browser_config={"headless": True, "stealth": True},
        seen_mode="test"
    )
    html = client.fetch_html("https://www.otodom.pl/pl/wyniki/sprzedaz/mieszkanie/cala-polska", timeout_s=45)
    
    assert html is not None
    lower_html = html.lower()
    # Otodom uses Cloudflare often
    assert "challenge" not in lower_html, "Otodom blocked by Challenge"
    assert "captcha" not in lower_html
