from __future__ import annotations

from src.listings.scraping.browser_engine import BrowserEngineConfig


def test_browser_engine_config__stealth_alias_maps_to_maximize_stealth() -> None:
    config = BrowserEngineConfig.from_dict(
        {"stealth": False},
        user_agent="PropertyScanner/Test/1.0",
        headless=True,
        wait_s=5.0,
        max_concurrency=2,
    )

    assert config.maximize_stealth is False


def test_browser_engine_config__proxy_fields_are_preserved() -> None:
    config = BrowserEngineConfig.from_dict(
        {
            "context_proxy": "http://proxy.local:9000",
            "context_proxy_bypass": "localhost",
            "remote_ws_address": "wss://browser.local/session",
        },
        user_agent="PropertyScanner/Test/1.0",
        headless=True,
        wait_s=5.0,
        max_concurrency=2,
    )

    assert config.context_proxy == "http://proxy.local:9000"
    assert config.context_proxy_bypass == "localhost"
    assert config.remote_ws_address == "wss://browser.local/session"
