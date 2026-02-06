
import unittest
from unittest.mock import MagicMock, patch
import numpy as np
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.valuation.services.retrieval import CompRetriever, IndexedListing
from src.platform.domain.schema import CanonicalListing, GeoLocation

class TestCompRetrieverLogic(unittest.TestCase):
    def setUp(self):
        self.model_patcher = patch("src.valuation.services.retrieval.SentenceTransformer")
        mock_model_cls = self.model_patcher.start()
        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 384
        mock_model.encode.return_value = np.zeros(384).astype("float32")
        mock_model_cls.return_value = mock_model

        # Create a mock retriever that bypasses legacy index loading
        self.retriever = CompRetriever(index_path="non_existent", metadata_path="non_existent")
        
        # Mock the index and model
        self.retriever.index = MagicMock()
        self.retriever.model = mock_model
        
        # Mock listings database
        # We will populate self.retriever.listings with diverse options
        self.setup_mock_listings()
        
        # Mock index search to return ALL our listings (index 0 to N)
        # So we can test the filtering logic in Python
        n_listings = len(self.retriever.listings)
        
        # Return indices [0, 1, ... N] and distances [0.1, 0.2, ... small]
        # We make distances small so they all look "semantically similar"
        # This isolates the structural filtering logic
        indices = np.array([[i for i in range(n_listings)]]).astype('int64')
        distances = np.array([[0.1 * i for i in range(n_listings)]]).astype('float32')
        
        self.retriever.index.ntotal = n_listings
        self.retriever.index.search.return_value = (distances, indices)

    def tearDown(self):
        self.model_patcher.stop()

    def setup_mock_listings(self):
        self.retriever.listings = {}
        
        # Target will be: 2 Bed, 80sqm
        
        # 0: Perfect Match (2 Bed, 80sqm)
        self.add_mock_listing(0, "Perfect", 2, 80.0)
        
        # 1: Good Match (2 Bed, 85sqm)
        self.add_mock_listing(1, "Good Size", 2, 85.0)
        
        # 2: Acceptable (1 Bed, 70sqm) - Within +/- 1 bed
        self.add_mock_listing(2, "Small Bed", 1, 70.0)
        
        # 3: Acceptable (3 Bed, 90sqm) - Within +/- 1 bed
        self.add_mock_listing(3, "Big Bed", 3, 90.0)
        
        # 4: BAD: Studio (0 Bed) - Too small vs 2 bed
        self.add_mock_listing(4, "Studio", 0, 40.0)
        
        # 5: BAD: Villa (5 Bed) - Too big
        self.add_mock_listing(5, "Villa", 5, 200.0)
        
        # 6: BAD: Tiny (2 Bed, 30sqm) - Strange data, maybe garage?
        # Ratio 30/80 = 0.37 -> Should be rejected (< 0.8)
        self.add_mock_listing(6, "Tiny", 2, 30.0)
        
        # 7: BAD: Huge (2 Bed, 200sqm) - Luxury loft?
        # Ratio 200/80 = 2.5 -> Should be rejected (> 1.2)
        self.add_mock_listing(7, "Huge", 2, 200.0)

    def add_mock_listing(self, int_id, title, beds, sqm):
        self.retriever.listings[int_id] = IndexedListing(
            id=f"id_{int_id}",
            int_id=int_id,
            title=title,
            price=100000.0,
            listing_type="sale",
            surface_area_sqm=sqm,
            bedrooms=beds,
            lat=40.0, lon=-3.0, # Same location
            snapshot_id="snap"
        )
        
    def test_logical_filtering(self):
        target = CanonicalListing(
            id="target",
            source_id="manual",
            external_id="ext_target",
            url="http://example.com/target",
            title="Target Property",
            price=150000.0,
            bedrooms=2,
            surface_area_sqm=80.0,
            location=GeoLocation(lat=40.0, lon=-3.0, address_full="Here", city="Madrid", country="Spain"),
            property_type="apartment"
        )
        
        comps = self.retriever.retrieve_comps(
            target=target, 
            k=4, # Request exactly the number of valid matches to verify strictness
            max_radius_km=5.0,
            strict_filters=True
        )
        
        comp_ids = [c.id for c in comps]
        print(f"Found comps: {comp_ids}")
        
        # MUST HAVE (The 4 valid matches)
        self.assertIn("id_0", comp_ids)
        self.assertIn("id_1", comp_ids)
        self.assertIn("id_2", comp_ids)
        self.assertIn("id_3", comp_ids)
        
        # MUST NOT HAVE (The 4 invalid matches)
        # Since k=4, and we have 4 valid ones, these should not be reached
        self.assertNotIn("id_4", comp_ids)
        self.assertNotIn("id_5", comp_ids)
        self.assertNotIn("id_6", comp_ids)
        self.assertNotIn("id_7", comp_ids)
        
        print("Strict filtering test passed!")

    def test_relaxation(self):
        # Case where NO strict matches exist
        # Only have ID 4 (Studio) and ID 5 (Villa)
        self.retriever.listings = {}
        self.add_mock_listing(4, "Studio", 0, 40.0)
        self.add_mock_listing(5, "Villa", 5, 200.0)
        
        # Need to fix index/search mock to match new listings count
        self.retriever.index.ntotal = 2 # only 4 and 5
        # IDs are 4 and 5
        indices = np.array([[4, 5]]).astype('int64')
        distances = np.array([[0.1, 0.2]]).astype('float32') 
        self.retriever.index.search.return_value = (distances, indices)
        
        target = CanonicalListing(
            id="target",
            source_id="mn",
            external_id="ex",
            url="http://x",
            title="T",
            price=1,
            bedrooms=2,
            surface_area_sqm=80.0, 
            location=GeoLocation(lat=40.0, lon=-3.0, address_full="Here", city="M", country="S"),
            property_type="apartment" # Fixed validation error
        )
        
        # However, Strategy 3 is "Desperate" (Fruit Salad) -> Pure vector search
        # So it SHOULD return them eventually if K is not met.
        
        comps = self.retriever.retrieve_comps(target=target, k=2)
        comp_ids = [c.id for c in comps]
        
        print(f"Relaxed/Desperate comps: {comp_ids}")
        self.assertIn("id_4", comp_ids, "Should fall back to studio")
        self.assertIn("id_5", comp_ids, "Should fall back to villa")

if __name__ == "__main__":
    unittest.main()
