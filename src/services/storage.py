import structlog
from datetime import datetime
from typing import List, Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError
from src.core.domain.models import Base, DBListing
from src.core.domain.schema import CanonicalListing
from src.services.enrichment_service import EnrichmentService
from src.services.enrichment_service import EnrichmentService
from src.services.description_analyst import DescriptionAnalyst
from src.services.rent_estimator import RentEstimator

logger = structlog.get_logger()

class StorageService:
    def __init__(self, db_url: str = "sqlite:///data/listings.db"):
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.enrichment_service = EnrichmentService()
        self.description_analyst = DescriptionAnalyst()
        self.rent_estimator = RentEstimator(db_url)

    def get_session(self) -> Session:
        return self.SessionLocal()

    def save_listings(self, listings: List[CanonicalListing]) -> int:
        """
        Upserts listings into the database. Returns count of new/updated items.
        """
        session = self.get_session()
        count = 0
        try:
            for item in listings:
                try:
                    # Convert Pydantic -> ORM
                    # Note: Simplified for MVP. Ideally check if exists and update fields if changed.
                    db_item = session.query(DBListing).filter_by(id=item.id).first()
                    
                    if not db_item:
                        db_item = DBListing(id=item.id)
                        db_item.listed_at = datetime.utcnow() # Default to now (first seen)
                        session.add(db_item)
                        count += 1
                    
                    
                    # Timestamp Reconciliation (Source of Truth)
                    if item.listed_at:
                        if db_item.listed_at is None:
                            db_item.listed_at = item.listed_at
                        elif item.listed_at < db_item.listed_at:
                            # Found an OLDER date from source (e.g. "Posted 2 months ago")
                            # This is more accurate than when we scraped it.
                            db_item.listed_at = item.listed_at
                            # Recalculate DOM if sold? Yes, but usually we do that on status change.
                            # DOM logic removed


                    # Update fields
                    db_item.source_id = item.source_id
                    db_item.external_id = item.external_id
                    db_item.url = str(item.url)
                    db_item.title = item.title
                    db_item.fetched_at = datetime.utcnow()

                    
                    # Logic: Status Change & DOM
                    # If becoming SOLD
                    if db_item.status == "active" and item.status == "sold":
                        db_item.sold_at = datetime.utcnow()
                        if db_item.listed_at:
                            delta = db_item.sold_at - db_item.listed_at
                            # db_item.dom = delta.days
                    
                    db_item.status = item.status # Update status
                    
                    db_item.price = item.price
                    db_item.bedrooms = item.bedrooms
                    db_item.surface_area_sqm = item.surface_area_sqm
                    db_item.updated_at = item.updated_at
                    
                    if item.vlm_description:
                        db_item.vlm_description = item.vlm_description
                    
                    if item.description:
                         db_item.description = item.description
                         
                    # Overwrite description with structured JSON if available (User Request)
                    if hasattr(item, "analysis_meta") and item.analysis_meta:
                        import json
                        db_item.description = json.dumps(item.analysis_meta, ensure_ascii=False, indent=2)
                        db_item.analysis_meta = item.analysis_meta
                    
                    # AI Analysis Results
                    if hasattr(item, "text_sentiment") and item.text_sentiment is not None:
                         db_item.text_sentiment = item.text_sentiment
                    if hasattr(item, "image_sentiment") and item.image_sentiment is not None:
                         db_item.image_sentiment = item.image_sentiment
                    if hasattr(item, "tags"):
                         db_item.tags = item.tags

                    # Explicit field mapping
                    if item.bathrooms is not None: db_item.bathrooms = item.bathrooms
                    if item.floor is not None: db_item.floor = item.floor
                    if item.has_elevator is not None: db_item.has_elevator = item.has_elevator
                    
                    
                    # Defaults for critical enums if missing
                    if not db_item.currency: db_item.currency = "EUR"
                    if not db_item.status: db_item.status = "active"
                    if not db_item.property_type and item.property_type: db_item.property_type = str(item.property_type)

                    # Handle Location if present
                    if item.location:
                         db_item.address_full = item.location.address_full
                         if item.location.city:
                             db_item.city = item.location.city
                         
                         # Fix: Persist Coordinates
                         db_item.lat = item.location.lat
                         db_item.lon = item.location.lon

                    # Image URLs Mapping
                    if item.image_urls:
                        # Ensure we store generic JSON list, not Pydantic HttpUrl objects
                        db_item.image_urls = [str(u) for u in item.image_urls]
                    
                    # Enrichment (Main Flow)
                    # Automatically fill missing city/data
                    self.enrichment_service.enrich_db_listing(db_item)

                    # Persistence of new fields
                    if hasattr(item, "listing_type") and item.listing_type:
                        db_item.listing_type = item.listing_type
                        
                    # Rental Estimation (Only for Sales)
                    if db_item.listing_type == "sale" and db_item.price > 0:
                        rent = self.rent_estimator.estimate_rent(item)
                        if rent:
                            db_item.estimated_rent = rent
                            db_item.gross_yield = self.rent_estimator.calculate_yield(db_item.price, rent)
                    
                except Exception as e:
                    logger.error("db_save_item_error", id=item.id, error=str(e))
                    continue
            
            session.commit()
            return count
        except Exception as e:
            session.rollback()
            logger.error("db_commit_failed", error=str(e))
            raise e
        finally:
            session.close()

    def get_listing(self, listing_id: str) -> Optional[DBListing]:
        session = self.get_session()
        try:
             return session.query(DBListing).filter_by(id=listing_id).first()
        finally:
             session.close()
