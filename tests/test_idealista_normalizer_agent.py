import unittest
from unittest.mock import patch, MagicMock
from src.listings.agents.processors.idealista import IdealistaNormalizerAgent
from src.platform.domain.schema import RawListing

class TestIdealistaNormalizerAgent(unittest.TestCase):

    @patch('src.listings.agents.processors.idealista.GeocodingService')
    def test_parse_item_with_geocoding(self, MockGeocodingService):
        # Arrange
        mock_geocoding_service = MockGeocodingService.return_value
        mock_geocoding_service.geocode_address.return_value = (40.411798, -3.697245)

        agent = IdealistaNormalizerAgent()

        html_snippet = """
        <article class="item" data-element-id="12345">
            <div class="item-info-container">
                <a href="/inmueble/12345/" class="item-link">Piso en Calle de Atocha, Madrid</a>
                <span class="item-price">450.000€</span>
            </div>
        </article>
        """
        raw_listing = RawListing(
            source_id="idealista",
            external_id="12345",
            url="http://example.com",
            raw_data={"html_snippet": html_snippet},
            fetched_at="2024-01-01T00:00:00Z"
        )

        # Act
        canonical_listing = agent._parse_item(raw_listing)

        # Assert
        self.assertIsNotNone(canonical_listing)
        self.assertEqual(canonical_listing.location.lat, 40.411798)
        self.assertEqual(canonical_listing.location.lon, -3.697245)
        mock_geocoding_service.geocode_address.assert_called_once_with("Piso en Calle de Atocha, Madrid")

if __name__ == '__main__':
    unittest.main()
