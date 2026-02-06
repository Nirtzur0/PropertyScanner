from datetime import datetime

from src.listings.agents.processors.pisos import PisosNormalizerAgent
from src.platform.domain.schema import RawListing


def test_pisos_parse__inline_html__extracts_core_fields():
    # Arrange
    html_snippet = """
    <html>
      <head>
        <script type="application/ld+json">
          {
            "@type": "Apartment",
            "name": "Piso en Madrid",
            "address": {"addressLocality": "Madrid"},
            "geo": {"latitude": 40.4168, "longitude": -3.7038},
            "image": "https://example.com/image.jpg",
            "datePosted": "2024-01-01"
          }
        </script>
      </head>
      <body>
        <div class="price">250.000 €</div>
        <ul class="features-summary">
          <li>3 habs.</li>
          <li>90 m²</li>
          <li>2 baños</li>
          <li>Planta 4</li>
          <li>Con ascensor</li>
          <li>Certificacion energetica: A</li>
        </ul>
        <div class="description__content">Bonito piso reformado.</div>
      </body>
    </html>
    """

    raw = RawListing(
        source_id="pisos",
        external_id="12345",
        url="https://www.pisos.com/venta/piso-test-12345/",
        raw_data={"html_snippet": html_snippet, "is_detail_page": True},
        fetched_at=datetime(2024, 1, 1, 0, 0, 0),
    )

    agent = PisosNormalizerAgent()

    # Act
    listing = agent._parse_item(raw)

    # Assert
    assert listing is not None
    assert listing.bedrooms == 3
    assert listing.bathrooms == 2
    assert listing.surface_area_sqm == 90.0
    assert listing.floor == 4
    assert listing.has_elevator is True
    assert listing.location is not None
    assert listing.location.city.lower() == "madrid"
