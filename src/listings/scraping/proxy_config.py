from __future__ import annotations

import os
from typing import Any, Dict

from src.listings.source_ids import canonicalize_source_id


def _clean_env_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _source_env_prefix(source_id: str) -> str:
    canonical = canonicalize_source_id(source_id)
    sanitized = "".join(ch if ch.isalnum() else "_" for ch in canonical.upper())
    return f"PROPERTY_SCANNER_{sanitized}"


def _resolve_env_override(
    *,
    source_id: str,
    explicit_value: Any,
    suffix: str,
    global_name: str,
) -> str | None:
    explicit = _clean_env_value(explicit_value)
    if explicit is not None:
        return explicit

    source_specific = _clean_env_value(os.getenv(f"{_source_env_prefix(source_id)}_{suffix}"))
    if source_specific is not None:
        return source_specific

    return _clean_env_value(os.getenv(global_name))


def resolve_browser_runtime_config(source_id: str, browser_config: Dict[str, Any] | None) -> Dict[str, Any]:
    payload = dict(browser_config or {})
    payload["proxy_required"] = bool(payload.get("proxy_required", False))
    payload["context_proxy"] = _resolve_env_override(
        source_id=source_id,
        explicit_value=payload.get("context_proxy"),
        suffix="PROXY_URL",
        global_name="PROPERTY_SCANNER_PROXY_URL",
    )
    payload["context_proxy_bypass"] = _resolve_env_override(
        source_id=source_id,
        explicit_value=payload.get("context_proxy_bypass"),
        suffix="PROXY_BYPASS",
        global_name="PROPERTY_SCANNER_PROXY_BYPASS",
    )
    payload["remote_ws_address"] = _resolve_env_override(
        source_id=source_id,
        explicit_value=payload.get("remote_ws_address"),
        suffix="REMOTE_BROWSER_WS",
        global_name="PROPERTY_SCANNER_REMOTE_BROWSER_WS",
    )
    return payload


def browser_proxy_required(browser_config: Dict[str, Any] | None) -> bool:
    return bool((browser_config or {}).get("proxy_required", False))


def browser_proxy_configured(browser_config: Dict[str, Any] | None) -> bool:
    payload = browser_config or {}
    return bool(payload.get("context_proxy") or payload.get("remote_ws_address"))


def proxy_requirement_error(source_id: str, browser_config: Dict[str, Any] | None) -> str | None:
    if browser_proxy_required(browser_config) and not browser_proxy_configured(browser_config):
        return f"proxy_required:{canonicalize_source_id(source_id)}"
    return None
