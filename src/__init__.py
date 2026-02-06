"""Top-level package exports.

Avoid importing optional/heavy runtime dependencies at import time.

Historically this module imported the public API eagerly, which pulled in Prefect
(and its transitive deps) during *any* `src.*` import. That made unrelated
modules (e.g. domain schema) unusable in environments where orchestration deps
were not installed or had version skew.

The public API remains available via lazy attribute access:

    from src import PipelineAPI, get_pipeline_api

"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

__all__ = ["PipelineAPI", "PipelineConfig", "get_pipeline_api"]

if TYPE_CHECKING:  # pragma: no cover
    from src.interfaces.api import PipelineAPI, PipelineConfig, get_pipeline_api


def __getattr__(name: str):
    if name in __all__:
        mod = importlib.import_module("src.interfaces.api")
        return getattr(mod, name)
    raise AttributeError(name)
