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
    lat: Optional[float] = None
    lon: Optional[float] = None
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
    
    listing_type: str = "sale" # "sale" or "rent"
    
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
    
    # AI Analysis
    text_sentiment: Optional[float] = None
    image_sentiment: Optional[float] = None
    
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
    
    # Forward-looking Logic
    projections: List["ValuationProjection"] = Field(default_factory=list)
    market_signals: Dict[str, float] = Field(default_factory=dict) # e.g. {"momentum": 0.8, "liquidity": 0.5}
    
    # SOTA V3: Structured evidence pack
    evidence: Optional["EvidencePack"] = None


class CompEvidence(BaseModel):
    """
    Evidence record for a single comparable used in valuation.
    Captures time-adjustment and attention weight for auditability.
    """
    id: str
    url: Optional[str] = None
    observed_month: str  # YYYY-MM format
    raw_price: float
    adj_factor: float  # Time adjustment factor
    adj_price: float  # raw_price * adj_factor
    attention_weight: float  # From Fusion model
    is_sold: bool = False
    similarity_score: Optional[float] = None


class EvidencePack(BaseModel):
    """
    Complete evidence pack for a valuation decision.
    Provides full audit trail of what was used and how.
    """
    model_used: str  # "fusion", "tabular_ml", "heuristic"
    
    # Anchor computation
    anchor_price: float  # Attention-weighted comp price
    anchor_std: float  # Comp price standard deviation
    
    # Comps used (ordered by attention weight)
    top_comps: List[CompEvidence] = Field(default_factory=list)
    
    # Fallback indicators
    hedonic_fallback: bool = False
    hedonic_fallback_reason: Optional[str] = None
    
    # Calibration status
    calibration_status: str = "uncalibrated"  # "calibrated", "uncalibrated", "partial"
    calibration_diagnostics: Optional[Dict[str, float]] = None
    
    # Timestamps
    valuation_date: Optional[str] = None
    comp_date_range: Optional[str] = None  # e.g. "2024-01 to 2024-06"

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

class ValuationProjection(BaseModel):
    """
    Projected value of a property over time.
    """
    months_future: int
    years_future: float # Allow 0.5, 0.25 etc
    predicted_value: float
    confidence_interval_low: float
    confidence_interval_high: float
    confidence_score: float # 0.0 to 1.0 (Model confidence)
    scenario_name: str = "baseline" # baseline, optimistic, pessimistic"

class MarketProfile(BaseModel):
    """
    Analysis of the market conditions for a specific property/area.
    """
    zone_id: str
    momentum_score: float # -1.0 to 1.0 (Growth trend)
    liquidity_score: float # 0.0 to 1.0 (Ease of exit)
    catchup_potential: float # 0.0 to 1.0 (Ripple effect)
    
    avg_price_sqm: float
    median_dom: Optional[int] = None
    inventory_trend: str # "increasing", "stable", "decreasing"
    
    projections: List[ValuationProjection] = Field(default_factory=list)

class AreaIntelligence(BaseModel):
    """
    Crawled/External intelligence for a specific area (City/Neighborhood).
    """
    area_id: str # e.g. "madrid" or "madrid_chamberi"
    last_updated: datetime = Field(default_factory=datetime.now)

    # Quantitative Indicators (0.0 to 1.0 or normalized)
    sentiment_score: float = 0.5 # 0.0=Negative, 1.0=Positive (News/Social)
    future_development_score: float = 0.5 # 0.0=Stagnant, 1.0=Booming (Construction permits, etc)

    # Raw Data / Metadata
    news_summary: Optional[str] = None
    top_keywords: List[str] = Field(default_factory=list)
    source_urls: List[str] = Field(default_factory=list)
