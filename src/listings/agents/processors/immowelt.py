from typing import Any, Dict
from src.platform.agents.base import BaseAgent, AgentResponse

class ImmoweltNormalizerAgent(BaseAgent):
    """
    Dedicated normalizer for Immowelt (DE).
    Currently returns empty data to trigger LLM fallback.
    TODO: Implement specific HTML parsing.
    """
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(name="ImmoweltNormalizer", config=config)

    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        return AgentResponse(status="success", data=[])
