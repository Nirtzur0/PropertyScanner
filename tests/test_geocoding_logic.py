import unittest
from unittest.mock import MagicMock

class MockGeocodingService:
    def geocode_address(self, address: str) -> tuple[float, float] | None:
        if "Calle de Atocha, Madrid" in address:
            return (40.411798, -3.697245)
        elif "Invalid Address" in address:
            return None
        return None

class TestGeocodingLogic(unittest.TestCase):

    def test_geocode_address_success(self):
        # Arrange
        service = MockGeocodingService()
        address = "Calle de Atocha, Madrid"

        # Act
        result = service.geocode_address(address)

        # Assert
        self.assertEqual(result, (40.411798, -3.697245))

    def test_geocode_address_failure(self):
        # Arrange
        service = MockGeocodingService()
        address = "Invalid Address"

        # Act
        result = service.geocode_address(address)

        # Assert
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()
