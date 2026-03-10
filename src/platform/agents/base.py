from abc import ABC, abstractmethod
from typing import Any, Dict, List, Literal
from pydantic import BaseModel
import structlog

logger = structlog.get_logger()

class AgentResponse(BaseModel):
    status: Literal[
        "success",
        "failure",
        "partial",
        "blocked",
        "policy_blocked",
        "fetch_failed",
        "no_listings_found",
    ]
    data: Any
    metadata: Dict[str, Any] = {}
    errors: List[str] = []

class BaseAgent(ABC):
    def __init__(self, name: str, config: Dict[str, Any] = None):
        self.name = name
        self.config = config or {}
        self.logger = logger.bind(agent=name)

    @abstractmethod
    def run(self, input_payload: Dict[str, Any]) -> AgentResponse:
        """
        Main entry point for the agent.
        """
        pass
