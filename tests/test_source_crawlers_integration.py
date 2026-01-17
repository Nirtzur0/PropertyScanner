from pathlib import Path

from src.listings.agents.crawlers.rightmove import RightmoveCrawlerAgent
from src.listings.agents.crawlers.zoopla import ZooplaCrawlerAgent
from src.listings.agents.crawlers.immobiliare import ImmobiliareCrawlerAgent
from src.listings.agents.processors.rightmove import RightmoveNormalizerAgent
from src.listings.agents.processors.zoopla import ZooplaNormalizerAgent
from src.listings.agents.processors.immobiliare import ImmobiliareNormalizerAgent
from src.listings.repositories.listings import ListingsRepository
from src.listings.services.listing_persistence import ListingPersistenceService


class DummyCompliance:
    def check_and_wait(self, url: str, rate_limit_seconds: float = 1.0) -> bool:
        return True


class FakeResponse:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


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
    crawler.snapshot_service.save_snapshot = lambda **kwargs: None

    def fake_get(url, timeout=30.0, **_kwargs):
        if "find.html" in url:
            return FakeResponse(200, search_html)
        if "/properties/12345678" in url:
            return FakeResponse(200, detail_html)
        return FakeResponse(404, "")

    crawler.session.get = fake_get

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
    crawler.snapshot_service.save_snapshot = lambda **kwargs: None

    def fake_get(url, timeout=30.0, **_kwargs):
        if "/details/98765432" in url:
            return FakeResponse(200, detail_html)
        if "property" in url or "for-sale" in url:
            return FakeResponse(200, search_html)
        return FakeResponse(404, "")

    crawler.session.get = fake_get

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


def test_immobiliare_crawler_normalizer_storage(tmp_path, monkeypatch):
    detail_html = Path("tests/resources/html/immobiliare.html").read_text(encoding="utf-8")
    listing_url = "https://www.immobiliare.it/annunci/1357911/"

    class DummyLocator:
        def all(self):
            return []

        def get_attribute(self, _name):
            return None

        def count(self):
            return 0

        @property
        def first(self):
            return self

        def is_visible(self):
            return False

        def click(self, *args, **kwargs):
            return None

    class DummyPage:
        def __init__(self, html_map):
            self._html_map = html_map
            self._current_url = None

        def goto(self, url, timeout=30000, wait_until="domcontentloaded"):
            self._current_url = url

        def content(self):
            return self._html_map.get(self._current_url, "")

        def get_by_text(self, *args, **kwargs):
            return DummyLocator()

        def wait_for_selector(self, *args, **kwargs):
            return None

        def locator(self, *args, **kwargs):
            return DummyLocator()

    class DummyContext:
        def __init__(self, html_map):
            self._html_map = html_map

        def new_page(self):
            return DummyPage(self._html_map)

    class DummyBrowser:
        def __init__(self, html_map):
            self._html_map = html_map

        def new_context(self, **kwargs):
            return DummyContext(self._html_map)

        def close(self):
            return None

    class DummyChromium:
        def __init__(self, html_map):
            self._html_map = html_map

        def launch(self, headless=True):
            return DummyBrowser(self._html_map)

    class DummyPlaywright:
        def __init__(self, html_map):
            self.chromium = DummyChromium(html_map)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class DummyStealth:
        def apply_stealth_sync(self, page):
            return None

    import src.listings.agents.crawlers.immobiliare as immobiliare_module

    monkeypatch.setattr(
        immobiliare_module,
        "sync_playwright",
        lambda: DummyPlaywright({listing_url: detail_html}),
    )
    monkeypatch.setattr(immobiliare_module, "Stealth", DummyStealth)
    monkeypatch.setattr(immobiliare_module.time, "sleep", lambda *_: None)

    crawler = ImmobiliareCrawlerAgent(
        config={
            "id": "immobiliare_it",
            "base_url": "https://www.immobiliare.it",
            "rate_limit": {"period_seconds": 0},
        },
        compliance_manager=DummyCompliance(),
    )
    crawler.snapshot_service.save_snapshot = lambda **kwargs: None

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
