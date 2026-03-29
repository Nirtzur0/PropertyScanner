"""Regression tests for compliance module fixes."""
from unittest.mock import MagicMock

from src.platform.utils.compliance import (
    ComplianceDecision,
    ComplianceManager,
    CompliancePolicy,
    RateLimiter,
    RobotsTxtValidator,
    _normalize_policy_paths,
    _path_matches,
    _merge_policies,
)


class TestComplianceDecision:
    def test_allowed(self):
        d = ComplianceDecision(allowed=True)
        assert d.allowed
        assert d.reason is None

    def test_blocked(self):
        d = ComplianceDecision(allowed=False, reason="robots_disallowed")
        assert not d.allowed
        assert d.reason == "robots_disallowed"


class TestNormalizePolicyPaths:
    def test_empty(self):
        assert _normalize_policy_paths([]) == []

    def test_strips_whitespace(self):
        assert _normalize_policy_paths(["  /foo  "]) == ["/foo"]

    def test_adds_leading_slash(self):
        assert _normalize_policy_paths(["foo"]) == ["/foo"]

    def test_strips_trailing_slash(self):
        assert _normalize_policy_paths(["/foo/"]) == ["/foo"]

    def test_root_stays_root(self):
        assert _normalize_policy_paths(["/"]) == ["/"]

    def test_skips_empty(self):
        assert _normalize_policy_paths(["", None, "  "]) == []


class TestPathMatches:
    def test_root_matches_all(self):
        assert _path_matches("/anything", ["/"])

    def test_exact_match(self):
        assert _path_matches("/foo", ["/foo"])

    def test_prefix_match(self):
        assert _path_matches("/foo/bar", ["/foo"])

    def test_no_match(self):
        assert not _path_matches("/bar", ["/foo"])

    def test_partial_no_match(self):
        assert not _path_matches("/foobar", ["/foo"])


class TestMergePolicies:
    def test_merge_deduplicates(self):
        left = CompliancePolicy(allowed_paths=("/a",), disallowed_paths=("/x",))
        right = CompliancePolicy(allowed_paths=("/a", "/b"), disallowed_paths=("/x", "/y"))
        result = _merge_policies(left, right)
        assert result.allowed_paths == ("/a", "/b")
        assert result.disallowed_paths == ("/x", "/y")

    def test_merge_uses_left_robots_url(self):
        left = CompliancePolicy(robots_txt_url="https://a.com/robots.txt")
        right = CompliancePolicy(robots_txt_url="https://b.com/robots.txt")
        assert _merge_policies(left, right).robots_txt_url == "https://a.com/robots.txt"


class TestCompliancePolicyFromPayload:
    def test_none(self):
        assert CompliancePolicy.from_payload(None).is_empty()

    def test_dict(self):
        p = CompliancePolicy.from_payload({
            "robots_txt_url": "https://x.com/robots.txt",
            "allowed_paths": ["/a"],
        })
        assert p.robots_txt_url == "https://x.com/robots.txt"
        assert p.allowed_paths == ("/a",)

    def test_non_dict(self):
        assert CompliancePolicy.from_payload("not a dict").is_empty()


class TestComplianceManagerEnforceRobotsFalse:
    """Regression: NameError when enforce_robots=False (decision variable undefined)."""

    def test_no_crash_when_robots_disabled(self):
        manager = ComplianceManager(
            user_agent="test-agent",
            enforce_robots=False,
        )
        decision = manager.assess_url("https://example.com/test", rate_limit_seconds=0.0)
        assert decision.allowed
        assert decision.reason is None

    def test_seen_url_still_blocked_when_robots_disabled(self):
        manager = ComplianceManager(
            user_agent="test-agent",
            seen_check=lambda url: True,
            enforce_robots=False,
        )
        decision = manager.assess_url("https://example.com/test", rate_limit_seconds=0.0)
        assert not decision.allowed
        assert decision.reason == "seen_url"


class TestRateLimiter:
    def test_first_request_no_wait(self):
        limiter = RateLimiter()
        # Should not raise or sleep excessively
        limiter.wait_for_slot("https://example.com/test", period_seconds=0.0)
