from __future__ import annotations

from src.listings.services import description_analyst as analyst_module
from src.listings.services.description_analyst import DescriptionAnalyst
from src.platform.settings import DescriptionAnalystConfig
from src.platform.utils.llm import LLMResponse


def test_description_analyst__builds_openai_compatible_request_and_parses_json(monkeypatch):
    calls = []

    def fake_complete_with_fallback(**kwargs):
        calls.append(kwargs)
        return LLMResponse(
            content='{"facts": {"has_elevator": true}, "financial_analysis": {"investor_sentiment": 0.4}}',
            model="gpt-4o-mini",
        )

    monkeypatch.setattr(analyst_module, "complete_with_fallback", fake_complete_with_fallback)

    analyst = DescriptionAnalyst(
        config=DescriptionAnalystConfig(
            provider="chatmock",
            api_base="http://127.0.0.1:8000/v1",
            api_key_env="CHATMOCK_API_KEY",
            model_name="gpt-4o-mini",
            min_description_length=10,
        )
    )

    result = analyst.analyze("Bright apartment with elevator and terrace.")

    assert result["facts"]["has_elevator"] is True
    assert calls[0]["models"] == ["gpt-4o-mini"]
    assert calls[0]["api_base"] == "http://127.0.0.1:8000/v1"
    assert calls[0]["response_format"] == {"type": "json_object"}
    assert calls[0]["messages"][0]["role"] == "system"
    assert "Return strict JSON only" in calls[0]["messages"][0]["content"]
    assert "Description:" in calls[0]["messages"][1]["content"]


def test_description_analyst__returns_empty_dict_for_malformed_json(monkeypatch):
    def fake_complete_with_fallback(**kwargs):
        return LLMResponse(content='{"facts":', model="gpt-4o-mini")

    monkeypatch.setattr(analyst_module, "complete_with_fallback", fake_complete_with_fallback)

    analyst = DescriptionAnalyst(
        config=DescriptionAnalystConfig(
            provider="chatmock",
            api_base="http://127.0.0.1:8000/v1",
            model_name="gpt-4o-mini",
            min_description_length=10,
        )
    )

    assert analyst.analyze("Needs renovation but has good upside.") == {}
