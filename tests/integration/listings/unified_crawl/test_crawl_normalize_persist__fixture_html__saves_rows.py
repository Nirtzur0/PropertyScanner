import pytest
from pathlib import Path

from src.listings.agents.crawlers.uk.rightmove import RightmoveCrawlerAgent
from src.listings.agents.crawlers.uk.zoopla import ZooplaCrawlerAgent
from src.listings.agents.crawlers.italy.immobiliare import ImmobiliareCrawlerAgent
from src.listings.agents.processors.rightmove import RightmoveNormalizerAgent
from src.listings.agents.processors.zoopla import ZooplaNormalizerAgent
from src.listings.agents.processors.immobiliare import ImmobiliareNormalizerAgent
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


def test_rightmove_crawler_normalizer_storage(tmp_path):
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

    result = crawler.run(
        {"start_url": "https://www.rightmove.co.uk/property-for-sale/find.html?index=0"}
    )

    assert result.status == "success"
    assert len(result.data) == 1
    raw = result.data[0]
    assert raw.external_id == "12345678"
    assert raw.raw_data.get("html_snippet")

    normalizer = RightmoveNormalizerAgent()
    normalized = normalizer.run({"raw_listings": result.data})
    assert normalized.status == "success"
    canonical = normalized.data[0]
    assert canonical.price == 850000.0
    assert canonical.location is not None

    listings_repo, persistence = _listing_store(tmp_path)
    saved = persistence.save_listings(normalized.data)
    assert saved == 1
    db_item = listings_repo.get_listing_by_id(canonical.id)
    assert db_item is not None
    assert db_item.price == canonical.price
    assert db_item.city.lower() == "london"


def test_zoopla_crawler_normalizer_storage(tmp_path):
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

    result = crawler.run(
        {"start_url": "https://www.zoopla.co.uk/for-sale/property/manchester/"}
    )

    assert result.status == "success"
    assert len(result.data) == 1
    raw = result.data[0]
    assert raw.external_id == "98765432"
    assert raw.raw_data.get("html_snippet")

    normalizer = ZooplaNormalizerAgent()
    normalized = normalizer.run({"raw_listings": result.data})
    assert normalized.status == "success"
    canonical = normalized.data[0]
    assert canonical.price == 450000.0
    assert canonical.location is not None

    listings_repo, persistence = _listing_store(tmp_path)
    saved = persistence.save_listings(normalized.data)
    assert saved == 1
    db_item = listings_repo.get_listing_by_id(canonical.id)
    assert db_item is not None
    assert db_item.price == canonical.price
    assert db_item.city.lower() == "manchester"


def test_immobiliare_crawler_normalizer_storage(tmp_path):
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

    result = crawler.run({"listing_url": listing_url})

    assert result.status == "success"
    assert len(result.data) == 1
    raw = result.data[0]
    assert raw.external_id == "1357911"
    assert raw.raw_data.get("html_snippet")

    normalizer = ImmobiliareNormalizerAgent()
    normalized = normalizer.run({"raw_listings": result.data})
    assert normalized.status == "success"
    canonical = normalized.data[0]
    assert canonical.price == 620000.0
    assert canonical.location is not None

    listings_repo, persistence = _listing_store(tmp_path)
    saved = persistence.save_listings(normalized.data)
    assert saved == 1
    db_item = listings_repo.get_listing_by_id(canonical.id)
    assert db_item is not None
    assert db_item.price == canonical.price
