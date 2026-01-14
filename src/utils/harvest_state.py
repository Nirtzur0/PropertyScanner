import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import List, Optional


STATE_VERSION = 1


def _canonicalize_url(url: str) -> str:
    return url.strip().rstrip("/")


@dataclass
class HarvestAreaState:
    start_url: str
    current_url: Optional[str] = None
    pages_visited: int = 0
    consecutive_no_new_pages: int = 0
    consecutive_same_signature: int = 0
    last_signature: Optional[str] = None
    done: bool = False

    def compute_signature(self, links: List[str]) -> str:
        normalized = sorted({_canonicalize_url(u) for u in links if u})
        payload = "\n".join(normalized).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @classmethod
    def from_dict(cls, data: dict) -> "HarvestAreaState":
        return cls(
            start_url=_canonicalize_url(data.get("start_url", "")),
            current_url=_canonicalize_url(data["current_url"]) if data.get("current_url") else None,
            pages_visited=int(data.get("pages_visited", 0)),
            consecutive_no_new_pages=int(data.get("consecutive_no_new_pages", 0)),
            consecutive_same_signature=int(data.get("consecutive_same_signature", 0)),
            last_signature=data.get("last_signature"),
            done=bool(data.get("done", False)),
        )

    def to_dict(self) -> dict:
        return {
            "start_url": self.start_url,
            "current_url": self.current_url,
            "pages_visited": self.pages_visited,
            "consecutive_no_new_pages": self.consecutive_no_new_pages,
            "consecutive_same_signature": self.consecutive_same_signature,
            "last_signature": self.last_signature,
            "done": self.done,
        }


@dataclass
class HarvestState:
    mode: str
    target_count: int
    areas: List[HarvestAreaState] = field(default_factory=list)
    current_area_index: int = 0
    version: int = STATE_VERSION

    @classmethod
    def from_dict(cls, data: dict) -> "HarvestState":
        areas = [HarvestAreaState.from_dict(a) for a in data.get("areas", []) if isinstance(a, dict)]
        return cls(
            version=int(data.get("version", STATE_VERSION)),
            mode=str(data.get("mode", "")),
            target_count=int(data.get("target_count", 0)),
            current_area_index=int(data.get("current_area_index", 0)),
            areas=areas,
        )

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "mode": self.mode,
            "target_count": self.target_count,
            "current_area_index": self.current_area_index,
            "areas": [a.to_dict() for a in self.areas],
        }


def load_harvest_state(path: str, mode: str, target_count: int, start_urls: List[str]) -> HarvestState:
    state: Optional[HarvestState] = None
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                candidate = HarvestState.from_dict(raw)
                if candidate.version == STATE_VERSION:
                    state = candidate
        except Exception:
            state = None

    normalized_start_urls = [_canonicalize_url(u) for u in start_urls if u]
    if state is None:
        state = HarvestState(
            mode=mode,
            target_count=target_count,
            areas=[HarvestAreaState(start_url=u) for u in normalized_start_urls],
            current_area_index=0,
        )
        return state

    # Reconcile configured start URLs with saved state (preserve the requested order)
    saved_start_urls = [a.start_url for a in state.areas if a.start_url]
    saved_index = int(state.current_area_index or 0)
    saved_resume_start_url: Optional[str] = None
    if 0 <= saved_index < len(saved_start_urls):
        saved_resume_start_url = saved_start_urls[saved_index]

    by_start_url = {a.start_url: a for a in state.areas if a.start_url}
    state.areas = [by_start_url.get(u) or HarvestAreaState(start_url=u) for u in normalized_start_urls]

    state.mode = mode
    state.target_count = target_count
    if normalized_start_urls != saved_start_urls:
        if saved_resume_start_url and saved_resume_start_url in normalized_start_urls:
            state.current_area_index = normalized_start_urls.index(saved_resume_start_url)
        else:
            state.current_area_index = 0
    state.current_area_index = max(0, min(int(state.current_area_index or 0), len(state.areas)))
    return state


def save_harvest_state(path: str, state: HarvestState) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(state.to_dict(), f, indent=2, sort_keys=True)
