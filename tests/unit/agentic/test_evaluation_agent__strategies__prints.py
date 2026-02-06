
import sys
import os
from unittest.mock import MagicMock

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.agentic.agents.evaluation_agent import EvaluationAgent, EvaluationRequest, PRESET_STRATEGIES
from src.platform.domain.schema import CanonicalListing, GeoLocation, PropertyType

def test_strategies():
    # Mocking external services to avoid actual retrieval/inference
    agent = EvaluationAgent()
    agent._retriever = MagicMock()
    agent._retriever.retrieve_comps.return_value = []
    
    agent._encoder = MagicMock()
    agent._encoder.encode_single.return_value = [0.1] * 384

    agent._tab_encoder = MagicMock()
    agent._tab_encoder.encode.return_value = [0.0] * 8 # 8 dims for tabular
    
    agent._fusion = MagicMock()
    # Mock prediction: Fair value 400k, Rent 2000
    mock_fusion_output = MagicMock()
    mock_fusion_output.price_quantiles = {"0.1": 350000.0, "0.5": 400000.0, "0.9": 450000.0}
    mock_fusion_output.rent_quantiles = {"0.5": 2000.0}
    mock_fusion_output.attention_weights = None
    agent._fusion.predict.return_value = mock_fusion_output

    # Create a test listing
    listing = CanonicalListing(
        id="test1",
        source_id="manual",
        external_id="ext_test1",
        url="http://example.com/listing",
        property_type=PropertyType.APARTMENT,
        title="Test Property",
        price=350000.0,
        description="A great place",
        location=GeoLocation(
            lat=40.0, 
            lon=-3.0, 
            address_full="Test St", 
            city="Test City", 
            country="Test Country"
        ),
        bedrooms=2,
        surface_area_sqm=100.0,
        image_urls=["http://example.com/img.jpg"]
    )

    strategies = ["balanced", "bargain_hunter", "cash_flow_investor", "safe_bet"]
    
    print(f"{'Strategy':<20} | {'Score':<10} | {'Thesis'}")
    print("-" * 100)
    
    for strat in strategies:
        req = EvaluationRequest(listing=listing, strategy=strat)
        result = agent.evaluate(req)
        print(f"{strat:<20} | {result.deal_score:.4f}     | {result.investment_thesis}")

if __name__ == "__main__":
    test_strategies()
