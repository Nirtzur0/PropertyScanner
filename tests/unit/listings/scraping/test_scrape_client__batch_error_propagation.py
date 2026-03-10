from __future__ import annotations

from src.listings.scraping.browser_engine import BrowserFetchResult
from src.listings.scraping.client import ScrapeClient
from src.platform.utils.compliance import ComplianceDecision


class DummyCompliance:
    def check_and_wait(self, url: str, rate_limit_seconds: float = 1.0) -> bool:
        return True

    def assess_url(self, url: str, rate_limit_seconds: float = 1.0) -> ComplianceDecision:
        return ComplianceDecision(allowed=True)


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


def test_fetch_html_batch__maps_policy_blocked_preflight_reason_without_fallback(monkeypatch) -> None:
    client = ScrapeClient(
        source_id="idealista",
        base_url="https://example.com",
        compliance_manager=DummyCompliance(),
        user_agent="PropertyScanner/Test/1.0",
        rate_limit_seconds=0.0,
    )

    async def fake_fetch_many(urls, **kwargs):
        preflight = kwargs["preflight"]
        allowed = await preflight(urls[0])
        return [
            BrowserFetchResult(
                url=urls[0],
                html=None,
                error="blocked:preflight" if not allowed else None,
            ),
        ]

    fallback_calls: list[str] = []

    def fake_fetch_html(url: str, **_kwargs):
        fallback_calls.append(url)
        return None

    def fake_assess_url(url: str, rate_limit_seconds: float = 1.0) -> ComplianceDecision:
        return ComplianceDecision(allowed=False, reason="robots_fetch_denied")

    monkeypatch.setattr(client.browser_engine, "fetch_many", fake_fetch_many)
    monkeypatch.setattr(client.compliance_manager, "assess_url", fake_assess_url)
    monkeypatch.setattr(client, "fetch_html", fake_fetch_html)
    monkeypatch.setattr(client, "_filter_seen_urls", lambda urls: urls)

    results = client.fetch_html_batch(
        ["https://example.com/listing"],
        retries=1,
        timeout_s=5.0,
    )

    assert fallback_calls == []
    assert results[0].html is None
    assert results[0].error == "policy_blocked:robots_fetch_denied:https://example.com/listing"
