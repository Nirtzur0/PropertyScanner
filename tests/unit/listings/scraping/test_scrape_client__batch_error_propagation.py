from __future__ import annotations

from src.listings.scraping.browser_engine import BrowserFetchResult
from src.listings.scraping.client import ScrapeClient


class DummyCompliance:
    def check_and_wait(self, url: str, rate_limit_seconds: float = 1.0) -> bool:
        return True


def test_fetch_html_batch__preserves_structured_errors_and_retries_sequentially(monkeypatch) -> None:
    client = ScrapeClient(
        source_id="rightmove_uk",
        base_url="https://example.com",
        compliance_manager=DummyCompliance(),
        user_agent="PropertyScanner/Test/1.0",
        rate_limit_seconds=0.0,
    )

    async def fake_fetch_many(urls, **_kwargs):
        return [
            BrowserFetchResult(
                url=urls[0],
                html=None,
                error="browser_task_failed:TimeoutError:boom",
            ),
            BrowserFetchResult(
                url=urls[1],
                html=None,
                error="browser_task_failed:TimeoutError:still-boom",
            ),
        ]

    fallback_calls: list[str] = []

    def fake_fetch_html(url: str, **_kwargs):
        fallback_calls.append(url)
        if url.endswith("/recover"):
            return "<html>fallback</html>"
        return None

    monkeypatch.setattr(client.browser_engine, "fetch_many", fake_fetch_many)
    monkeypatch.setattr(client, "fetch_html", fake_fetch_html)
    monkeypatch.setattr(client, "_filter_seen_urls", lambda urls: urls)

    results = client.fetch_html_batch(
        ["https://example.com/recover", "https://example.com/fail"],
        retries=1,
        timeout_s=5.0,
    )

    assert fallback_calls == ["https://example.com/recover", "https://example.com/fail"]
    assert results[0].html == "<html>fallback</html>"
    assert results[0].error is None
    assert results[1].html is None
    assert results[1].error == "browser_task_failed:TimeoutError:still-boom"
