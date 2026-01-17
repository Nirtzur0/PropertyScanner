import pytest
import os
from datetime import datetime
from src.platform.domain.schema import RawListing
from src.listings.agents.processors.idealista import IdealistaNormalizerAgent

def test_idealista_normalization(real_data_dir):
    """
    Test parsing a realistic Idealista HTML file.
    """
    html_path = os.path.join(real_data_dir, "html", "idealista.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # Create RawListing Input
    raw = RawListing(
        source_id="idealista",
        external_id="123456",
        url="https://www.idealista.com/inmueble/123456/",
        raw_data={"html_snippet": html_content},
        fetched_at=datetime.utcnow()
    )
    
    agent = IdealistaNormalizerAgent()
    
    # We might need to mock geocoding if it requires external API
    # For now, let's assume it fails gracefully or works
    
    response = agent.run({"raw_listings": [raw]})
    
    assert response.status == "success"
    assert len(response.data) == 1
    
    listing = response.data[0]
    
    # Assertions based on idealista.html content
    assert listing.price == 450000.0
    assert listing.title == "Piso en venta en Calle de Alcalá, Madrid"
    assert "Piso en venta en Calle de Alcalá, Madrid" in listing.title or listing.location.city == "Madrid"
    assert listing.surface_area_sqm == 120.0
    assert listing.bedrooms == 3
    assert listing.bathrooms == 2
    assert listing.has_elevator is True
    assert listing.floor == 4
    assert listing.location.city.lower() == "madrid"
