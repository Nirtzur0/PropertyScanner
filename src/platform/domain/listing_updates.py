from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ListingUpsertPayload:
    listing_id: str
    fields: Dict[str, Any] = field(default_factory=dict)
    listed_at: Optional[datetime] = None
    sold_at: Optional[datetime] = None
    geohash: Optional[str] = None
