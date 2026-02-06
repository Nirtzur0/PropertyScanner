from unittest.mock import MagicMock

import pytest

from src.agentic.agents.evaluation_agent import EvaluationAgent, EvaluationRequest, PRESET_STRATEGIES
from src.platform.domain.schema import CanonicalListing, GeoLocation, PropertyType


@pytest.mark.parametrize("strategy", sorted(PRESET_STRATEGIES.keys()))
def test_evaluation_agent__preset_strategies__returns_scored_result(strategy: str):
    # Arrange
    agent = EvaluationAgent()

    agent._retriever = MagicMock()
    agent._retriever.retrieve_comps.return_value = []

    agent._encoder = MagicMock()
    agent._encoder.encode_single.return_value = [0.1] * 384

    agent._tab_encoder = MagicMock()
    agent._tab_encoder.encode.return_value = [0.0] * 8

    agent._fusion = MagicMock()
    fusion_out = MagicMock()
    fusion_out.price_quantiles = {"0.1": 350000.0, "0.5": 400000.0, "0.9": 450000.0}
    fusion_out.rent_quantiles = {"0.5": 2000.0}
    fusion_out.attention_weights = None
    agent._fusion.predict.return_value = fusion_out

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
            country="Test Country",
        ),
        bedrooms=2,
        bathrooms=1,
        surface_area_sqm=100.0,
        image_urls=["http://example.com/img.jpg"],
    )

    # Act
    result = agent.evaluate(EvaluationRequest(listing=listing, strategy=strategy))

    # Assert
    assert result.listing_id == listing.id
    assert 0.0 <= result.deal_score <= 1.0
    assert result.investment_thesis
    assert result.strategy_used == strategy

    assert set(result.fair_value_quantiles.keys()) == {"0.1", "0.5", "0.9"}
    assert result.fair_value_quantiles["0.1"] < result.fair_value_quantiles["0.5"] < result.fair_value_quantiles["0.9"]
