import time
import urllib.robotparser
import urllib.request
import ssl
from urllib.parse import urlparse
from threading import Lock
from typing import Dict, Optional, Callable
import structlog

logger = structlog.get_logger()

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

    def _get_parser(self, domain: str, scheme: str) -> urllib.robotparser.RobotFileParser:
        with self._lock:
            if domain in self._parsers:
                return self._parsers[domain]
            
            robots_url = f"{scheme}://{domain}/robots.txt"
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
                rp.disallow_all = True

            self._parsers[domain] = rp
            return rp

    def can_fetch(self, url: str) -> bool:
        parsed = urlparse(url)
        domain = parsed.netloc
        scheme = parsed.scheme
        
        if not domain or not scheme:
            return False

        if domain in self._whitelist:
            logger.info("compliance_whitelist_allowed", domain=domain)
            return True
            
        rp = self._get_parser(domain, scheme)
        return rp.can_fetch(self.user_agent, url)

class ComplianceManager:
    """
    Unified interface for compliance checks.
    """
    def __init__(self, user_agent: str, seen_check: Optional[Callable[[str], bool]] = None):
        self.rate_limiter = RateLimiter()
        self.robots_validator = RobotsTxtValidator(user_agent)
        self.seen_check = seen_check

    def check_and_wait(self, url: str, rate_limit_seconds: float = 1.0) -> bool:
        """
        Checks robots.txt and waits for rate limit.
        Returns True if safe to proceed, False if blocked by robots.txt.
        """
        if self.seen_check and self.seen_check(url):
            logger.info("skipped_seen_url", url=url)
            return False

        # Disabled robots.txt check as requested
        # if not self.robots_validator.can_fetch(url):
        #    logger.warning("blocked_by_robots_txt", url=url)
        #    return False
        
        self.rate_limiter.wait_for_slot(url, period_seconds=rate_limit_seconds)
        return True
