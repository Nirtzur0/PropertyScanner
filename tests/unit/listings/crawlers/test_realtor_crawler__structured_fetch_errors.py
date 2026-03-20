from __future__ import annotations

from src.listings.agents.crawlers.usa.realtor import RealtorCrawlerAgent
from src.platform.utils.compliance import ComplianceDecision


class AllowedCompliance:
    def assess_url(self, url: str, rate_limit_seconds: float = 1.0) -> ComplianceDecision:
        return ComplianceDecision(allowed=True)


def test_realtor_crawler__search_fetch_failure_surfaces_structured_status() -> None:
    crawler = RealtorCrawlerAgent(
        config={
            "id": "realtor_us",
            "base_url": "https://www.realtor.com",
            "rate_limit": {"period_seconds": 0},
        },
        compliance=AllowedCompliance(),
    )
    crawler.scrape_client.fetch_html = lambda url, **_kwargs: None

    result = crawler.run({"search_path": "/realestateandhomes-search/San-Francisco_CA"})

    assert result.status == "fetch_failed"
    assert result.errors == [
        "fetch_failed:https://www.realtor.com/realestateandhomes-search/San-Francisco_CA"
    ]
    assert result.metadata["search_pages_attempted"] == 1
    assert result.metadata["search_pages_succeeded"] == 0
    assert result.metadata["listing_urls_discovered"] == 0


def test_realtor_crawler__missing_required_proxy_surfaces_structured_status(monkeypatch) -> None:
    monkeypatch.delenv("PROPERTY_SCANNER_PROXY_URL", raising=False)
    monkeypatch.delenv("PROPERTY_SCANNER_REMOTE_BROWSER_WS", raising=False)
    monkeypatch.delenv("PROPERTY_SCANNER_REALTOR_US_PROXY_URL", raising=False)
    monkeypatch.delenv("PROPERTY_SCANNER_REALTOR_US_REMOTE_BROWSER_WS", raising=False)

    crawler = RealtorCrawlerAgent(
        config={
            "id": "realtor_us",
            "base_url": "https://www.realtor.com",
            "rate_limit": {"period_seconds": 0},
            "browser_config": {"proxy_required": True},
        },
        compliance=AllowedCompliance(),
    )

    result = crawler.run({"search_path": "/realestateandhomes-search/San-Francisco_CA"})

    assert result.status == "proxy_required"
    assert result.errors == ["proxy_required:realtor_us"]
    assert result.metadata["proxy_required"] is True
