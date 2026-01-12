from unittest.mock import patch, MagicMock
from src.services.storage import StorageService
from src.core.domain.schema import CanonicalListing, GeoLocation
from src.core.domain.models import DBListing
import json

def test_description_analysis():
    print("Initializing StorageService (with integrated DescriptionAnalyst)...")
    storage = StorageService("sqlite:///:memory:") 
    
    # Mock Ollama response
    mock_response = {
        "response": json.dumps({
            "facts": {
                "has_elevator": True,
                "has_pool": False,
                "floor": 5
            },
            "sentiment_score": 0.8,
            "summary": "Great renovated apartment."
        })
    }
    
    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = mock_response
        
        # Create a listing with description but missing elevator/floor info
        listing = CanonicalListing(
            id="desc_test_123",
            source_id="src_1",
            external_id="ext_1",
            url="http://example.com/desc",
            title="Luxury Flat",
            description="Amazing 5th floor apartment with elevator. Stunning views.", # Should trigger extraction
            price=500000,
            property_type="apartment",
            # has_elevator and floor are None/Default
        )
        
        print("Saving listing...")
        storage.save_listings([listing])
        
        print("Retrieving listing from DB...")
        db_item = storage.get_listing("desc_test_123")
        
        # Verify Sentiment Persistence
        print(f"Sentiment Score: {db_item.sentiment_score}")
        assert db_item.sentiment_score == 0.8, f"Expected 0.8, got {db_item.sentiment_score}"
        
        # Verify Fact Extraction (Elevator)
        print(f"Has Elevator: {db_item.has_elevator}")
        assert db_item.has_elevator is True, "Elevator fact failed to extract/persist!"
        
        # Verify Fact Extraction (Floor)
        print(f"Floor: {db_item.floor}")
        assert db_item.floor == 5, "Floor fact failed to extract/persist!"

        print("Verification Successful!")

if __name__ == "__main__":
    test_description_analysis()
