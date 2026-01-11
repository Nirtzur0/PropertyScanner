from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, HttpUrl, AnyUrl

class PropertyType(str, Enum):
    APARTMENT = "apartment"
    HOUSE = "house"
    LAND = "land"
    COMMERCIAL = "commercial"
    OTHER = "other"

class Currency(str, Enum):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"

class ListingStatus(str, Enum):
    ACTIVE = "active"
    SOLD = "sold"
    EXPIRED = "expired"
    PENDING = "pending"

class GeoLocation(BaseModel):
    lat: float
    lon: float
    address_full: str
    city: str
    zip_code: Optional[str] = None
    country: str

class PriceHistoryItem(BaseModel):
    price: float
    date: datetime
    event: str  # e.g., "listed", "price_change"

class RawListing(BaseModel):
    """
    Represents the raw data extracted from a source before normalization.
    """
    source_id: str
    external_id: str
    url: str
    raw_data: Dict  # The full JSON or parsed HTML dict
    fetched_at: datetime
    html_snapshot_path: Optional[str] = None

class CanonicalListing(BaseModel):
    """
    The normalized, clean representation of a property listing.
    """
    id: str  # Unique system ID (hash of source_id + external_id)
    source_id: str
    external_id: str
    url: AnyUrl
    title: str
    description: Optional[str] = None
    
    price: float
    currency: Currency = Currency.EUR
    
    property_type: PropertyType
    
    # Physical attributes
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    surface_area_sqm: Optional[float] = None
    plot_area_sqm: Optional[float] = None
    energy_rating: Optional[str] = None
    floor: Optional[int] = None
    has_elevator: Optional[bool] = None
    
    # Location
    location: Optional[GeoLocation] = None
    
    # Media
    image_urls: List[HttpUrl] = Field(default_factory=list)
    vlm_description: Optional[str] = None
    image_embeddings: Optional[List[List[float]]] = None # Cached vector embeddings
    
    # Metadata
    listed_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=datetime.now)
    status: ListingStatus = ListingStatus.ACTIVE
    
    tags: List[str] = Field(default_factory=list)  # e.g., "pool", "garage"

class DealAnalysis(BaseModel):
    """
    The output of the scoring and valuation agents.
    """
    listing_id: str
    fair_value_estimate: float
    fair_value_uncertainty_pct: float  # e.g. 0.05 for +/- 5%
    
    rental_yield_estimate: Optional[float] = None
    
    deal_score: float = 0.0  # 0.0 to 1.0
    
    flags: List[str] = Field(default_factory=list) # e.g. "under_market_value", "missing_data"
    investment_thesis: Optional[str] = None

class CompListing(BaseModel):
    id: str
    price: float
    features: Dict[str, float] = Field(default_factory=dict)
    similarity_score: float
    snapshot_id: str

class ListingEvaluationResult(BaseModel):
    """
    The advanced ML output, including probabilistic estimates and evidence.
    """
    listing_id: str
    model_version: str
    
    # Probabilistic Outputs
    fair_value_quantiles: Dict[str, float] = Field(default_factory=dict) # e.g. "0.5": 450000
    rent_est_quantiles: Dict[str, float] = Field(default_factory=dict)
    
    # Uncertainty
    confidence_interval_width: float = 0.0
    
    # Deal Logic
    deal_score: float
    score_breakdown: Dict[str, float] = Field(default_factory=dict)
    
    # Evidence
    top_comps: List[CompListing] = Field(default_factory=list)
    flags: List[str] = Field(default_factory=list)
    
    timestamp: datetime = Field(default_factory=datetime.now)
