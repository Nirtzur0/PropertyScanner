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
