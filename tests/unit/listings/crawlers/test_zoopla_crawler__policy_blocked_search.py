from __future__ import annotations

from src.listings.agents.crawlers.uk.zoopla import ZooplaCrawlerAgent
from src.platform.utils.compliance import ComplianceDecision


class BlockedCompliance:
    def assess_url(self, url: str, rate_limit_seconds: float = 1.0) -> ComplianceDecision:
        return ComplianceDecision(allowed=False, reason="robots_fetch_denied")


def test_zoopla_crawler__search_policy_block_surfaces_structured_status() -> None:
    crawler = ZooplaCrawlerAgent(
        config={
            "id": "zoopla_uk",
            "base_url": "https://www.zoopla.co.uk",
            "rate_limit": {"period_seconds": 0},
        },
        compliance_manager=BlockedCompliance(),
    )

    result = crawler.run({"start_url": "https://www.zoopla.co.uk/for-sale/property/london/"})

    assert result.status == "policy_blocked"
    assert result.errors == [
        "policy_blocked:robots_fetch_denied:https://www.zoopla.co.uk/for-sale/property/london/"
    ]
    assert result.metadata["search_pages_attempted"] == 1
    assert result.metadata["search_pages_succeeded"] == 0
    assert result.metadata["listing_urls_discovered"] == 0
