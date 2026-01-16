import unittest
from pathlib import Path

from src.agents.processors.immobiliare import ImmobiliareNormalizerAgent
from src.core.domain.schema import RawListing


class TestImmobiliareNormalizerAgent(unittest.TestCase):
    def test_parse_item_extracts_fields(self):
        agent = ImmobiliareNormalizerAgent()
        fixture = Path("tests/resources/html/immobiliare.html").read_text(encoding="utf-8")

        raw_listing = RawListing(
            source_id="immobiliare_it",
            external_id="1357911",
            url="https://www.immobiliare.it/annunci/1357911/",
            raw_data={"html_snippet": fixture, "is_detail_page": True},
            fetched_at="2024-04-10T00:00:00Z",
        )

        canonical = agent._parse_item(raw_listing)

        self.assertIsNotNone(canonical)
        self.assertEqual(canonical.price, 620000.0)
        self.assertEqual(canonical.currency.value, "EUR")
        self.assertEqual(canonical.surface_area_sqm, 95.0)
        self.assertIsNotNone(canonical.location)


if __name__ == "__main__":
    unittest.main()
