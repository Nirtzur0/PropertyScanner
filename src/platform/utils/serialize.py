from __future__ import annotations

from typing import Any


def model_to_dict(value: Any) -> Any:
    """
    Best-effort conversion of Pydantic models to plain dicts.

    Supports Pydantic v2 (`model_dump`) and v1 (`dict`), while remaining
    a no-op for non-model values.
    """

    if value is None:
        return None
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump()
    legacy = getattr(value, "dict", None)
    if callable(legacy):
        return legacy()
    return value

