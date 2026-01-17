import sys
from pathlib import Path
from typing import Optional


_ROOT_DIR = Path(__file__).resolve().parents[3]
_VENDOR_DIR = _ROOT_DIR / "third_party" / "stealth_requests"

if _VENDOR_DIR.exists():
    sys.path.insert(0, str(_VENDOR_DIR))

try:
    import stealth_requests
except Exception as exc:  # pragma: no cover - import-time failure
    raise ImportError(
        "stealth_requests not available. Clone https://github.com/jpjacobpadilla/Stealth-Requests "
        "into third_party/stealth_requests."
    ) from exc


def create_session(user_agent: Optional[str] = None, **kwargs):
    headers = kwargs.pop("headers", {})
    if user_agent:
        headers["User-Agent"] = user_agent
    return stealth_requests.StealthSession(headers=headers, **kwargs)


def request_get(session, url: str, **kwargs):
    try:
        return session.get(url, **kwargs)
    except TypeError:
        if "impersonate" in kwargs:
            kwargs = dict(kwargs)
            kwargs.pop("impersonate", None)
            return session.get(url, **kwargs)
        raise
