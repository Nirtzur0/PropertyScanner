import unittest

from src.agents.processors.pisos import PisosNormalizerAgent
from src.core.domain.schema import RawListing


class TestPisosNormalizerAgent(unittest.TestCase):
    def test_parse_item_extracts_features(self):
        agent = PisosNormalizerAgent()

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

        raw_listing = RawListing(
            source_id="pisos",
            external_id="12345",
            url="https://www.pisos.com/venta/piso-test-12345/",
            raw_data={"html_snippet": html_snippet, "is_detail_page": True},
            fetched_at="2024-01-01T00:00:00Z",
        )

        canonical = agent._parse_item(raw_listing)

        self.assertIsNotNone(canonical)
        self.assertEqual(canonical.bedrooms, 3)
        self.assertEqual(canonical.bathrooms, 2)
        self.assertEqual(canonical.surface_area_sqm, 90.0)
        self.assertEqual(canonical.floor, 4)
        self.assertTrue(canonical.has_elevator)
        self.assertIsNotNone(canonical.location)
        self.assertEqual(canonical.location.city.lower(), "madrid")


if __name__ == "__main__":
    unittest.main()
