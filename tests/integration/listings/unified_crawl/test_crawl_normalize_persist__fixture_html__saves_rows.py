import pytest
from pathlib import Path

from src.listings.agents.crawlers.uk.rightmove import RightmoveCrawlerAgent
from src.listings.agents.crawlers.uk.zoopla import ZooplaCrawlerAgent
from src.listings.agents.crawlers.italy.immobiliare import ImmobiliareCrawlerAgent
from src.listings.agents.crawlers.spain.pisos import PisosCrawlerAgent
from src.listings.agents.crawlers.uk.onthemarket import OnTheMarketCrawlerAgent
from src.listings.agents.crawlers.czech_republic.sreality import SrealityCrawlerAgent
from src.listings.agents.crawlers.portugal.imovirtual import ImovirtualCrawlerAgent
from src.listings.agents.processors.rightmove import RightmoveNormalizerAgent
from src.listings.agents.processors.zoopla import ZooplaNormalizerAgent
from src.listings.agents.processors.immobiliare import ImmobiliareNormalizerAgent
from src.listings.agents.processors.pisos import PisosNormalizerAgent
from src.listings.agents.processors.onthemarket import OnTheMarketNormalizerAgent
from src.listings.agents.processors.sreality import SrealityNormalizerAgent
from src.listings.agents.processors.imovirtual import ImovirtualNormalizerAgent
from src.listings.scraping.client import FetchResult
from src.listings.repositories.listings import ListingsRepository
from src.listings.services.listing_persistence import ListingPersistenceService

pytestmark = pytest.mark.integration



class DummyCompliance:
    def check_and_wait(self, url: str, rate_limit_seconds: float = 1.0) -> bool:
        return True


def _listing_store(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'listings.db'}"
    listings_repo = ListingsRepository(db_url=db_url)
    persistence = ListingPersistenceService(listings_repo)
    return listings_repo, persistence


def test_crawl_normalize_persist__rightmove_fixture_html__saves_listing_row(tmp_path):
    # Arrange
    search_html = Path("tests/resources/html/rightmove_search.html").read_text(encoding="utf-8")
    detail_html = Path("tests/resources/html/rightmove.html").read_text(encoding="utf-8")

    crawler = RightmoveCrawlerAgent(
        config={
            "id": "rightmove_uk",
            "base_url": "https://www.rightmove.co.uk",
            "rate_limit": {"period_seconds": 0},
        },
        compliance_manager=DummyCompliance(),
    )
    crawler.scrape_client.snapshot_service.save_snapshot = lambda **kwargs: None

    def fake_fetch_html(url, timeout_s=30.0, **_kwargs):
        if "find.html" in url:
            return search_html
        if "/properties/12345678" in url:
            return detail_html
        return None

    def fake_fetch_html_batch(urls, **_kwargs):
        results = []
        for url in urls:
            html = detail_html if "/properties/12345678" in url else fake_fetch_html(url)
            results.append(FetchResult(url=url, html=html))
        return results

    crawler.scrape_client.fetch_html = fake_fetch_html
    crawler.scrape_client.fetch_html_batch = fake_fetch_html_batch

    # Act
    result = crawler.run(
        {"start_url": "https://www.rightmove.co.uk/property-for-sale/find.html?index=0"}
    )

    # Assert
    assert result.status == "success"
    assert len(result.data) == 1
    raw = result.data[0]
    assert raw.external_id == "12345678"
    assert raw.raw_data.get("html_snippet")

    # Act
    normalizer = RightmoveNormalizerAgent()
    normalized = normalizer.run({"raw_listings": result.data})

    # Assert
    assert normalized.status == "success"
    canonical = normalized.data[0]
    assert canonical.price == 850000.0
    assert canonical.location is not None

    # Act
    listings_repo, persistence = _listing_store(tmp_path)
    saved = persistence.save_listings(normalized.data)

    # Assert
    assert saved == 1
    db_item = listings_repo.get_listing_by_id(canonical.id)
    assert db_item is not None
    assert db_item.price == canonical.price
    assert db_item.city.lower() == "london"


def test_crawl_normalize_persist__zoopla_fixture_html__saves_listing_row(tmp_path):
    # Arrange
    search_html = Path("tests/resources/html/zoopla_search.html").read_text(encoding="utf-8")
    detail_html = Path("tests/resources/html/zoopla.html").read_text(encoding="utf-8")

    crawler = ZooplaCrawlerAgent(
        config={
            "id": "zoopla_uk",
            "base_url": "https://www.zoopla.co.uk",
            "rate_limit": {"period_seconds": 0},
        },
        compliance_manager=DummyCompliance(),
    )
    crawler.scrape_client.snapshot_service.save_snapshot = lambda **kwargs: None

    def fake_fetch_html(url, timeout_s=30.0, **_kwargs):
        if "/details/98765432" in url:
            return detail_html
        if "property" in url or "for-sale" in url:
            return search_html
        return None

    def fake_fetch_html_batch(urls, **_kwargs):
        results = []
        for url in urls:
            html = detail_html if "/details/98765432" in url else fake_fetch_html(url)
            results.append(FetchResult(url=url, html=html))
        return results

    crawler.scrape_client.fetch_html = fake_fetch_html
    crawler.scrape_client.fetch_html_batch = fake_fetch_html_batch

    # Act
    result = crawler.run(
        {"start_url": "https://www.zoopla.co.uk/for-sale/property/manchester/"}
    )

    # Assert
    assert result.status == "success"
    assert len(result.data) == 1
    raw = result.data[0]
    assert raw.external_id == "98765432"
    assert raw.raw_data.get("html_snippet")

    # Act
    normalizer = ZooplaNormalizerAgent()
    normalized = normalizer.run({"raw_listings": result.data})

    # Assert
    assert normalized.status == "success"
    canonical = normalized.data[0]
    assert canonical.price == 450000.0
    assert canonical.location is not None

    # Act
    listings_repo, persistence = _listing_store(tmp_path)
    saved = persistence.save_listings(normalized.data)

    # Assert
    assert saved == 1
    db_item = listings_repo.get_listing_by_id(canonical.id)
    assert db_item is not None
    assert db_item.price == canonical.price
    assert db_item.city.lower() == "manchester"


def test_crawl_normalize_persist__immobiliare_fixture_html__saves_listing_row(tmp_path):
    # Arrange
    detail_html = Path("tests/resources/html/immobiliare.html").read_text(encoding="utf-8")
    listing_url = "https://www.immobiliare.it/annunci/1357911/"

    crawler = ImmobiliareCrawlerAgent(
        config={
            "id": "immobiliare_it",
            "base_url": "https://www.immobiliare.it",
            "rate_limit": {"period_seconds": 0},
        },
        compliance_manager=DummyCompliance(),
    )
    crawler.scrape_client.snapshot_service.save_snapshot = lambda **kwargs: None

    def fake_fetch_html_batch(urls, **_kwargs):
        results = []
        for url in urls:
            html = detail_html if "immobiliare.it/annunci/1357911" in url else None
            results.append(FetchResult(url=url, html=html))
        return results

    crawler.scrape_client.fetch_html_batch = fake_fetch_html_batch

    # Act
    result = crawler.run({"listing_url": listing_url})

    # Assert
    assert result.status == "success"
    assert len(result.data) == 1
    raw = result.data[0]
    assert raw.external_id == "1357911"
    assert raw.raw_data.get("html_snippet")

    # Act
    normalizer = ImmobiliareNormalizerAgent()
    normalized = normalizer.run({"raw_listings": result.data})

    # Assert
    assert normalized.status == "success"
    canonical = normalized.data[0]
    assert canonical.price == 620000.0
    assert canonical.location is not None

    # Act
    listings_repo, persistence = _listing_store(tmp_path)
    saved = persistence.save_listings(normalized.data)

    # Assert
    assert saved == 1
    db_item = listings_repo.get_listing_by_id(canonical.id)
    assert db_item is not None
    assert db_item.price == canonical.price


def test_crawl_normalize_persist__pisos_fixture_html__saves_listing_row(tmp_path):
    # Arrange
    search_html = Path("tests/resources/html/pisos_search.html").read_text(encoding="utf-8")
    detail_html = Path("tests/resources/html/pisos.html").read_text(encoding="utf-8")

    crawler = PisosCrawlerAgent(
        config={
            "id": "pisos",
            "base_url": "https://www.pisos.com",
            "rate_limit": {"period_seconds": 0},
        },
        compliance_manager=DummyCompliance(),
    )
    crawler.scrape_client.snapshot_service.save_snapshot = lambda **kwargs: None

    def fake_fetch_html(url, timeout_s=30.0, **_kwargs):
        if "pisos-madrid_capital_centro" in url or "venta/pisos" in url:
            return search_html
        return None

    def fake_fetch_html_batch(urls, **_kwargs):
        results = []
        for url in urls:
            html = detail_html if "/inmueble/piso-madrid-centro-12345/" in url else None
            results.append(FetchResult(url=url, html=html))
        return results

    crawler.scrape_client.fetch_html = fake_fetch_html
    crawler.scrape_client.fetch_html_batch = fake_fetch_html_batch

    # Act
    result = crawler.run({"search_path": "/venta/pisos-madrid_capital_centro/", "max_listings": 1})

    # Assert
    assert result.status == "success"
    assert len(result.data) == 1
    raw = result.data[0]
    assert raw.external_id == "12345"
    assert raw.raw_data.get("html_snippet")

    # Act
    normalizer = PisosNormalizerAgent()
    normalized = normalizer.run({"raw_listings": result.data})

    # Assert
    assert normalized.status == "success"
    canonical = normalized.data[0]
    assert canonical.price == 245000.0
    assert canonical.surface_area_sqm is not None and canonical.surface_area_sqm > 0
    assert canonical.location is not None

    # Act
    listings_repo, persistence = _listing_store(tmp_path)
    saved = persistence.save_listings(normalized.data)

    # Assert
    assert saved == 1
    db_item = listings_repo.get_listing_by_id(canonical.id)
    assert db_item is not None
    assert db_item.price == canonical.price
    assert (db_item.city or "").lower() == "madrid"
    assert db_item.surface_area_sqm is not None and db_item.surface_area_sqm > 0


def test_crawl_normalize_persist__onthemarket_fixture_html__saves_listing_row(tmp_path):
    # Arrange
    search_html = Path("tests/resources/html/onthemarket_search.html").read_text(encoding="utf-8")
    detail_html = Path("tests/resources/html/onthemarket.html").read_text(encoding="utf-8")

    crawler = OnTheMarketCrawlerAgent(
        config={
            "id": "onthemarket_uk",
            "base_url": "https://www.onthemarket.com",
            "rate_limit": {"period_seconds": 0},
        },
        compliance=DummyCompliance(),
    )
    crawler.scrape_client.snapshot_service.save_snapshot = lambda **kwargs: None

    def fake_fetch_html(url, timeout_s=30.0, **_kwargs):
        if "/for-sale/property/" in url or "onthemarket.com/for-sale" in url:
            return search_html
        return None

    def fake_fetch_html_batch(urls, **_kwargs):
        results = []
        for url in urls:
            html = detail_html if "/details/12345/" in url else None
            results.append(FetchResult(url=url, html=html))
        return results

    crawler.scrape_client.fetch_html = fake_fetch_html
    crawler.scrape_client.fetch_html_batch = fake_fetch_html_batch

    # Act
    result = crawler.run({"search_path": "/for-sale/property/london/", "max_listings": 1})

    # Assert
    assert result.status == "success"
    assert len(result.data) == 1
    raw = result.data[0]
    assert raw.external_id == "12345"
    assert raw.raw_data.get("html_snippet")

    # Act
    normalizer = OnTheMarketNormalizerAgent()
    normalized = normalizer.run({"raw_listings": result.data})

    # Assert
    assert normalized.status == "success"
    canonical = normalized.data[0]
    assert canonical.price == 275000.0
    assert canonical.surface_area_sqm is not None and canonical.surface_area_sqm > 0
    assert canonical.location is not None

    # Act
    listings_repo, persistence = _listing_store(tmp_path)
    saved = persistence.save_listings(normalized.data)

    # Assert
    assert saved == 1
    db_item = listings_repo.get_listing_by_id(canonical.id)
    assert db_item is not None
    assert db_item.price == canonical.price
    assert db_item.source_id == "onthemarket_uk"
    assert db_item.surface_area_sqm is not None and db_item.surface_area_sqm > 0


def test_crawl_normalize_persist__sreality_fixture_html__saves_listing_row(tmp_path):
    # Arrange
    search_html = Path("tests/resources/html/sreality_search.html").read_text(encoding="utf-8")
    detail_html = Path("tests/resources/html/sreality.html").read_text(encoding="utf-8")

    crawler = SrealityCrawlerAgent(
        config={
            "id": "sreality_cz",
            "base_url": "https://www.sreality.cz",
            "rate_limit": {"period_seconds": 0},
        },
        compliance=DummyCompliance(),
    )
    crawler.scrape_client.snapshot_service.save_snapshot = lambda **kwargs: None

    def fake_fetch_html(url, timeout_s=45.0, **_kwargs):
        if "/en/search/for-sale/apartments" in url:
            return search_html
        return None

    def fake_fetch_html_batch(urls, **_kwargs):
        results = []
        for url in urls:
            html = detail_html if "/en/detail/sale/apartment/2+1/prague/3233633884" in url else None
            results.append(FetchResult(url=url, html=html))
        return results

    crawler.scrape_client.fetch_html = fake_fetch_html
    crawler.scrape_client.fetch_html_batch = fake_fetch_html_batch

    # Act
    result = crawler.run({"start_url": "https://www.sreality.cz/en/search/for-sale/apartments", "max_listings": 1})

    # Assert
    assert result.status == "success"
    assert len(result.data) == 1
    raw = result.data[0]
    assert raw.external_id == "3233633884"
    assert raw.raw_data.get("html_snippet")

    # Act
    normalizer = SrealityNormalizerAgent()
    normalized = normalizer.run({"raw_listings": result.data})

    # Assert
    assert normalized.status == "success"
    canonical = normalized.data[0]
    assert canonical.price == 3200000.0
    assert canonical.surface_area_sqm is not None and canonical.surface_area_sqm > 0
    assert canonical.location is not None
    assert canonical.location.city.lower() in ("prague", "praha")

    # Act
    listings_repo, persistence = _listing_store(tmp_path)
    saved = persistence.save_listings(normalized.data)

    # Assert
    assert saved == 1
    db_item = listings_repo.get_listing_by_id(canonical.id)
    assert db_item is not None
    assert db_item.price == canonical.price
    assert db_item.source_id == "sreality_cz"
    assert db_item.country == "CZ"
    assert db_item.surface_area_sqm is not None and db_item.surface_area_sqm > 0


def test_crawl_normalize_persist__imovirtual_fixture_html__saves_listing_row(tmp_path):
    # Arrange
    search_html = Path("tests/resources/html/imovirtual_search.html").read_text(encoding="utf-8")
    detail_html = Path("tests/resources/html/imovirtual.html").read_text(encoding="utf-8")

    crawler = ImovirtualCrawlerAgent(
        config={
            "id": "imovirtual_pt",
            "base_url": "https://www.imovirtual.com",
            "rate_limit": {"period_seconds": 0},
        },
        compliance=DummyCompliance(),
    )
    crawler.scrape_client.snapshot_service.save_snapshot = lambda **kwargs: None

    def fake_fetch_html(url, timeout_s=45.0, **_kwargs):
        if "/comprar/apartamento/porto/" in url:
            return search_html
        return None

    def fake_fetch_html_batch(urls, **_kwargs):
        results = []
        for url in urls:
            html = detail_html if "IDABCD12" in url else fake_fetch_html(url)
            results.append(FetchResult(url=url, html=html))
        return results

    crawler.scrape_client.fetch_html = fake_fetch_html
    crawler.scrape_client.fetch_html_batch = fake_fetch_html_batch

    # Act
    result = crawler.run({"search_path": "/comprar/apartamento/porto/", "max_listings": 1})

    # Assert
    assert result.status == "success"
    assert len(result.data) == 1
    raw = result.data[0]
    assert raw.external_id == "IDABCD12"
    assert raw.raw_data.get("html_snippet")

    # Act
    normalizer = ImovirtualNormalizerAgent()
    normalized = normalizer.run({"raw_listings": result.data})

    # Assert
    assert normalized.status == "success"
    canonical = normalized.data[0]
    assert canonical.price == 448000.0
    assert canonical.surface_area_sqm is not None and canonical.surface_area_sqm > 0
    assert canonical.location is not None
    assert (canonical.location.city or "").lower() == "porto"

    # Act
    listings_repo, persistence = _listing_store(tmp_path)
    saved = persistence.save_listings(normalized.data)

    # Assert
    assert saved == 1
    db_item = listings_repo.get_listing_by_id(canonical.id)
    assert db_item is not None
    assert db_item.price == canonical.price
    assert db_item.source_id == "imovirtual_pt"
    assert db_item.country == "PT"
    assert db_item.surface_area_sqm is not None and db_item.surface_area_sqm > 0
