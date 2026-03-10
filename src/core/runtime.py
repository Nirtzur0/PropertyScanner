from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


_ROOT_DIR = Path(__file__).resolve().parents[2]


class RuntimeAppConfig(BaseModel):
    name: str = "property_scanner"
    api_host: str = "127.0.0.1"
    api_port: int = 8000


class RuntimePathConfig(BaseModel):
    db_path: Path = Field(default=_ROOT_DIR / "data" / "listings.db")
    docs_crawler_status_path: Path = Field(default=_ROOT_DIR / "docs" / "crawler_status.md")
    sources_config_path: Path = Field(default=_ROOT_DIR / "config" / "sources.yaml")
    benchmark_json_path: Path = Field(
        default=_ROOT_DIR / "docs" / "implementation" / "reports" / "fusion_tree_benchmark.json"
    )
    benchmark_md_path: Path = Field(
        default=_ROOT_DIR / "docs" / "implementation" / "reports" / "fusion_tree_benchmark.md"
    )


class RuntimeJobConfig(BaseModel):
    max_workers: int = 2


class RuntimeQualityConfig(BaseModel):
    supported_invalid_ratio_max: float = 0.005
    degraded_invalid_ratio_max: float = 0.05
    freshness_days: int = 14
    experimental_min_rows: int = 25
    required_parser_fixture_ratio: float = 0.95


class RuntimeModelReadinessConfig(BaseModel):
    sale_min_closed_labels: int = 200
    sale_min_closed_ratio: float = 0.05


class RuntimeConfig(BaseModel):
    app: RuntimeAppConfig = Field(default_factory=RuntimeAppConfig)
    paths: RuntimePathConfig = Field(default_factory=RuntimePathConfig)
    jobs: RuntimeJobConfig = Field(default_factory=RuntimeJobConfig)
    quality: RuntimeQualityConfig = Field(default_factory=RuntimeQualityConfig)
    model_readiness: RuntimeModelReadinessConfig = Field(default_factory=RuntimeModelReadinessConfig)


class RuntimeEnv(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PROPERTY_SCANNER_",
        case_sensitive=False,
        extra="ignore",
    )

    runtime_config: Path = Field(default=_ROOT_DIR / "config" / "runtime.yaml")
    db_path: Path | None = None
    api_host: str | None = None
    api_port: int | None = None


def _load_yaml_payload(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError("runtime_config_invalid")
    return data


@lru_cache(maxsize=1)
def load_runtime_config() -> RuntimeConfig:
    env = RuntimeEnv()
    payload = _load_yaml_payload(Path(env.runtime_config))

    if env.db_path is not None:
        payload.setdefault("paths", {})
        payload["paths"]["db_path"] = str(env.db_path)
    if env.api_host is not None:
        payload.setdefault("app", {})
        payload["app"]["api_host"] = env.api_host
    if env.api_port is not None:
        payload.setdefault("app", {})
        payload["app"]["api_port"] = env.api_port

    return RuntimeConfig.model_validate(payload)
