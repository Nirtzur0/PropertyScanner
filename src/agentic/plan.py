from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

DEFAULT_MAX_STEPS = 16
DEFAULT_ACTION_BUDGETS: Dict[str, int] = {
    "preflight": 1,
    "build_market_data": 1,
    "build_index": 1,
    "train_model": 1,
    "crawl": 1,
    "normalize": 1,
    "enrich": 1,
    "filter": 1,
    "evaluate": 10,
    "report": 1,
}


class ActionType(str, Enum):
    PREFLIGHT = "preflight"
    BUILD_MARKET_DATA = "build_market_data"
    BUILD_INDEX = "build_index"
    TRAIN_MODEL = "train_model"
    CRAWL = "crawl"
    NORMALIZE = "normalize"
    ENRICH = "enrich"
    FILTER = "filter"
    EVALUATE = "evaluate"
    REPORT = "report"


class PlanStep(BaseModel):
    action: ActionType
    params: Dict[str, Any] = Field(default_factory=dict)
    rationale: Optional[str] = None


class PlanBudget(BaseModel):
    max_steps: int = DEFAULT_MAX_STEPS
    max_action_calls: Dict[str, int] = Field(default_factory=dict)


class AgentPlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: uuid4().hex)
    objective: str
    deterministic: bool = True
    budgets: PlanBudget = Field(default_factory=PlanBudget)
    steps: List[PlanStep] = Field(default_factory=list)


def default_action_budgets() -> Dict[str, int]:
    return dict(DEFAULT_ACTION_BUDGETS)


def _pipeline_steps(pipeline_status: Optional[Dict[str, Any]]) -> List[PlanStep]:
    if not pipeline_status:
        return []

    steps: List[PlanStep] = []
    if pipeline_status.get("needs_crawl"):
        steps.append(PlanStep(action=ActionType.PREFLIGHT))
        return steps
    if pipeline_status.get("needs_market_data"):
        steps.append(PlanStep(action=ActionType.BUILD_MARKET_DATA))
    if pipeline_status.get("needs_index"):
        steps.append(PlanStep(action=ActionType.BUILD_INDEX))
    if pipeline_status.get("needs_training"):
        steps.append(PlanStep(action=ActionType.TRAIN_MODEL))

    if not steps and pipeline_status.get("needs_refresh"):
        steps.append(PlanStep(action=ActionType.PREFLIGHT))

    return steps


def build_default_plan(
    query: str,
    target_areas: Optional[List[str]] = None,
    pipeline_status: Optional[Dict[str, Any]] = None,
) -> AgentPlan:
    pipeline_steps = _pipeline_steps(pipeline_status)
    steps = pipeline_steps + [
        PlanStep(action=ActionType.CRAWL),
        PlanStep(action=ActionType.NORMALIZE),
        PlanStep(action=ActionType.ENRICH),
        PlanStep(action=ActionType.FILTER),
        PlanStep(action=ActionType.EVALUATE),
        PlanStep(action=ActionType.REPORT),
    ]

    budgets = PlanBudget(
        max_steps=DEFAULT_MAX_STEPS,
        max_action_calls=default_action_budgets(),
    )

    return AgentPlan(
        objective=query,
        deterministic=True,
        budgets=budgets,
        steps=steps,
    )


def _plan_has_action(plan: AgentPlan, action: ActionType) -> bool:
    return any(step.action == action for step in plan.steps)


def _ensure_pipeline_steps(plan: AgentPlan, pipeline_status: Optional[Dict[str, Any]]) -> AgentPlan:
    if not pipeline_status or not pipeline_status.get("needs_refresh"):
        return plan

    if _plan_has_action(plan, ActionType.PREFLIGHT):
        return plan

    required_steps: List[PlanStep] = []
    if pipeline_status.get("needs_crawl"):
        required_steps.append(PlanStep(action=ActionType.PREFLIGHT))
        return plan.model_copy(update={"steps": required_steps + plan.steps})
    if pipeline_status.get("needs_market_data") and not _plan_has_action(plan, ActionType.BUILD_MARKET_DATA):
        required_steps.append(PlanStep(action=ActionType.BUILD_MARKET_DATA))
    if pipeline_status.get("needs_index") and not _plan_has_action(plan, ActionType.BUILD_INDEX):
        required_steps.append(PlanStep(action=ActionType.BUILD_INDEX))
    if pipeline_status.get("needs_training") and not _plan_has_action(plan, ActionType.TRAIN_MODEL):
        required_steps.append(PlanStep(action=ActionType.TRAIN_MODEL))

    if not required_steps:
        required_steps.append(PlanStep(action=ActionType.PREFLIGHT))

    if not required_steps:
        return plan

    return plan.model_copy(update={"steps": required_steps + plan.steps})


def _merge_budgets(budgets: PlanBudget) -> PlanBudget:
    max_steps = budgets.max_steps if budgets.max_steps and budgets.max_steps > 0 else DEFAULT_MAX_STEPS
    merged_calls = default_action_budgets()
    if budgets.max_action_calls:
        merged_calls.update(budgets.max_action_calls)
    return PlanBudget(max_steps=max_steps, max_action_calls=merged_calls)


def coerce_plan(
    plan: AgentPlan | Dict[str, Any],
    *,
    pipeline_status: Optional[Dict[str, Any]] = None,
) -> AgentPlan:
    if not isinstance(plan, AgentPlan):
        plan = AgentPlan.model_validate(plan)

    if not plan.deterministic:
        plan = plan.model_copy(update={"deterministic": True})

    plan = _ensure_pipeline_steps(plan, pipeline_status)
    merged_budgets = _merge_budgets(plan.budgets)

    max_steps = merged_budgets.max_steps
    steps = plan.steps[:max_steps]

    return plan.model_copy(update={"steps": steps, "budgets": merged_budgets})
