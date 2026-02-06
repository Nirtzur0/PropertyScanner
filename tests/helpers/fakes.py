from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class FakeComp:
    id: str
    similarity_score: float = 1.0


class FakeRetriever:
    """Test double for the valuation retriever boundary."""

    def __init__(self, *, comps: Optional[List[FakeComp]] = None, metadata: Optional[Dict[str, Any]] = None):
        self._comps = comps or []
        self._metadata = metadata or {}

    def retrieve_comps(self, *args: Any, **kwargs: Any) -> List[FakeComp]:
        return list(self._comps)

    def get_metadata(self) -> Dict[str, Any]:
        return dict(self._metadata)
