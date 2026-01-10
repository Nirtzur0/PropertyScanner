import structlog
from typing import List, Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError
from src.core.domain.models import Base, DBListing
from src.core.domain.schema import CanonicalListing

logger = structlog.get_logger()

class StorageService:
    def __init__(self, db_url: str = "sqlite:///data/listings.db"):
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
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
                    # Convert Pydantic -> ORM
                    # Note: Simplified for MVP. Ideally check if exists and update fields if changed.
                    db_item = session.query(DBListing).filter_by(id=item.id).first()
                    
                    if not db_item:
                        db_item = DBListing(id=item.id)
                        session.add(db_item)
                        count += 1
                    
                    # Update fields
                    db_item.source_id = item.source_id
                    db_item.external_id = item.external_id
                    db_item.url = str(item.url)
                    db_item.title = item.title
                    db_item.price = item.price
                    db_item.bedrooms = item.bedrooms
                    db_item.surface_area_sqm = item.surface_area_sqm
                    db_item.updated_at = item.updated_at
                    
                    # Handle Location if present
                    if item.location:
                         db_item.address_full = item.location.address_full
                         db_item.city = item.location.city
                    
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
