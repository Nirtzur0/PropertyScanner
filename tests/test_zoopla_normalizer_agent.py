import unittest
from pathlib import Path

from src.agents.processors.zoopla import ZooplaNormalizerAgent
from src.core.domain.schema import RawListing


class TestZooplaNormalizerAgent(unittest.TestCase):
    def test_parse_item_extracts_fields(self):
        agent = ZooplaNormalizerAgent()
        fixture = Path("tests/resources/html/zoopla.html").read_text(encoding="utf-8")

        raw_listing = RawListing(
            source_id="zoopla_uk",
            external_id="98765432",
            url="https://www.zoopla.co.uk/for-sale/details/98765432/",
            raw_data={"html_snippet": fixture, "is_detail_page": True},
            fetched_at="2024-05-15T00:00:00Z",
        )

        canonical = agent._parse_item(raw_listing)

        self.assertIsNotNone(canonical)
        self.assertEqual(canonical.price, 450000.0)
        self.assertEqual(canonical.currency.value, "GBP")
        self.assertEqual(canonical.bedrooms, 2)
        self.assertEqual(canonical.bathrooms, 1)
        self.assertIsNotNone(canonical.location)
        self.assertEqual(canonical.location.city.lower(), "manchester")


if __name__ == "__main__":
    unittest.main()
