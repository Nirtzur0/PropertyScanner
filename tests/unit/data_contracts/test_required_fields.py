from datetime import datetime
from pathlib import Path

import pytest

from tests.helpers.assertions import assert_required_fields
from tests.helpers.contracts import CANONICAL_LISTING_REQUIRED_FIELDS
from tests.helpers.factories import make_raw_listing

from src.listings.agents.processors.idealista import IdealistaNormalizerAgent
from src.listings.agents.processors.pisos import PisosNormalizerAgent
from src.listings.agents.processors.rightmove import RightmoveNormalizerAgent
from src.listings.agents.processors.zoopla import ZooplaNormalizerAgent
from src.listings.agents.processors.immobiliare import ImmobiliareNormalizerAgent


def _fixed_now() -> datetime:
    return datetime(2024, 6, 1, 0, 0, 0)


@pytest.fixture
def _no_geocode(monkeypatch):
    # Idealista normalizer calls GeocodingService; keep it deterministic/offline.
    monkeypatch.setattr(
        "src.listings.services.geocoding_service.GeocodingService.geocode_address",
        lambda self, address: (40.4168, -3.7038),
    )


def test_required_fields__idealista_fixture_html__present_and_populated(_no_geocode):
    # Arrange
    html = Path("tests/resources/html/idealista.html").read_text(encoding="utf-8")
    raw = make_raw_listing(
        source_id="idealista",
        external_id="123456",
        url="https://www.idealista.com/inmueble/123456/",
        html_snippet=html,
        fetched_at=_fixed_now(),
    )
    agent = IdealistaNormalizerAgent()

    # Act
    canonical = agent._parse_item(raw)

    # Assert
    assert canonical is not None
    assert_required_fields(canonical, CANONICAL_LISTING_REQUIRED_FIELDS, context="idealista:_parse_item")
    assert canonical.location is not None
    assert canonical.location.city


def test_required_fields__pisos_inline_html__present_and_populated():
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
    raw = make_raw_listing(
        source_id="pisos",
        external_id="12345",
        url="https://www.pisos.com/venta/piso-test-12345/",
        html_snippet=html_snippet,
        fetched_at=_fixed_now(),
    )
    agent = PisosNormalizerAgent()

    # Act
    canonical = agent._parse_item(raw)

    # Assert
    assert canonical is not None
    assert_required_fields(canonical, CANONICAL_LISTING_REQUIRED_FIELDS, context="pisos:_parse_item")
    assert canonical.location is not None
    assert canonical.location.city.lower() == "madrid"


@pytest.mark.parametrize(
    "source_id, external_id, url, fixture_path, agent_cls",
    [
        (
            "rightmove_uk",
            "12345678",
            "https://www.rightmove.co.uk/properties/12345678",
            "tests/resources/html/rightmove.html",
            RightmoveNormalizerAgent,
        ),
        (
            "zoopla_uk",
            "98765432",
            "https://www.zoopla.co.uk/for-sale/details/98765432/",
            "tests/resources/html/zoopla.html",
            ZooplaNormalizerAgent,
        ),
        (
            "immobiliare_it",
            "1357911",
            "https://www.immobiliare.it/annunci/1357911/",
            "tests/resources/html/immobiliare.html",
            ImmobiliareNormalizerAgent,
        ),
    ],
)
def test_required_fields__fixture_html__present_and_populated(
    source_id, external_id, url, fixture_path, agent_cls
):
    # Arrange
    html = Path(fixture_path).read_text(encoding="utf-8")
    raw = make_raw_listing(
        source_id=source_id,
        external_id=external_id,
        url=url,
        html_snippet=html,
        fetched_at=_fixed_now(),
    )
    agent = agent_cls()

    # Act
    canonical = agent._parse_item(raw)

    # Assert
    assert canonical is not None
    assert_required_fields(canonical, CANONICAL_LISTING_REQUIRED_FIELDS, context=f"{source_id}:_parse_item")
    assert canonical.location is not None
    assert canonical.location.city
