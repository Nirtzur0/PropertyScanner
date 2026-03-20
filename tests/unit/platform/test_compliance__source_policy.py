from __future__ import annotations

import urllib.robotparser

from src.platform.utils.compliance import ComplianceManager


def _parser_with_error(reason: str) -> urllib.robotparser.RobotFileParser:
    parser = urllib.robotparser.RobotFileParser()
    setattr(parser, "_property_scanner_error_reason", reason)
    return parser


def test_assess_url__robots_fetch_denied_with_allowed_path_policy__allows_request(monkeypatch) -> None:
    manager = ComplianceManager(
        user_agent="PropertyScanner/Test/1.0",
        source_policy={"allowed_paths": ["/for-sale"], "disallowed_paths": ["/login"]},
    )
    monkeypatch.setattr(manager.rate_limiter, "wait_for_slot", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        manager.robots_validator,
        "_get_parser",
        lambda domain, scheme, policy: _parser_with_error("robots_fetch_denied"),
    )

    decision = manager.assess_url(
        "https://www.zoopla.co.uk/for-sale/property/london/",
        rate_limit_seconds=0.0,
    )

    assert decision.allowed is True
    assert decision.reason == "source_policy_fallback:robots_fetch_denied"


def test_assess_url__robots_fetch_failed_without_allowlist__blocks_request(monkeypatch) -> None:
    manager = ComplianceManager(user_agent="PropertyScanner/Test/1.0")
    monkeypatch.setattr(manager.rate_limiter, "wait_for_slot", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        manager.robots_validator,
        "_get_parser",
        lambda domain, scheme, policy: _parser_with_error("robots_fetch_failed"),
    )

    decision = manager.assess_url(
        "https://blocked.example.com/listings",
        rate_limit_seconds=0.0,
    )

    assert decision.allowed is False
    assert decision.reason == "robots_fetch_failed"


def test_assess_url__disallowed_path_blocks_even_when_allowlist_exists(monkeypatch) -> None:
    manager = ComplianceManager(
        user_agent="PropertyScanner/Test/1.0",
        source_policy={"allowed_paths": ["/for-sale"], "disallowed_paths": ["/login"]},
    )
    monkeypatch.setattr(manager.rate_limiter, "wait_for_slot", lambda *args, **kwargs: None)

    decision = manager.assess_url(
        "https://www.zoopla.co.uk/login",
        rate_limit_seconds=0.0,
    )

    assert decision.allowed is False
    assert decision.reason == "config_disallowed_path"
