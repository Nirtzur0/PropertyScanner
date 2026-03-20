"""Public package facade for Property Scanner."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

__version__ = "0.1.0"
__all__ = ["PipelineAPI", "get_pipeline_api", "__version__"]

if TYPE_CHECKING:  # pragma: no cover
    from src.interfaces.api import PipelineAPI, get_pipeline_api


def __getattr__(name: str):
    if name in {"PipelineAPI", "get_pipeline_api"}:
        mod = importlib.import_module("src.interfaces.api")
        return getattr(mod, name)
    raise AttributeError(name)
