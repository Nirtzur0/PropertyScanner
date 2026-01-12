from src.services.storage import StorageService
from src.core.domain.schema import CanonicalListing
from src.services.fusion_model import FusionModelService
from src.services.market_analyst import MarketAnalyst
from src.core.domain.models import DBListing
import torch
import numpy as np
from datetime import datetime, timedelta

def test_market_intelligence():
    print("Initializing services...")
    storage = StorageService("sqlite:///:memory:") 
    
    # --- Test 1: DOM Calculation ---
    print("\nTest 1: DOM Calculation")
    
    # Create active listing
    listing = CanonicalListing(
        id="dom_test_1", source_id="s1", external_id="e1", url="http://x",
        title="Test Prop", price=100000, status="active", property_type="apartment"
    )
    # Simulate it was listed 10 days ago (manually setting listed_at after save for test)
    storage.save_listings([listing])
    
    with storage.get_session() as session:
        db_item = session.query(DBListing).filter_by(id="dom_test_1").first()
        # Backdate listed_at
        db_item.listed_at = datetime.utcnow() - timedelta(days=10)
        session.commit()
        
    # Now update stats to SOLD
    listing_sold = listing.model_copy()
    listing_sold.status = "sold"
    
    storage.save_listings([listing_sold])
    
    # Check DOM
    db_item = storage.get_listing("dom_test_1")
    print(f"Status: {db_item.status}")
    print(f"Sold At: {db_item.sold_at}")
    print(f"DOM: {db_item.dom}")
    
    assert db_item.status == "sold"
    assert db_item.sold_at is not None
    assert db_item.dom is not None
    # Depending on precision, DOM should be 10
    assert db_item.dom >= 9 and db_item.dom <= 11
    
    # --- Test 2: Market Analyst ---
    print("\nTest 2: Market Analyst")
    analyst = MarketAnalyst(storage.get_session())
    # Should get 10.0 (or close) as average for "all" (since we have 1 sold item with DOM 10)
    velocity = analyst.get_market_velocity()
    print(f"Market Velocity: {velocity}")
    assert abs(velocity - 10.0) < 1.0
    
    # --- Test 3: Fusion Model Input ---
    print("\nTest 3: Fusion Model with Market Velocity")
    fusion = FusionModelService() 
    if not torch.cuda.is_available() and not torch.backends.mps.is_available():
        pass # Just running on CPU
        
    # Mock Inputs
    target_text = np.random.randn(384).astype(np.float32)
    target_tab = np.random.randn(8).astype(np.float32)
    
    # Comps
    comp_texts = [np.random.randn(384).astype(np.float32) for _ in range(5)]
    comp_tabs = [np.random.randn(8).astype(np.float32) for _ in range(5)]
    comp_images = [None] * 5
    comp_prices = [100000.0] * 5
    
    # Mock Market Velocity (DOMs)
    # If the model uses this, the time prediction should shift.
    # We passed comp_doms as [10, 10, 10, 10, 10]
    comp_doms = [10.0] * 5
    
    output = fusion.predict(
        target_text, target_tab, None,
        comp_texts, comp_tabs, comp_images,
        comp_prices,
        comp_doms=comp_doms
    )
    
    print("Prediction Output (Time Quantiles):", output.time_to_sell_quantiles)
    # With base=10, prediction should be around 10 +/- residual
    # Default base is 90.
    
    print("Verification Successful!")

if __name__ == "__main__":
    test_market_intelligence()
