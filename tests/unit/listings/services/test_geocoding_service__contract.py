from unittest.mock import MagicMock

import pytest

from geopy.exc import GeocoderServiceError, GeocoderTimedOut

from src.listings.services.geocoding_service import GeocodingService


def test_geocode_address__geolocator_returns_location__returns_lat_lon():
    # Arrange
    svc = GeocodingService(user_agent="test")
    svc.geolocator = MagicMock()
    svc.geolocator.geocode.return_value = MagicMock(latitude=40.0, longitude=-3.0)

    # Act
    result = svc.geocode_address("Calle de Atocha, Madrid")

    # Assert
    assert result == (40.0, -3.0)
    svc.geolocator.geocode.assert_called_once_with("Calle de Atocha, Madrid", timeout=5)


def test_geocode_address__geolocator_returns_none__returns_none():
    # Arrange
    svc = GeocodingService(user_agent="test")
    svc.geolocator = MagicMock()
    svc.geolocator.geocode.return_value = None

    # Act
    result = svc.geocode_address("Invalid Address")

    # Assert
    assert result is None


@pytest.mark.parametrize("exc", [GeocoderTimedOut("x"), GeocoderServiceError("y")])
def test_geocode_address__geolocator_errors__returns_none(exc):
    # Arrange
    svc = GeocodingService(user_agent="test")
    svc.geolocator = MagicMock()
    svc.geolocator.geocode.side_effect = exc

    # Act
    result = svc.geocode_address("Some Address")

    # Assert
    assert result is None


def test_geocode_details__geolocator_returns_address_details__returns_country_code_uppercase():
    # Arrange
    svc = GeocodingService(user_agent="test")
    svc.geolocator = MagicMock()
    svc.geolocator.geocode.return_value = MagicMock(
        latitude=40.0,
        longitude=-3.0,
        raw={"address": {"country": "Spain", "country_code": "es"}},
    )

    # Act
    details = svc.geocode_details("Madrid")

    # Assert
    assert details == {"lat": 40.0, "lon": -3.0, "country": "Spain", "country_code": "ES"}
    svc.geolocator.geocode.assert_called_once_with("Madrid", timeout=5, addressdetails=True)


def test_geocode_details__geolocator_returns_none__returns_none():
    # Arrange
    svc = GeocodingService(user_agent="test")
    svc.geolocator = MagicMock()
    svc.geolocator.geocode.return_value = None

    # Act
    details = svc.geocode_details("Nowhere")

    # Assert
    assert details is None
