"""Deprecated shim. Use src.listings.scraping instead."""

from src.listings.scraping.client import FetchResult, LinkExtractorSpec, ScrapeClient


CrawlerToolbox = ScrapeClient

__all__ = ["CrawlerToolbox", "ScrapeClient", "LinkExtractorSpec", "FetchResult"]
