from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import yaml
from hydra import compose, initialize_config_dir
from hydra.core.global_hydra import GlobalHydra
from omegaconf import OmegaConf

from src.core.config import CONFIG_DIR
from src.core.settings import AppConfig, AgentsConfig, ScoringConfig, SourcesConfig


def _ensure_hydra_initialized(config_dir: str) -> None:
    config_path = str(Path(config_dir).resolve())
    global_hydra = GlobalHydra.instance()
    if global_hydra.is_initialized():
        return
    initialize_config_dir(config_dir=config_path, job_name="property_scanner", version_base=None)


def _compose_config(config_dir: str, config_name: str, overrides: Sequence[str]) -> Dict[str, Any]:
    _ensure_hydra_initialized(config_dir)
    cfg = compose(config_name=config_name, overrides=list(overrides))
    data = OmegaConf.to_container(cfg, resolve=True)
    if not isinstance(data, dict):
        raise ValueError("config_invalid")
    return data


@lru_cache(maxsize=4)
def load_app_config(
    config_dir: str = str(CONFIG_DIR),
    config_name: str = "app",
    overrides: Tuple[str, ...] = (),
) -> AppConfig:
    payload = _compose_config(config_dir=config_dir, config_name=config_name, overrides=overrides)
    return AppConfig.model_validate(payload)


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
