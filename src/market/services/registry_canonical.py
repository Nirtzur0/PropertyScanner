from __future__ import annotations

import re
from typing import Dict, Optional

from src.platform.settings import AppConfig
from src.platform.utils.config import load_app_config_safe


class RegistryCanonicalizer:
    """
    Normalizes registry region identifiers to a canonical, comparable form.
    """

    def __init__(self, app_config: Optional[AppConfig] = None) -> None:
        self.app_config = app_config or load_app_config_safe()
        self.config = getattr(self.app_config, "registry", None)
        self.include_country_prefix = bool(getattr(self.config, "include_country_prefix", False))
        self.region_aliases: Dict[str, Dict[str, str]] = getattr(self.config, "region_aliases", {}) or {}
        self.provider_region_aliases: Dict[str, Dict[str, str]] = getattr(
            self.config,
            "provider_region_aliases",
            {},
        ) or {}

    def canonicalize(
        self,
        region_id: Optional[str],
        *,
        country_code: Optional[str] = None,
        provider_id: Optional[str] = None,
    ) -> str:
        normalized = self._normalize(region_id)
        if not normalized:
            return ""

        alias = self._resolve_alias(normalized, country_code=country_code, provider_id=provider_id)
        if alias:
            normalized = self._normalize(alias)

        if self.include_country_prefix and country_code:
            code = str(country_code).strip().lower()
            if not normalized.startswith(f"{code}:"):
                normalized = f"{code}:{normalized}"

        return normalized

    def _resolve_alias(
        self,
        normalized: str,
        *,
        country_code: Optional[str],
        provider_id: Optional[str],
    ) -> Optional[str]:
        if provider_id:
            provider_map = self.provider_region_aliases.get(str(provider_id).strip(), {})
            alias = self._lookup_alias(provider_map, normalized)
            if alias:
                return alias

        if country_code:
            country_key = str(country_code).strip().upper()
            country_map = self.region_aliases.get(country_key, {})
            alias = self._lookup_alias(country_map, normalized)
            if alias:
                return alias

        return None

    def _lookup_alias(self, mapping: Dict[str, str], normalized: str) -> Optional[str]:
        if not mapping:
            return None
        for key, value in mapping.items():
            if self._normalize(key) == normalized:
                return value
        return None

    @staticmethod
    def _normalize(value: Optional[str]) -> str:
        if value is None:
            return ""
        text = str(value).strip().lower()
        if not text:
            return ""
        text = re.sub(r"[\(\)\[\]\{\}]", " ", text)
        text = re.sub(r"[-/_,;]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text
