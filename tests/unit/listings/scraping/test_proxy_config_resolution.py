from __future__ import annotations

from src.listings.scraping.proxy_config import (
    browser_proxy_configured,
    browser_proxy_required,
    proxy_requirement_error,
    resolve_browser_runtime_config,
)


def test_proxy_config_resolution__global_envs_fill_missing_runtime_values(monkeypatch) -> None:
    monkeypatch.setenv("PROPERTY_SCANNER_PROXY_URL", "http://proxy.local:9000")
    monkeypatch.setenv("PROPERTY_SCANNER_PROXY_BYPASS", "localhost,127.0.0.1")
    monkeypatch.setenv("PROPERTY_SCANNER_REMOTE_BROWSER_WS", "wss://browser.local/session")

    resolved = resolve_browser_runtime_config("realtor_us", {"proxy_required": True})

    assert resolved["context_proxy"] == "http://proxy.local:9000"
    assert resolved["context_proxy_bypass"] == "localhost,127.0.0.1"
    assert resolved["remote_ws_address"] == "wss://browser.local/session"
    assert browser_proxy_required(resolved) is True
    assert browser_proxy_configured(resolved) is True


def test_proxy_config_resolution__source_specific_env_overrides_global(monkeypatch) -> None:
    monkeypatch.setenv("PROPERTY_SCANNER_PROXY_URL", "http://proxy.global:9000")
    monkeypatch.setenv("PROPERTY_SCANNER_REDFIN_US_PROXY_URL", "http://proxy.redfin:9443")

    resolved = resolve_browser_runtime_config("redfin_us", {"proxy_required": True})

    assert resolved["context_proxy"] == "http://proxy.redfin:9443"


def test_proxy_requirement_error__missing_proxy_on_required_source_returns_structured_reason(monkeypatch) -> None:
    monkeypatch.delenv("PROPERTY_SCANNER_PROXY_URL", raising=False)
    monkeypatch.delenv("PROPERTY_SCANNER_REMOTE_BROWSER_WS", raising=False)
    monkeypatch.delenv("PROPERTY_SCANNER_REALTOR_US_PROXY_URL", raising=False)
    monkeypatch.delenv("PROPERTY_SCANNER_REALTOR_US_REMOTE_BROWSER_WS", raising=False)

    resolved = resolve_browser_runtime_config("realtor_us", {"proxy_required": True})

    assert proxy_requirement_error("realtor_us", resolved) == "proxy_required:realtor_us"
