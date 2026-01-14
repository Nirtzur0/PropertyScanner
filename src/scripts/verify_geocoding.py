import sys
import os
import logging
from datetime import datetime

# Add src to path
sys.path.append(os.getcwd())

from src.core.domain.models import DBListing
from src.core.domain.schema import CanonicalListing, GeoLocation, PropertyType
from src.services.enrichment_service import EnrichmentService
from src.agents.analysts.enricher import EnrichmentAgent
from src.utils.compliance import ComplianceManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_service_level():
    logger.info("--- Testing EnrichmentService (Storage Level) ---")
    service = EnrichmentService()
    
    # Create valid address listing
    # Using a known address in Madrid: "Calle Gran Vía, 1, 28013 Madrid, Spain"
    listing = DBListing(
        id="test_1",
        source_id="manual",
        external_id="1",
        url="http://test.com",
        title="Test Listing",
        price=100000,
        address_full="Calle Gran Vía 1, Madrid, Spain",
        lat=None,
        lon=None,
        geohash=None
    )
    
    logger.info(f"Before: lat={listing.lat}, lon={listing.lon}, geohash={listing.geohash}")
    service.enrich_db_listing(listing)
    logger.info(f"After: lat={listing.lat}, lon={listing.lon}, geohash={listing.geohash}")
    
    if listing.lat and listing.lon and listing.geohash:
        logger.info("PASS: Service enriched lat/lon and geohash.")
    else:
        logger.error("FAIL: Service did not enrich properly.")

def test_agent_level():
    logger.info("--- Testing EnrichmentAgent (Agent Level) ---")
    compliance = ComplianceManager(user_agent="verify_script")
    agent = EnrichmentAgent(compliance)
    
    # Create listing with location object but missing lat/lon
    c_listing = CanonicalListing(
        id="test_2",
        source_id="manual",
        external_id="2",
        url="http://test.com",
        title="Test Agent Listing",
        price=200000,
        property_type=PropertyType.APARTMENT,
        location=GeoLocation(
            address_full="Passeig de Gràcia 1, Barcelona, Spain",
            city="Barcelona",
            country="Spain",
            lat=0.0,
            lon=0.0
        )
    )
    
    logger.info(f"Before: lat={c_listing.location.lat}, lon={c_listing.location.lon}")
    
    response = agent.run({"listings": [c_listing]})
    out_listing = response.data[0]
    
    logger.info(f"After: lat={out_listing.location.lat}, lon={out_listing.location.lon}")
    
    if out_listing.location.lat != 0 and out_listing.location.lon != 0:
        logger.info("PASS: Agent enriched lat/lon from address.")
    else:
        logger.error("FAIL: Agent did not enrich.")

if __name__ == "__main__":
    test_service_level()
    logger.info("\n")
    test_agent_level()
