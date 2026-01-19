from typing import Any, Dict

from src.platform.agents.base import BaseAgent, AgentResponse


class GenericNormalizerAgent(BaseAgent):
    """
    A generic normalizer that returns no data, relying on the LLMFallbackNormalizer
    to perform extraction via LLM if enabled.
    """
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(name="GenericNormalizer", config=config)

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        # We intentionally return empty data so that the fallback mechanism
        # (LLMFallbackNormalizer) picks up all raw listings.
        return AgentResponse(status="success", data=[])
