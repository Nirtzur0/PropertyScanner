from __future__ import annotations

from types import SimpleNamespace
import sys

import pytest
from PIL import Image

from src.listings.services import vlm as vlm_module
from src.listings.services.vlm import VLMImageDescriber, VisionBackendUnsupportedError
from src.platform.settings import VLMConfig


class _Selector:
    def __init__(self, image: Image.Image):
        self._image = image

    def select(self, image_urls, max_images):
        candidate = SimpleNamespace(image=self._image, to_debug=lambda: {"kind": "selected"})
        return SimpleNamespace(selected=[candidate], rejected=[], errors=[])


def test_vlm_describer__builds_multimodal_payload_for_chatmock(monkeypatch):
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return {"choices": [{"message": {"content": '{"visual_sentiment": 0.6}'}}]}

    monkeypatch.setattr(vlm_module, "completion", fake_completion)

    describer = VLMImageDescriber(
        config=VLMConfig(
            provider="chatmock",
            api_base="http://127.0.0.1:8000/v1",
            api_key_env="CHATMOCK_API_KEY",
            model="gpt-4o-mini",
            supports_vision=True,
        ),
        image_selector=_Selector(Image.new("RGB", (16, 16), color="white")),
    )

    result = describer.describe_images(["https://example.com/image.jpg"])

    assert result == '{"visual_sentiment": 0.6}'
    assert calls[0]["api_base"] == "http://127.0.0.1:8000/v1"
    content = calls[0]["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_vlm_describer__raises_explicit_error_when_backend_rejects_vision(monkeypatch):
    def fake_completion(**kwargs):
        raise RuntimeError("vision not supported for this model")

    monkeypatch.setattr(vlm_module, "completion", fake_completion)

    describer = VLMImageDescriber(
        config=VLMConfig(
            provider="chatmock",
            api_base="http://127.0.0.1:8000/v1",
            model="gpt-4o-mini",
            supports_vision=True,
        ),
        image_selector=_Selector(Image.new("RGB", (16, 16), color="white")),
    )

    with pytest.raises(VisionBackendUnsupportedError, match="vision not supported"):
        describer.describe_images(["https://example.com/image.jpg"])


def test_vlm_describer__keeps_ollama_mode_working_when_explicitly_configured(monkeypatch):
    fake_ollama = SimpleNamespace(
        list=lambda: SimpleNamespace(models=[SimpleNamespace(model="llava:latest")]),
        generate=lambda **kwargs: {"response": '{"visual_sentiment": 0.1}'},
    )
    monkeypatch.setitem(sys.modules, "ollama", fake_ollama)

    describer = VLMImageDescriber(
        config=VLMConfig(
            provider="ollama",
            api_base="http://localhost:11434",
            api_key_env="",
            model="llava",
            supports_vision=True,
        ),
        image_selector=_Selector(Image.new("RGB", (16, 16), color="white")),
    )

    assert describer.describe_images(["https://example.com/image.jpg"]) == '{"visual_sentiment": 0.1}'
