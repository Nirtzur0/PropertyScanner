import structlog
from datetime import datetime
from typing import List, Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError
from src.core.domain.models import Base, DBListing
from src.core.domain.schema import CanonicalListing
from src.services.enrichment_service import EnrichmentService
from src.services.description_analyst import DescriptionAnalyst

logger = structlog.get_logger()

class StorageService:
    def __init__(self, db_url: str = "sqlite:///data/listings.db"):
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.enrichment_service = EnrichmentService()
        self.description_analyst = DescriptionAnalyst()

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
                            # If it's already sold, we might want to update DOM here?
                            if db_item.status == "sold" and db_item.sold_at:
                                 delta = db_item.sold_at - db_item.listed_at
                                 db_item.dom = (delta.days if delta.days >= 0 else 0)

                    # Update fields
                    db_item.source_id = item.source_id
                    db_item.external_id = item.external_id
                    db_item.url = str(item.url)
                    db_item.title = item.title
                    
                    # Logic: Status Change & DOM
                    # If becoming SOLD
                    if db_item.status == "active" and item.status == "sold":
                        db_item.sold_at = datetime.utcnow()
                        if db_item.listed_at:
                            delta = db_item.sold_at - db_item.listed_at
                            db_item.dom = delta.days
                    
                    db_item.status = item.status # Update status
                    
                    db_item.price = item.price
                    db_item.bedrooms = item.bedrooms
                    db_item.surface_area_sqm = item.surface_area_sqm
                    db_item.updated_at = item.updated_at
                    
                    # Explicit field mapping
                    if item.bathrooms is not None: db_item.bathrooms = item.bathrooms
                    if item.floor is not None: db_item.floor = item.floor
                    if item.has_elevator is not None: db_item.has_elevator = item.has_elevator
                    
                    # Fix: Persist Description
                    if item.description:
                         db_item.description = item.description
                         
                         # Run Analysis if not present (simple check to avoid re-run)
                         # NOTE: In production, use a flag or check if sentiment_score is None
                         if db_item.sentiment_score is None:
                             analysis = self.description_analyst.analyze(item.description)
                             if analysis:
                                 db_item.sentiment_score = analysis.get("sentiment_score")
                                 db_item.analysis_meta = analysis
                                 
                                 # Fill missing facts
                                 facts = analysis.get("facts", {})
                                 if facts:
                                     if db_item.has_elevator is None: db_item.has_elevator = facts.get("has_elevator")
                                     if db_item.floor is None: db_item.floor = facts.get("floor")
                                     # Extend with other mappings as needed

                    # Handle Location if present
                    if item.location:
                         db_item.address_full = item.location.address_full
                         if item.location.city:
                             db_item.city = item.location.city
                         
                         # Fix: Persist Coordinates
                         db_item.lat = item.location.lat
                         db_item.lon = item.location.lon
                    
                    # Enrichment (Main Flow)
                    # Automatically fill missing city/data
                    self.enrichment_service.enrich_db_listing(db_item)
                    
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
