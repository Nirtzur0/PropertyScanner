import sys
import os
import asyncio
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from src.platform.domain.schema import RawListing
from src.listings.agents.processors.pisos import PisosNormalizerAgent
from src.listings.agents.processors.immobiliare import ImmobiliareNormalizerAgent
from src.agentic.agents.enricher import EnrichmentAgent
from src.platform.utils.compliance import ComplianceManager
from src.platform.domain.schema import GeoLocation

def test_pisos_pipeline():
    print("\n--- Testing Pisos Pipeline ---")
    
    # Mock Raw HTML from Pisos (Simple case without JSON-LD or explicit location)
    html = """
    <html>
        <h1>Piso en venta en Calle de Alcalá, Madrid</h1>
        <div class="price">300.000 €</div>
        <div class="features-summary">
            <li>2 habs.</li>
            <li>80 m²</li>
        </div>
    </html>
    """
    
    raw = RawListing(
        source_id="pisos",
        external_id="test_pisos_123",
        url="https://www.pisos.com/comprar/piso-madrid-test/",
        raw_data={"html_snippet": html},
        fetched_at=datetime.now()
    )
    
    # 1. Normalize
    normalizer = PisosNormalizerAgent()
    canonical = normalizer._parse_item(raw)
    
    if not canonical:
        print("❌ Normalization failed!")
        return
        
    print(f"✅ Normalized: {canonical.title}")
    
    # Verify strict normalization (Should have NO location or incomplete)
    if canonical.location and canonical.location.lat != 0:
        print(f"⚠️ Warning: Location present unexpectedly: {canonical.location}")
    else:
        print("✅ Location properly empty/partial (ready for enrichment)")
        
    # 2. Enrich
    print("Running Enrichment...")
    compliance = ComplianceManager("TestBot/1.0")
    enricher = EnrichmentAgent(compliance)
    
    # Manually run on single item for test
    result = enricher.run({"listings": [canonical]})
    enriched_listing = result.data[0]
    
    if enriched_listing.location and enriched_listing.location.lat != 0:
        print(f"✅ Enrichment Successful: {enriched_listing.location.city} ({enriched_listing.location.lat}, {enriched_listing.location.lon})")
    else:
        print("❌ Enrichment Failed to geocode.")

def test_immobiliare_pipeline():
    print("\n--- Testing Immobiliare Pipeline ---")
    
    # Mock Raw HTML
    html = """
    <html>
        <h1 class="in-title">Trilocale via Dante Alighieri, Milano</h1>
        <div class="in-feat__item--main">€ 450.000</div>
        <div class="in-feat">
            3 locali, 1 bagno, 95 mq
        </div>
    </html>
    """
    
    raw = RawListing(
        source_id="immobiliare_it",
        external_id="test_immo_456",
        url="https://www.immobiliare.it/annunci/12345/milano/",
        raw_data={"html_snippet": html},
        fetched_at=datetime.now()
    )
    
    # 1. Normalize
    normalizer = ImmobiliareNormalizerAgent()
    canonical = normalizer._parse_item(raw)
    
    if not canonical:
        print("❌ Normalization failed!")
        return

    print(f"✅ Normalized: {canonical.title}")
    
    # Verify strict normalization
    if canonical.location:
         print(f"⚠️ Warning: Location present unexpectedly: {canonical.location}")
    else:
         print("✅ Location properly empty (ready for enrichment)")

    # 2. Enrich
    print("Running Enrichment...")
    compliance = ComplianceManager("TestBot/1.0")
    enricher = EnrichmentAgent(compliance)
    
    result = enricher.run({"listings": [canonical]})
    enriched_listing = result.data[0]
    
    if enriched_listing.location and enriched_listing.location.lat != 0:
        print(f"✅ Enrichment Successful: {enriched_listing.location.city} ({enriched_listing.location.lat}, {enriched_listing.location.lon})")
    else:
        print("❌ Enrichment Failed to geocode.")

if __name__ == "__main__":
    test_pisos_pipeline()
    test_immobiliare_pipeline()
