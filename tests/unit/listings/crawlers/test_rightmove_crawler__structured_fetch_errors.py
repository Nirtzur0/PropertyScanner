from __future__ import annotations

from pathlib import Path

from src.listings.agents.crawlers.uk.rightmove import RightmoveCrawlerAgent
from src.listings.scraping.client import FetchResult


class DummyCompliance:
    def check_and_wait(self, url: str, rate_limit_seconds: float = 1.0) -> bool:
        return True


def test_rightmove_crawler__detail_fetch_failures_surface_structured_errors() -> None:
    search_html = Path("tests/resources/html/rightmove_search.html").read_text(encoding="utf-8")

    crawler = RightmoveCrawlerAgent(
        config={
            "id": "rightmove_uk",
            "base_url": "https://www.rightmove.co.uk",
            "rate_limit": {"period_seconds": 0},
        },
        compliance_manager=DummyCompliance(),
    )
    crawler.scrape_client.snapshot_service.save_snapshot = lambda **kwargs: None
    crawler.scrape_client.fetch_html = lambda url, **_kwargs: search_html if "find.html" in url else None
    crawler.scrape_client.fetch_html_batch = lambda urls, **_kwargs: [
        FetchResult(
            url=urls[0],
            html=None,
            error="browser_task_failed:TimeoutError:detail-timeout",
        )
    ]

    result = crawler.run({"start_url": "https://www.rightmove.co.uk/property-for-sale/find.html?index=0"})

    assert result.status == "failure"
    assert result.data == []
    assert result.errors == ["browser_task_failed:TimeoutError:detail-timeout"]
