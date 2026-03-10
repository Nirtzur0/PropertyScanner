from __future__ import annotations

import pytest

from src.platform.settings import DescriptionAnalystConfig, LLMConfig
from src.platform.utils import llm as llm_module
from src.platform.utils.llm import LiteLLMClient


def _response(content: str) -> dict:
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def test_litellm_client__passes_chatmock_routing_and_preserves_ordered_fallback(monkeypatch):
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        if kwargs["model"] == "gpt-4o-mini":
            raise RuntimeError("primary failed")
        return _response('{"ok": true}')

    monkeypatch.setenv("CHATMOCK_API_KEY", "secret-token")
    monkeypatch.setattr(llm_module, "completion", fake_completion)

    client = LiteLLMClient(
        models=["gpt-4o-mini", "gpt-4.1-mini"],
        temperature=0.2,
        max_tokens=123,
        timeout_seconds=45,
        api_base="http://127.0.0.1:8000/v1",
        api_key_env="CHATMOCK_API_KEY",
    )

    response = client.invoke([{"role": "user", "content": "hello"}])

    assert response.model == "gpt-4.1-mini"
    assert response.content == '{"ok": true}'
    assert [call["model"] for call in calls] == ["gpt-4o-mini", "gpt-4.1-mini"]
    assert calls[0]["api_base"] == "http://127.0.0.1:8000/v1"
    assert calls[0]["api_key"] == "secret-token"
    assert calls[0]["messages"] == [{"role": "user", "content": "hello"}]


def test_litellm_client__raises_exhausted_error_when_all_models_fail(monkeypatch):
    def fake_completion(**kwargs):
        raise RuntimeError(f"failed:{kwargs['model']}")

    monkeypatch.setattr(llm_module, "completion", fake_completion)

    client = LiteLLMClient(
        models=["gpt-4o-mini", "gpt-4.1-mini"],
        temperature=0.0,
        max_tokens=50,
        timeout_seconds=10,
        api_base="http://127.0.0.1:8000/v1",
        api_key_env="CHATMOCK_API_KEY",
    )

    with pytest.raises(RuntimeError, match="llm_all_providers_failed:failed:gpt-4.1-mini"):
        client.invoke([{"role": "user", "content": "hello"}])


def test_config_models__preserve_legacy_ollama_fields():
    llm_config = LLMConfig(provider="ollama", models=["ollama/llama3:latest"])
    analyst_config = DescriptionAnalystConfig(
        provider="ollama",
        model_name="llama3:latest",
        base_url="http://localhost:11434",
    )

    assert llm_config.text_models == ["ollama/llama3:latest"]
    assert llm_config.models == ["ollama/llama3:latest"]
    assert analyst_config.api_base == "http://localhost:11434"
