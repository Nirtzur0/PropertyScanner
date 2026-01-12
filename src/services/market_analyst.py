from sqlalchemy.orm import Session
from sqlalchemy import func
from src.core.domain.models import DBListing
import structlog
from typing import Dict, Optional

logger = structlog.get_logger()

class MarketAnalyst:
    """
    Analyzes market dynamics.
    Key metric: Market Velocity (Average Days on Market).
    """
    
    def __init__(self, session: Session):
        self.session = session
        
    def get_market_velocity(self, city: str = None) -> float:
        """
        Calculate the average DOM for sold listings.
        If city is provided, filter by city.
        Returns average DOM in days. Default/Fallback is 90.0.
        """
        try:
            query = self.session.query(func.avg(DBListing.dom)).filter(
                DBListing.status == 'sold',
                DBListing.dom.isnot(None)
            )
            
            if city:
                query = query.filter(DBListing.city == city)
                
            avg_dom = query.scalar()
            
            if avg_dom:
                return float(avg_dom)
            
            return 90.0 # Fallback baseline
            
        except Exception as e:
            logger.error("market_velocity_calc_failed", error=str(e))
            return 90.0

    def get_city_stats(self, city: str) -> Dict[str, float]:
        """
        Get aggregated stats for a city.
        """
        velocity = self.get_market_velocity(city)
        # Placeholder for more stats like "inventory_count" etc.
        return {
            "market_velocity": velocity
        }
