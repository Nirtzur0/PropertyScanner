import unittest
from pathlib import Path

from src.listings.agents.processors.rightmove import RightmoveNormalizerAgent
from src.platform.domain.schema import RawListing


class TestRightmoveNormalizerAgent(unittest.TestCase):
    def test_parse_item_extracts_fields(self):
        agent = RightmoveNormalizerAgent()
        fixture = Path("tests/resources/html/rightmove.html").read_text(encoding="utf-8")

        raw_listing = RawListing(
            source_id="rightmove_uk",
            external_id="12345678",
            url="https://www.rightmove.co.uk/properties/12345678",
            raw_data={"html_snippet": fixture, "is_detail_page": True},
            fetched_at="2024-06-01T00:00:00Z",
        )

        canonical = agent._parse_item(raw_listing)

        self.assertIsNotNone(canonical)
        self.assertEqual(canonical.price, 850000.0)
        self.assertEqual(canonical.currency.value, "GBP")
        self.assertEqual(canonical.bedrooms, 4)
        self.assertEqual(canonical.bathrooms, 2)
        self.assertIsNotNone(canonical.location)
        self.assertEqual(canonical.location.city.lower(), "london")


if __name__ == "__main__":
    unittest.main()
