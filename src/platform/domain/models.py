from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, Boolean, Text, ForeignKey, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime
from src.platform.domain.schema import PropertyType, ListingStatus, Currency
from src.platform.utils.time import utcnow

Base = declarative_base()

class DBListing(Base):
    """
    SQLAlchemy model for listings.
    """
    __tablename__ = "listings"

    id = Column(String, primary_key=True)  # MD5 Hash
    source_id = Column(String, nullable=False, index=True)
    external_id = Column(String, nullable=False)
    url = Column(String, nullable=False)
    
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    
    price = Column(Float, nullable=False)
    currency = Column(String, default="EUR")
    
    property_type = Column(String, default="apartment")
    
    # Details
    bedrooms = Column(Integer, nullable=True)
    bathrooms = Column(Integer, nullable=True)
    surface_area_sqm = Column(Float, nullable=True)
    plot_area_sqm = Column(Float, nullable=True)
    floor = Column(Integer, nullable=True)
    has_elevator = Column(Boolean, nullable=True)
    
    # Location (JSON/Composite in real PG, flat here for simplicity)
    address_full = Column(String, nullable=True)
    city = Column(String, nullable=True)
    zip_code = Column(String, nullable=True)
    country = Column(String, nullable=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    geohash = Column(String, nullable=True, index=True)
    
    # Rental / Investment Data
    listing_type = Column(String, default="sale") # "sale" or "rent"
    estimated_rent = Column(Float, nullable=True) # For sales: inferred rent
    gross_yield = Column(Float, nullable=True)    # For sales: (rent*12)/price
    sold_price = Column(Float, nullable=True)     # Closed transaction price when available
    
    # Meta
    image_urls = Column(JSON, default=list)
    vlm_description = Column(Text, nullable=True) # VLM generated text
    image_embeddings = Column(JSON, default=list)
    
    # AI Analysis
    text_sentiment = Column(Float, nullable=True) # -1.0 to 1.0 from DescriptionAnalyst
    image_sentiment = Column(Float, nullable=True) # -1.0 to 1.0 from VLM
    analysis_meta = Column(JSON, default=dict) # Full output from DescriptionAnalyst
    
    tags = Column(JSON, default=list)
    
    listed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    fetched_at = Column(DateTime, default=utcnow)
    
    status = Column(String, default="active")
    sold_at = Column(DateTime, nullable=True)

    
    def __repr__(self):
        return f"<DBListing(id={self.id}, title={self.title}, price={self.price})>"

class PropertyValuation(Base):
    """
    Stores the result of the valuation pipeline.
    One listing can have multiple valuations over time (history).
    """
    __tablename__ = "valuations"
    
    id = Column(String, primary_key=True) # UUID
    listing_id = Column(String, ForeignKey("listings.id"), index=True)
    model_version = Column(String, default="v1.0")
    created_at = Column(DateTime, default=utcnow)
    
    # Core Outputs
    fair_value = Column(Float)
    price_range_low = Column(Float)  # p10
    price_range_high = Column(Float) # p90
    confidence_score = Column(Float)
    
    # Structured Evidence (JSON)
    # Stores: comps used, adjustments, thesis, signals
    evidence = Column(JSON) 
    
    listing = relationship("DBListing", backref="valuations")


class AgentRun(Base):
    """
    Stores a persisted record of an agent run for replay and memory.
    """
    __tablename__ = "agent_runs"

    id = Column(String, primary_key=True)  # UUID
    created_at = Column(DateTime, default=utcnow)

    query = Column(Text, nullable=False)
    target_areas = Column(JSON, default=list)
    strategy = Column(String, default="balanced")

    plan = Column(JSON, default=dict)
    status = Column(String, default="success")
    summary = Column(Text, nullable=True)
    error = Column(Text, nullable=True)

    listings_count = Column(Integer, default=0)
    evaluations_count = Column(Integer, default=0)
    top_listing_ids = Column(JSON, default=list)
    ui_blocks = Column(JSON, default=list)


class JobRun(Base):
    __tablename__ = "job_runs"

    id = Column(String, primary_key=True)
    job_type = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="queued", index=True)
    payload = Column(JSON, default=dict)
    result = Column(JSON, default=dict)
    logs = Column(JSON, default=list)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)


class SourceContractRun(Base):
    __tablename__ = "source_contract_runs"

    id = Column(String, primary_key=True)
    source_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="experimental", index=True)
    metrics = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class DataQualityEvent(Base):
    __tablename__ = "data_quality_events"

    id = Column(String, primary_key=True)
    source_id = Column(String, nullable=False, index=True)
    listing_id = Column(String, nullable=True, index=True)
    field_name = Column(String, nullable=False)
    severity = Column(String, nullable=False, index=True)
    code = Column(String, nullable=False, index=True)
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class UIEvent(Base):
    __tablename__ = "ui_events"

    id = Column(String, primary_key=True)
    event_name = Column(String, nullable=False, index=True)
    route = Column(String, nullable=False, index=True)
    subject_type = Column(String, nullable=True, index=True)
    subject_id = Column(String, nullable=True, index=True)
    context = Column(JSON, default=dict)
    occurred_at = Column(DateTime, default=utcnow, nullable=False, index=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class ListingObservation(Base):
    __tablename__ = "listing_observations"

    id = Column(String, primary_key=True)
    source_id = Column(String, nullable=False, index=True)
    external_id = Column(String, nullable=False, index=True)
    listing_id = Column(String, nullable=True, index=True)
    observed_at = Column(DateTime, default=utcnow, nullable=False)
    raw_payload = Column(JSON, default=dict)
    normalized_payload = Column(JSON, default=dict)
    status = Column(String, nullable=False, default="observed", index=True)
    field_confidence = Column(JSON, default=dict)


class ListingEntity(Base):
    __tablename__ = "listing_entities"

    id = Column(String, primary_key=True)
    canonical_listing_id = Column(String, nullable=False, unique=True, index=True)
    attributes = Column(JSON, default=dict)
    source_links = Column(JSON, default=list)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class BenchmarkRun(Base):
    __tablename__ = "benchmark_runs"

    id = Column(String, primary_key=True)
    status = Column(String, nullable=False, default="queued", index=True)
    config = Column(JSON, default=dict)
    metrics = Column(JSON, default=dict)
    output_json_path = Column(String, nullable=True)
    output_md_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)


class CoverageReport(Base):
    __tablename__ = "coverage_reports"

    id = Column(String, primary_key=True)
    listing_type = Column(String, nullable=False, index=True)
    segment_key = Column(String, nullable=False, index=True)
    segment_value = Column(String, nullable=False, index=True)
    sample_size = Column(Integer, nullable=False, default=0)
    empirical_coverage = Column(Float, nullable=True)
    avg_interval_width = Column(Float, nullable=True)
    status = Column(String, nullable=False, default="pending", index=True)
    report = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class Watchlist(Base):
    __tablename__ = "watchlists"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="active", index=True)
    listing_ids = Column(JSON, default=list)
    filters = Column(JSON, default=dict)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class SavedSearch(Base):
    __tablename__ = "saved_searches"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True, index=True)
    query = Column(String, nullable=True)
    filters = Column(JSON, default=dict)
    sort = Column(JSON, default=dict)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class Memo(Base):
    __tablename__ = "memos"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False, index=True)
    listing_id = Column(String, ForeignKey("listings.id"), nullable=True, index=True)
    watchlist_id = Column(String, ForeignKey("watchlists.id"), nullable=True, index=True)
    status = Column(String, nullable=False, default="draft", index=True)
    assumptions = Column(JSON, default=list)
    risks = Column(JSON, default=list)
    sections = Column(JSON, default=list)
    export_format = Column(String, nullable=False, default="markdown")
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class CompReview(Base):
    __tablename__ = "comp_reviews"

    id = Column(String, primary_key=True)
    listing_id = Column(String, ForeignKey("listings.id"), nullable=False, index=True)
    status = Column(String, nullable=False, default="draft", index=True)
    selected_comp_ids = Column(JSON, default=list)
    rejected_comp_ids = Column(JSON, default=list)
    overrides = Column(JSON, default=dict)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
