from __future__ import annotations

from importlib import import_module

import pytest


class _FakeScrapeClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _DummyCompliance:
    pass


@pytest.mark.parametrize(
    ("module_name", "class_name", "compliance_kwarg", "source_id", "expected_concurrency"),
    [
        ("src.listings.agents.crawlers.spain.pisos", "PisosCrawlerAgent", "compliance_manager", "pisos", 6),
        ("src.listings.agents.crawlers.uk.rightmove", "RightmoveCrawlerAgent", "compliance_manager", "rightmove_uk", 1),
        ("src.listings.agents.crawlers.uk.zoopla", "ZooplaCrawlerAgent", "compliance_manager", "zoopla_uk", 6),
        ("src.listings.agents.crawlers.czech_republic.sreality", "SrealityCrawlerAgent", "compliance", "sreality_cz", 4),
        ("src.listings.agents.crawlers.uk.onthemarket", "OnTheMarketCrawlerAgent", "compliance", "onthemarket_uk", 6),
        ("src.listings.agents.crawlers.italy.immobiliare", "ImmobiliareCrawlerAgent", "compliance_manager", "immobiliare_it", 6),
        ("src.listings.agents.crawlers.italy.casa_it", "CasaItCrawlerAgent", "compliance", "casa_it", 6),
        ("src.listings.agents.crawlers.uk.daft", "DaftCrawlerAgent", "compliance", "daft_ie", 4),
        ("src.listings.agents.crawlers.portugal.imovirtual", "ImovirtualCrawlerAgent", "compliance", "imovirtual_pt", 4),
        ("src.listings.agents.crawlers.poland.otodom", "OtodomCrawlerAgent", "compliance", "otodom_pl", 4),
        ("src.listings.agents.crawlers.spain.idealista", "IdealistaCrawlerAgent", "compliance_manager", "idealista", 6),
        ("src.listings.agents.crawlers.netherlands.funda", "FundaCrawlerAgent", "compliance", "funda_nl", 4),
        ("src.listings.agents.crawlers.netherlands.pararius", "ParariusCrawlerAgent", "compliance", "pararius_nl", 4),
        ("src.listings.agents.crawlers.usa.homes", "HomesCrawlerAgent", "compliance", "homes_us", 4),
        ("src.listings.agents.crawlers.usa.realtor", "RealtorCrawlerAgent", "compliance", "realtor_us", 4),
        ("src.listings.agents.crawlers.usa.redfin", "RedfinCrawlerAgent", "compliance", "redfin_us", 4),
        ("src.listings.agents.crawlers.france.seloger", "SeLogerCrawlerAgent", "compliance", "seloger_fr", 4),
        ("src.listings.agents.crawlers.germany.immowelt", "ImmoweltCrawlerAgent", "compliance", "immowelt_de", 4),
    ],
)
def test_crawler_init__uses_default_browser_concurrency_when_config_value_is_none(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    class_name: str,
    compliance_kwarg: str,
    source_id: str,
    expected_concurrency: int,
) -> None:
    module = import_module(module_name)
    monkeypatch.setattr(module, "ScrapeClient", _FakeScrapeClient)
    crawler_cls = getattr(module, class_name)

    crawler = crawler_cls(
        config={
            "id": source_id,
            "browser_max_concurrency": None,
            "rate_limit": {"period_seconds": 1},
        },
        **{compliance_kwarg: _DummyCompliance()},
    )

    assert crawler.scrape_client.kwargs["browser_max_concurrency"] == expected_concurrency
