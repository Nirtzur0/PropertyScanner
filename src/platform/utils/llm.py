from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

import structlog
from litellm import completion

from src.platform.settings import AppConfig, LLMConfig
from src.platform.utils.config import load_app_config_safe

logger = structlog.get_logger(__name__)


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: Dict[str, Any] = field(default_factory=dict)
    raw: Any = None


def _normalize_messages(messages: Iterable[Any]) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role") or msg.get("type") or "user"
            content = msg.get("content")
            if content is None:
                content = str(msg)
            normalized.append({"role": str(role), "content": str(content)})
            continue

        content = getattr(msg, "content", None)
        if content is None:
            content = str(msg)

        role = getattr(msg, "role", None)
        if not role:
            msg_type = getattr(msg, "type", None)
            if not msg_type:
                msg_type = msg.__class__.__name__.lower()
            if msg_type in ("human", "humanmessage", "user"):
                role = "user"
            elif msg_type in ("system", "systemmessage"):
                role = "system"
            elif msg_type in ("ai", "assistant", "aimessage"):
                role = "assistant"
            else:
                role = "user"

        normalized.append({"role": str(role), "content": str(content)})
    return normalized


class LiteLLMClient:
    def __init__(
        self,
        *,
        models: List[str],
        temperature: float,
        max_tokens: int,
        timeout_seconds: int,
    ) -> None:
        cleaned = [m.strip() for m in models if m and str(m).strip()]
        self.models = cleaned
        self.temperature = float(temperature)
        self.max_tokens = int(max_tokens)
        self.timeout_seconds = int(timeout_seconds)

    def invoke(self, messages: Iterable[Any]) -> LLMResponse:
        if not self.models:
            raise RuntimeError("llm_models_empty")

        payload = _normalize_messages(messages)
        last_error: Optional[str] = None

        for model in self.models:
            try:
                response = completion(
                    model=model,
                    messages=payload,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    timeout=self.timeout_seconds,
                )
                response_data = response
                if not isinstance(response_data, dict):
                    response_data = getattr(response, "model_dump", lambda: {})()

                choices = response_data.get("choices") if isinstance(response_data, dict) else None
                if not choices and hasattr(response, "choices"):
                    choices = response.choices
                choice = choices[0] if choices else {}

                message = {}
                if isinstance(choice, dict):
                    message = choice.get("message", {}) or {}
                elif hasattr(choice, "message"):
                    message = choice.message or {}

                content = ""
                if isinstance(message, dict):
                    content = message.get("content", "")
                elif hasattr(message, "content"):
                    content = message.content or ""

                usage = {}
                if isinstance(response_data, dict):
                    usage = response_data.get("usage", {}) or {}
                elif hasattr(response, "usage"):
                    usage = response.usage or {}

                logger.info(
                    "litellm_completion",
                    model=model,
                    prompt_tokens=usage.get("prompt_tokens"),
                    completion_tokens=usage.get("completion_tokens"),
                    total_tokens=usage.get("total_tokens"),
                )
                return LLMResponse(content=content, model=model, usage=usage, raw=response)
            except Exception as exc:
                last_error = str(exc)
                logger.warning("litellm_completion_failed", model=model, error=last_error)

        raise RuntimeError(f"llm_all_providers_failed:{last_error}")


def get_llm(*, temperature: Optional[float] = None, app_config: Optional[AppConfig] = None) -> LiteLLMClient:
    app_config = app_config or load_app_config_safe()
    config: LLMConfig = app_config.llm
    if temperature is None:
        temperature = config.temperature
    return LiteLLMClient(
        models=config.models,
        temperature=temperature,
        max_tokens=config.max_tokens,
        timeout_seconds=config.timeout_seconds,
    )
