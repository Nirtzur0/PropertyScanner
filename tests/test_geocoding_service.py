import unittest
from unittest.mock import patch
from src.services.geocoding_service import GeocodingService

class TestGeocodingService(unittest.TestCase):

    @patch('src.services.geocoding_service.GeocodingService.geocode_address')
    def test_geocode_address_success(self, mock_geocode_address):
        # Arrange
        mock_geocode_address.return_value = (40.411798, -3.697245)
        service = GeocodingService()
        address = "Calle de Atocha, Madrid"

        # Act
        result = service.geocode_address(address)

        # Assert
        self.assertEqual(result, (40.411798, -3.697245))
        mock_geocode_address.assert_called_once_with(address)

    @patch('src.services.geocoding_service.GeocodingService.geocode_address')
    def test_geocode_address_failure(self, mock_geocode_address):
        # Arrange
        mock_geocode_address.return_value = None
        service = GeocodingService()
        address = "Invalid Address"

        # Act
        result = service.geocode_address(address)

        # Assert
        self.assertIsNone(result)
        mock_geocode_address.assert_called_once_with(address)

if __name__ == '__main__':
    unittest.main()
