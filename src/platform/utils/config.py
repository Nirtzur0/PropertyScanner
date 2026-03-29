"""
Configuration loader — replaces Hydra with plain YAML merge + Pydantic validation.

Reads ``config/app.yaml`` to discover which sub-files to include (via a
``defaults`` list), merges them into a single dict, validates through
:class:`AppConfig`, and caches the result.

Environment variables with prefix ``PROPERTY_SCANNER_`` still override any YAML
value at the ``RuntimeConfig`` level (see :mod:`src.core.runtime`).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from src.platform.config import CONFIG_DIR
from src.platform.settings import AgentsConfig, AppConfig, ScoringConfig, SourcesConfig


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge *override* into *base* (override wins on conflicts)."""
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def _resolve_env_interpolations(data: Dict[str, Any]) -> Dict[str, Any]:
    """Replace ``${oc.env:VAR,default}`` patterns with env values (Hydra compat)."""
    resolved: Dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            resolved[key] = _resolve_env_interpolations(value)
        elif isinstance(value, str) and "${oc.env:" in value:
            # Parse ${oc.env:VAR_NAME,default_value} or ${oc.env:VAR_NAME}
            import re

            def _replace(match: re.Match) -> str:
                inner = match.group(1)
                parts = inner.split(",", 1)
                env_var = parts[0].strip()
                default = parts[1].strip() if len(parts) > 1 else ""
                return os.environ.get(env_var, default)

            resolved[key] = re.sub(r"\$\{oc\.env:([^}]+)\}", _replace, value)
        elif isinstance(value, list):
            resolved[key] = [
                _resolve_env_interpolations(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            resolved[key] = value
    return resolved


def _compose_config(config_dir: str, config_name: str = "app") -> Dict[str, Any]:
    """Load the app YAML and merge all referenced sub-configs."""
    config_path = Path(config_dir).resolve()
    app_yaml = _load_yaml(config_path / f"{config_name}.yaml")

    # Parse ``defaults`` list (Hydra-style)
    defaults = app_yaml.pop("defaults", [])

    merged: Dict[str, Any] = {}
    for entry in defaults:
        if isinstance(entry, str):
            if entry == "_self_":
                merged = _deep_merge(merged, app_yaml)
                continue
            sub = _load_yaml(config_path / f"{entry}.yaml")
            merged = _deep_merge(merged, sub)
        elif isinstance(entry, dict):
            for sub_key, sub_name in entry.items():
                sub = _load_yaml(config_path / f"{sub_name}.yaml")
                merged = _deep_merge(merged, {sub_key: sub})
    # If _self_ was not in defaults, apply app_yaml overrides last
    if "_self_" not in [e for e in defaults if isinstance(e, str)]:
        merged = _deep_merge(merged, app_yaml)

    return _resolve_env_interpolations(merged)


@lru_cache(maxsize=4)
def load_app_config(
    config_dir: str = str(CONFIG_DIR),
    config_name: str = "app",
    overrides: Tuple[str, ...] = (),
) -> AppConfig:
    payload = _compose_config(config_dir=config_dir, config_name=config_name)
    # Apply CLI-style overrides (key=value) for backward compat
    for override in overrides:
        if "=" in override:
            key, _, val = override.partition("=")
            parts = key.strip().split(".")
            target = payload
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = val
    return AppConfig.model_validate(payload)


def load_app_config_safe(
    config_dir: str = str(CONFIG_DIR),
    config_name: str = "app",
    overrides: Tuple[str, ...] = (),
) -> AppConfig:
    try:
        return load_app_config(config_dir=config_dir, config_name=config_name, overrides=overrides)
    except Exception:
        return AppConfig()


class ConfigLoader:
    def __init__(
        self,
        config_dir: str = str(CONFIG_DIR),
        config_name: str = "app",
        overrides: Optional[List[str]] = None,
    ) -> None:
        self.config_dir = config_dir
        self.config_name = config_name
        self.overrides = tuple(overrides or ())
        self._app: Optional[AppConfig] = None

    def load_yaml(self, filename: str) -> Dict[str, Any]:
        file_path = Path(self.config_dir).resolve() / filename
        if not file_path.exists():
            raise FileNotFoundError(f"Config file not found: {file_path}")
        with open(file_path, "r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)

    @property
    def app(self) -> AppConfig:
        if self._app is None:
            self._app = load_app_config(
                config_dir=self.config_dir,
                config_name=self.config_name,
                overrides=self.overrides,
            )
        return self._app

    @property
    def sources(self) -> SourcesConfig:
        return self.app.sources

    @property
    def agents(self) -> AgentsConfig:
        return self.app.agents

    @property
    def scoring(self) -> ScoringConfig:
        return self.app.scoring

    def as_dict(self) -> Dict[str, Any]:
        return self.app.model_dump(mode="json")
