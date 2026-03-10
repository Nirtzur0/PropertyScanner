from __future__ import annotations

import os
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


def _coerce_message_content(content: Any) -> Any:
    if content is None:
        return ""
    if isinstance(content, list):
        return content
    return str(content)


def _extract_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                elif item.get("type") == "output_text":
                    parts.append(str(item.get("text", "")))
        return "\n".join(part for part in parts if part)
    return str(content or "")


def _normalize_messages(messages: Iterable[Any]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role") or msg.get("type") or "user"
            content = _coerce_message_content(msg.get("content", str(msg)))
            normalized.append({"role": str(role), "content": content})
            continue

        content = getattr(msg, "content", None)
        content = _coerce_message_content(content if content is not None else str(msg))

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

        normalized.append({"role": str(role), "content": content})
    return normalized


def build_completion_kwargs(
    *,
    model: str,
    messages: Iterable[Any],
    temperature: float,
    max_tokens: int,
    timeout_seconds: int,
    api_base: Optional[str] = None,
    api_key_env: Optional[str] = None,
    response_format: Optional[Dict[str, Any]] = None,
    extra_kwargs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": _normalize_messages(messages),
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        "timeout": int(timeout_seconds),
    }
    if api_base:
        kwargs["api_base"] = api_base
    api_key = os.getenv(api_key_env, "").strip() if api_key_env else ""
    if api_key:
        kwargs["api_key"] = api_key
    if response_format:
        kwargs["response_format"] = response_format
    if extra_kwargs:
        kwargs.update(extra_kwargs)
    return kwargs


def _response_to_llm_response(*, model: str, response: Any) -> LLMResponse:
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

    content: Any = ""
    if isinstance(message, dict):
        content = message.get("content", "")
    elif hasattr(message, "content"):
        content = message.content or ""

    usage = {}
    if isinstance(response_data, dict):
        usage = response_data.get("usage", {}) or {}
    elif hasattr(response, "usage"):
        usage = response.usage or {}

    return LLMResponse(
        content=_extract_content_text(content),
        model=model,
        usage=usage,
        raw=response,
    )


def complete_with_fallback(
    *,
    models: List[str],
    messages: Iterable[Any],
    temperature: float,
    max_tokens: int,
    timeout_seconds: int,
    api_base: Optional[str] = None,
    api_key_env: Optional[str] = None,
    response_format: Optional[Dict[str, Any]] = None,
    extra_kwargs: Optional[Dict[str, Any]] = None,
) -> LLMResponse:
    cleaned_models = [m.strip() for m in models if m and str(m).strip()]
    if not cleaned_models:
        raise RuntimeError("llm_models_empty")

    last_error: Optional[str] = None
    for model in cleaned_models:
        try:
            response = completion(
                **build_completion_kwargs(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout_seconds=timeout_seconds,
                    api_base=api_base,
                    api_key_env=api_key_env,
                    response_format=response_format,
                    extra_kwargs=extra_kwargs,
                )
            )
            parsed = _response_to_llm_response(model=model, response=response)
            logger.info(
                "litellm_completion",
                model=model,
                api_base=api_base,
                prompt_tokens=parsed.usage.get("prompt_tokens"),
                completion_tokens=parsed.usage.get("completion_tokens"),
                total_tokens=parsed.usage.get("total_tokens"),
            )
            return parsed
        except Exception as exc:
            last_error = str(exc)
            logger.warning("litellm_completion_failed", model=model, api_base=api_base, error=last_error)

    raise RuntimeError(f"llm_all_providers_failed:{last_error}")


class LiteLLMClient:
    def __init__(
        self,
        *,
        models: List[str],
        temperature: float,
        max_tokens: int,
        timeout_seconds: int,
        api_base: Optional[str] = None,
        api_key_env: Optional[str] = None,
    ) -> None:
        cleaned = [m.strip() for m in models if m and str(m).strip()]
        self.models = cleaned
        self.temperature = float(temperature)
        self.max_tokens = int(max_tokens)
        self.timeout_seconds = int(timeout_seconds)
        self.api_base = api_base
        self.api_key_env = api_key_env

    def invoke(self, messages: Iterable[Any]) -> LLMResponse:
        return complete_with_fallback(
            models=self.models,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout_seconds=self.timeout_seconds,
            api_base=self.api_base,
            api_key_env=self.api_key_env,
        )


def get_llm(*, temperature: Optional[float] = None, app_config: Optional[AppConfig] = None) -> LiteLLMClient:
    app_config = app_config or load_app_config_safe()
    config: LLMConfig = app_config.llm
    if temperature is None:
        temperature = config.temperature
    return LiteLLMClient(
        models=config.text_models,
        temperature=temperature,
        max_tokens=config.max_tokens,
        timeout_seconds=config.timeout_seconds,
        api_base=config.api_base,
        api_key_env=config.api_key_env,
    )
