from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image

from src.listings.services import description_analyst as analyst_module
from src.listings.services import vlm as vlm_module
from src.listings.services.feature_fusion import FeatureFusionService
from src.platform.settings import AppConfig, DescriptionAnalystConfig, VLMConfig
from src.platform.domain.schema import PropertyType
from src.platform.utils.llm import LLMResponse
from tests.helpers.factories import make_canonical_listing


class _Selector:
    def __init__(self, image: Image.Image):
        self._image = image

    def select(self, image_urls, max_images):
        candidate = SimpleNamespace(image=self._image, to_debug=lambda: {"kind": "selected"})
        return SimpleNamespace(selected=[candidate], rejected=[], errors=[])


@pytest.mark.integration
def test_feature_fusion__chatmock_text_path_updates_listing(monkeypatch):
    def fake_complete_with_fallback(**kwargs):
        return LLMResponse(
            content=(
                '{"facts": {"has_elevator": true, "floor": 3}, '
                '"financial_analysis": {"positive_drivers": ["terrace"], "investor_sentiment": 0.4}}'
            ),
            model="gpt-4o-mini",
        )

    monkeypatch.setattr(analyst_module, "complete_with_fallback", fake_complete_with_fallback)

    service = FeatureFusionService(
        app_config=AppConfig(
            description_analyst=DescriptionAnalystConfig(
                provider="chatmock",
                api_base="http://127.0.0.1:8000/v1",
                model_name="gpt-4o-mini",
                min_description_length=10,
            ),
            vlm=VLMConfig(provider="chatmock", api_base="http://127.0.0.1:8000/v1", supports_vision=True),
        )
    )
    listing = make_canonical_listing(
        property_type=PropertyType.APARTMENT,
        description="Sunny apartment with elevator and terrace.",
    )

    result = service.fuse(listing, run_vlm=False)

    assert result.has_elevator is True
    assert result.floor == 3
    assert result.text_sentiment == 0.4
    assert "PLUS:terrace" in result.tags


@pytest.mark.integration
def test_feature_fusion__chatmock_vision_path_populates_vlm_fields(monkeypatch):
    def fake_completion(**kwargs):
        return {"choices": [{"message": {"content": '{"visual_sentiment": 0.7, "summary": "bright and renovated"}'}}]}

    monkeypatch.setattr(vlm_module, "completion", fake_completion)

    service = FeatureFusionService(
        app_config=AppConfig(
            description_analyst=DescriptionAnalystConfig(
                provider="chatmock",
                api_base="http://127.0.0.1:8000/v1",
                model_name="gpt-4o-mini",
                min_description_length=500,
            ),
            vlm=VLMConfig(
                provider="chatmock",
                api_base="http://127.0.0.1:8000/v1",
                model="gpt-4o-mini",
                supports_vision=True,
            ),
        )
    )
    service.vlm.selector = _Selector(Image.new("RGB", (16, 16), color="white"))
    listing = make_canonical_listing(
        property_type=PropertyType.APARTMENT,
        description="too short",
        image_urls=["https://example.com/a.jpg"],
    )

    result = service.fuse(listing, run_vlm=True)

    assert result.image_sentiment == 0.7
    assert result.vlm_description == '{"visual_sentiment": 0.7, "summary": "bright and renovated"}'


@pytest.mark.integration
def test_feature_fusion__unsupported_chatmock_vision_fails_closed(monkeypatch):
    def fake_completion(**kwargs):
        raise RuntimeError("vision not supported for this model")

    monkeypatch.setattr(vlm_module, "completion", fake_completion)

    service = FeatureFusionService(
        app_config=AppConfig(
            description_analyst=DescriptionAnalystConfig(
                provider="chatmock",
                api_base="http://127.0.0.1:8000/v1",
                model_name="gpt-4o-mini",
                min_description_length=500,
            ),
            vlm=VLMConfig(
                provider="chatmock",
                api_base="http://127.0.0.1:8000/v1",
                model="gpt-4o-mini",
                supports_vision=True,
            ),
        )
    )
    service.vlm.selector = _Selector(Image.new("RGB", (16, 16), color="white"))
    listing = make_canonical_listing(
        property_type=PropertyType.APARTMENT,
        description="too short",
        image_urls=["https://example.com/a.jpg"],
    )

    result = service.fuse(listing, run_vlm=True)

    assert result.image_sentiment is None
    assert result.vlm_description is None
