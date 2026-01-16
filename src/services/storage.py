import structlog
from datetime import datetime
from typing import List, Optional
from sqlalchemy import create_engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker, Session
from src.core.domain.models import Base, DBListing
from src.core.domain.schema import CanonicalListing
from src.core.migrations import run_migrations
from src.services.feature_sanitizer import sanitize_listing_features
from src.core.config import DEFAULT_DB_URL
import geolib.geohash

logger = structlog.get_logger()

class StorageService:
    def __init__(self, db_url: str = DEFAULT_DB_URL):
        connect_args = {}
        try:
            url = make_url(db_url)
            if url.drivername.startswith("sqlite"):
                connect_args["timeout"] = 30
        except Exception:
            pass

        self.engine = create_engine(db_url, connect_args=connect_args)
        Base.metadata.create_all(self.engine)

        # Ensure auxiliary tables/columns exist (indices, macro tables, etc).
        # SQLAlchemy `create_all` won't evolve existing SQLite schemas.
        try:
            url = make_url(db_url)
            if url.drivername.startswith("sqlite") and url.database and url.database != ":memory:":
                run_migrations(db_path=url.database)
        except Exception as e:
            logger.warning("migrations_failed", error=str(e))

        self.SessionLocal = sessionmaker(bind=self.engine)

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
                    sanitize_listing_features(item)
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

                    if hasattr(item, "analysis_meta") and item.analysis_meta:
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
                    if item.plot_area_sqm is not None: db_item.plot_area_sqm = item.plot_area_sqm
                    if item.floor is not None: db_item.floor = item.floor
                    if item.has_elevator is not None: db_item.has_elevator = item.has_elevator
                    
                    
                    # Defaults for critical enums if missing
                    if not db_item.currency: db_item.currency = "EUR"
                    if not db_item.status: db_item.status = "active"
                    if not db_item.property_type and item.property_type:
                        prop = item.property_type
                        db_item.property_type = prop.value if hasattr(prop, "value") else str(prop)

                    # Handle Location if present
                    if item.location:
                         db_item.address_full = item.location.address_full
                         if item.location.city:
                             db_item.city = item.location.city
                         if item.location.zip_code:
                             db_item.zip_code = item.location.zip_code
                         if item.location.country:
                             db_item.country = item.location.country
                         
                         # Fix: Persist Coordinates
                         db_item.lat = item.location.lat
                         db_item.lon = item.location.lon

                    # Image URLs Mapping
                    if item.image_urls:
                        # Ensure we store generic JSON list, not Pydantic HttpUrl objects
                        db_item.image_urls = [str(u) for u in item.image_urls]
                    if item.image_embeddings:
                        db_item.image_embeddings = item.image_embeddings
                    
                    # Persistence of new fields
                    if hasattr(item, "listing_type") and item.listing_type:
                        db_item.listing_type = item.listing_type

                    if hasattr(item, "estimated_rent") and item.estimated_rent is not None:
                        db_item.estimated_rent = item.estimated_rent
                    if hasattr(item, "gross_yield") and item.gross_yield is not None:
                        db_item.gross_yield = item.gross_yield

                    if db_item.lat is not None and db_item.lon is not None and not db_item.geohash:
                        try:
                            db_item.geohash = geolib.geohash.encode(db_item.lat, db_item.lon, 9)
                        except Exception as e:
                            logger.warning("geohash_failed", id=item.id, error=str(e))
                    
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
