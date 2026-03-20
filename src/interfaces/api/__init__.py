"""Public API surface for Property Scanner."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

__all__ = ["PipelineAPI", "PipelineConfig", "get_pipeline_api"]

if TYPE_CHECKING:  # pragma: no cover
    from src.interfaces.api.pipeline import PipelineAPI, get_pipeline_api
    from src.platform.settings import PipelineConfig


def __getattr__(name: str):
    if name in {"PipelineAPI", "get_pipeline_api"}:
        mod = importlib.import_module("src.interfaces.api.pipeline")
        return getattr(mod, name)
    if name == "PipelineConfig":
        mod = importlib.import_module("src.platform.settings")
        return getattr(mod, name)
    raise AttributeError(name)
