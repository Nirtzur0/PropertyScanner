import time
import urllib.robotparser
import urllib.request
import ssl
from functools import lru_cache
from urllib.parse import urlparse
from threading import Lock
from typing import Dict, Iterable, Optional, Callable
from dataclasses import dataclass
import structlog

logger = structlog.get_logger()


@dataclass(frozen=True)
class ComplianceDecision:
    allowed: bool
    reason: Optional[str] = None


@dataclass(frozen=True)
class CompliancePolicy:
    robots_txt_url: Optional[str] = None
    allowed_paths: tuple[str, ...] = ()
    disallowed_paths: tuple[str, ...] = ()

    @classmethod
    def from_payload(cls, payload: object) -> "CompliancePolicy":
        if payload is None:
            return cls()
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump()
        if not isinstance(payload, dict):
            return cls()
        return cls(
            robots_txt_url=str(payload.get("robots_txt_url") or "").strip() or None,
            allowed_paths=tuple(_normalize_policy_paths(payload.get("allowed_paths") or ())),
            disallowed_paths=tuple(_normalize_policy_paths(payload.get("disallowed_paths") or ())),
        )

    def is_empty(self) -> bool:
        return not (self.robots_txt_url or self.allowed_paths or self.disallowed_paths)


def _normalize_policy_paths(paths: Iterable[object]) -> list[str]:
    normalized: list[str] = []
    for raw in paths:
        value = str(raw or "").strip()
        if not value:
            continue
        if not value.startswith("/"):
            value = f"/{value}"
        normalized.append(value.rstrip("/") or "/")
    return normalized


def _path_matches(path: str, prefixes: Iterable[str]) -> bool:
    normalized_path = (path or "/").rstrip("/") or "/"
    for prefix in prefixes:
        normalized_prefix = (str(prefix or "").rstrip("/") or "/")
        if normalized_prefix == "/":
            return True
        if normalized_path == normalized_prefix or normalized_path.startswith(f"{normalized_prefix}/"):
            return True
    return False


def _merge_policies(left: CompliancePolicy, right: CompliancePolicy) -> CompliancePolicy:
    def unique(values: Iterable[str]) -> tuple[str, ...]:
        seen: list[str] = []
        for value in values:
            if value not in seen:
                seen.append(value)
        return tuple(seen)

    return CompliancePolicy(
        robots_txt_url=left.robots_txt_url or right.robots_txt_url,
        allowed_paths=unique((*left.allowed_paths, *right.allowed_paths)),
        disallowed_paths=unique((*left.disallowed_paths, *right.disallowed_paths)),
    )


@lru_cache(maxsize=1)
def _domain_policy_cache() -> Dict[str, CompliancePolicy]:
    try:
        from src.platform.utils.config import load_app_config_safe

        app_config = load_app_config_safe()
    except Exception:
        return {}

    policies: Dict[str, CompliancePolicy] = {}
    for source in getattr(app_config.sources, "sources", []) or []:
        base_url = str(getattr(source, "base_url", "") or "").strip()
        if not base_url:
            continue
        domain = urlparse(base_url).netloc.lower()
        if not domain:
            continue
        policy = CompliancePolicy.from_payload(getattr(source, "compliance", None))
        if policy.is_empty():
            continue
        existing = policies.get(domain)
        policies[domain] = _merge_policies(existing, policy) if existing else policy
    return policies


def resolve_compliance_policy(url: str, explicit_policy: object = None) -> CompliancePolicy:
    policy = CompliancePolicy.from_payload(explicit_policy)
    if not policy.is_empty():
        return policy
    domain = urlparse(url).netloc.lower()
    if not domain:
        return policy
    return _domain_policy_cache().get(domain, policy)

class RateLimiter:
    """
    Thread-safe token bucket rate limiter per domain.
    """
    def __init__(self):
        self._locks: Dict[str, Lock] = {}
        self._last_request_time: Dict[str, float] = {}
        self._global_lock = Lock()

    def _get_lock(self, domain: str) -> Lock:
        with self._global_lock:
            if domain not in self._locks:
                self._locks[domain] = Lock()
            return self._locks[domain]

    def wait_for_slot(self, url: str, period_seconds: float = 1.0):
        domain = urlparse(url).netloc
        lock = self._get_lock(domain)
        
        with lock:
            now = time.time()
            last_request = self._last_request_time.get(domain, 0)
            elapsed = now - last_request
            
            if elapsed < period_seconds:
                sleep_time = period_seconds - elapsed
                logger.info("rate_limit_sleep", domain=domain, sleep_seconds=sleep_time)
                time.sleep(sleep_time)
            
            self._last_request_time[domain] = time.time()

class RobotsTxtValidator:
    """
    Validates URLs against robots.txt. Caches parsers per domain.
    """
    def __init__(self, user_agent: str = "*"):
        self.user_agent = user_agent
        self._parsers: Dict[str, urllib.robotparser.RobotFileParser] = {}
        self._lock = Lock()
        self._whitelist = [
            "photon.komoot.io",
            "nominatim.openstreetmap.org",
            "www.pisos.com", 
            "pisos.com" 
        ]

    def _path_policy_decision(self, path: str, policy: CompliancePolicy) -> Optional[ComplianceDecision]:
        if policy.disallowed_paths and _path_matches(path, policy.disallowed_paths):
            return ComplianceDecision(allowed=False, reason="config_disallowed_path")
        if policy.allowed_paths and not _path_matches(path, policy.allowed_paths):
            return ComplianceDecision(allowed=False, reason="config_path_not_allowed")
        return None

    def _get_parser(
        self,
        domain: str,
        scheme: str,
        *,
        policy: CompliancePolicy,
    ) -> urllib.robotparser.RobotFileParser:
        with self._lock:
            robots_url = policy.robots_txt_url or f"{scheme}://{domain}/robots.txt"
            cache_key = robots_url
            if cache_key in self._parsers:
                return self._parsers[cache_key]

            logger.info("fetching_robots_txt", url=robots_url)
            
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(robots_url)
            try:
                # SSL context to ignore certificate errors (e.g. self-signed or missing intermediate)
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                
                with urllib.request.urlopen(robots_url, timeout=10, context=ctx) as response:
                    data = response.read().decode("utf-8", errors="ignore")
                    rp.parse(data.splitlines())
            except Exception as e:
                logger.warning("robots_txt_fetch_failed", url=robots_url, error=str(e))
                error_text = str(e).lower()
                if "403" in error_text or "forbidden" in error_text:
                    setattr(rp, "_property_scanner_error_reason", "robots_fetch_denied")
                else:
                    setattr(rp, "_property_scanner_error_reason", "robots_fetch_failed")
                rp.disallow_all = True

            self._parsers[cache_key] = rp
            return rp

    def assess_fetch(self, url: str, *, explicit_policy: object = None) -> ComplianceDecision:
        parsed = urlparse(url)
        domain = parsed.netloc
        scheme = parsed.scheme
        path = parsed.path or "/"
        policy = resolve_compliance_policy(url, explicit_policy)
        
        if not domain or not scheme:
            return ComplianceDecision(allowed=False, reason="invalid_url")

        if domain in self._whitelist:
            logger.info("compliance_whitelist_allowed", domain=domain)
            return ComplianceDecision(allowed=True, reason="whitelist")

        path_decision = self._path_policy_decision(path, policy)
        if path_decision is not None:
            return path_decision

        rp = self._get_parser(domain, scheme, policy=policy)
        error_reason = getattr(rp, "_property_scanner_error_reason", None)
        if error_reason:
            if policy.allowed_paths and _path_matches(path, policy.allowed_paths):
                logger.info(
                    "robots_txt_fallback_to_source_policy",
                    domain=domain,
                    path=path,
                    reason=error_reason,
                )
                return ComplianceDecision(
                    allowed=True,
                    reason=f"source_policy_fallback:{error_reason}",
                )
            return ComplianceDecision(allowed=False, reason=str(error_reason))
        if not rp.can_fetch(self.user_agent, url):
            return ComplianceDecision(allowed=False, reason="robots_disallowed")
        return ComplianceDecision(allowed=True)

    def can_fetch(self, url: str) -> bool:
        return self.assess_fetch(url).allowed

class ComplianceManager:
    """
    Unified interface for compliance checks.
    """
    def __init__(
        self,
        user_agent: str,
        seen_check: Optional[Callable[[str], bool]] = None,
        *,
        enforce_robots: bool = True,
        source_policy: object = None,
    ):
        self.user_agent = user_agent
        self.rate_limiter = RateLimiter()
        self.robots_validator = RobotsTxtValidator(user_agent)
        self.seen_check = seen_check
        self.enforce_robots = enforce_robots
        self.source_policy = CompliancePolicy.from_payload(source_policy)

    def with_policy(self, source_policy: object = None) -> "ComplianceManager":
        policy = CompliancePolicy.from_payload(source_policy)
        return ComplianceManager(
            user_agent=self.user_agent,
            seen_check=self.seen_check,
            enforce_robots=self.enforce_robots,
            source_policy=policy if not policy.is_empty() else self.source_policy,
        )

    def check_and_wait(self, url: str, rate_limit_seconds: float = 1.0) -> bool:
        """
        Checks robots.txt and waits for rate limit.
        Returns True if safe to proceed, False if blocked by robots.txt.
        """
        return self.assess_url(url, rate_limit_seconds=rate_limit_seconds).allowed

    def assess_url(self, url: str, rate_limit_seconds: float = 1.0) -> ComplianceDecision:
        """
        Returns an explicit compliance decision and enforces rate limiting only when allowed.
        """
        if self.seen_check and self.seen_check(url):
            logger.info("skipped_seen_url", url=url)
            return ComplianceDecision(allowed=False, reason="seen_url")

        if self.enforce_robots:
            decision = self.robots_validator.assess_fetch(url, explicit_policy=self.source_policy)
            if not decision.allowed:
                logger.warning("blocked_by_robots_txt", url=url, reason=decision.reason)
                return decision
        
        self.rate_limiter.wait_for_slot(url, period_seconds=rate_limit_seconds)
        return ComplianceDecision(allowed=True, reason=decision.reason if self.enforce_robots else None)
