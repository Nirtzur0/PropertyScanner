from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from src.platform.domain.schema import CanonicalListing


class CrawlJobRequest(BaseModel):
    source_ids: Optional[List[str]] = None
    max_listings: int = 0
    max_pages: int = 1
    page_size: int = 24


class IndexJobRequest(BaseModel):
    listing_type: str = "all"
    limit: int = 0


class BenchmarkJobRequest(BaseModel):
    listing_type: str = "sale"
    label_source: str = "auto"
    geo_key: str = "city"


class PreflightJobRequest(BaseModel):
    source_ids: Optional[List[str]] = None
    max_listings: int = 0
    max_pages: int = 1
    page_size: int = 24
    skip_crawl: bool = False
    skip_market_data: bool = False
    skip_index: bool = False
    skip_training: bool = False


class ValuationRequest(BaseModel):
    listing_id: Optional[str] = None
    listing: Optional[CanonicalListing] = None
    persist: bool = False

    def validate_payload(self) -> None:
        if not self.listing_id and self.listing is None:
            raise ValueError("listing_id_or_listing_required")


class WatchlistRequest(BaseModel):
    name: str = Field(min_length=1)
    description: Optional[str] = None
    status: str = "active"
    listing_ids: List[str] = Field(default_factory=list)
    filters: dict = Field(default_factory=dict)
    notes: Optional[str] = None


class SavedSearchRequest(BaseModel):
    name: str = Field(min_length=1)
    query: Optional[str] = None
    filters: dict = Field(default_factory=dict)
    sort: dict = Field(default_factory=dict)
    notes: Optional[str] = None


class MemoRequest(BaseModel):
    title: str = Field(min_length=1)
    listing_id: Optional[str] = None
    watchlist_id: Optional[str] = None
    status: str = "draft"
    assumptions: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    sections: List[dict] = Field(default_factory=list)
    export_format: str = "markdown"


class CompReviewRequest(BaseModel):
    listing_id: str = Field(min_length=1)
    status: str = "draft"
    selected_comp_ids: List[str] = Field(default_factory=list)
    rejected_comp_ids: List[str] = Field(default_factory=list)
    overrides: dict = Field(default_factory=dict)
    notes: Optional[str] = None


class UIEventRequest(BaseModel):
    event_name: str = Field(min_length=1)
    route: str = Field(min_length=1)
    subject_type: Optional[str] = None
    subject_id: Optional[str] = None
    context: dict = Field(default_factory=dict)
    occurred_at: datetime
