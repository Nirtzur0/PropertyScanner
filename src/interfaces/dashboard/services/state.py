from __future__ import annotations
import streamlit as st
import random
from typing import List, Dict, Any, Tuple

from src.interfaces.dashboard.scout_logic import (
    DEFAULT_PRICE_RANGE,
    VIEW_OPTIONS,
)

def ensure_session_defaults(
    available_cities: List[str], 
    available_types: List[str], 
    available_countries: List[str], 
    cities_by_country: Dict[str, List[str]]
) -> None:
    """Initializes session state with default values if not present."""
    state = st.session_state
    if "selected_country" not in state:
        state.selected_country = "All"
    if state.selected_country != "All" and state.selected_country not in available_countries:
        state.selected_country = "All"

    city_pool = (
        available_cities
        if state.selected_country == "All"
        else cities_by_country.get(state.selected_country, [])
    )
    if "selected_city" not in state:
        state.selected_city = "All"
    if state.selected_city != "All" and state.selected_city not in city_pool:
        state.selected_city = "All"

    if "selected_types" not in state:
        state.selected_types = list(available_types)
    else:
        state.selected_types = [t for t in state.selected_types if t in available_types]
        if not state.selected_types and available_types:
            state.selected_types = list(available_types)

    if "price_range" not in state:
        state.price_range = DEFAULT_PRICE_RANGE
    if "max_listings" not in state:
        state.max_listings = 300
    if "sort_by" not in state:
        state.sort_by = "Deal Score"
    if "sort_order" not in state:
        state.sort_order = "Desc"
    if "scout_profile" not in state:
        state.scout_profile = "Balanced"
    if "active_view" not in state:
        state.active_view = VIEW_OPTIONS[0]
    if "selected_title" not in state:
        state.selected_title = None
    if "orchestrator_log" not in state:
        state.orchestrator_log = []
    if "orchestrator_input" not in state:
        state.orchestrator_input = ""
    if "autonomy_mode" not in state:
        state.autonomy_mode = "Assisted"
    if "allow_refresh" not in state:
        state.allow_refresh = True
    if "pending_actions" not in state:
        state.pending_actions = []
    if "ai_response" not in state:
        state.ai_response = ""
    if "last_plan" not in state:
        state.last_plan = []
    if "deal_page" not in state:
        state.deal_page = 1
    if "deal_page_size" not in state:
        state.deal_page_size = 8
    if "deal_view_mode" not in state:
        state.deal_view_mode = "Grid"
    if "left_panel_view" not in state:
        state.left_panel_view = "📋 Deal Flow"
    if "agent_plan" not in state:
        state.agent_plan = None
    if "agent_messages" not in state:
        state.agent_messages = []
    if "agent_report" not in state:
        state.agent_report = ""
    if "agent_evaluations" not in state:
        state.agent_evaluations = []
    if "agent_error" not in state:
        state.agent_error = None
    if "agent_trace" not in state:
        state.agent_trace = []
    if "agent_ui_blocks" not in state:
        state.agent_ui_blocks = []
    if "agent_quality_checks" not in state:
        state.agent_quality_checks = []
    if "agent_run_id" not in state:
        state.agent_run_id = None
    if "agent_pending_plan" not in state:
        state.agent_pending_plan = None
    if "agent_pending_prompt" not in state:
        state.agent_pending_prompt = ""
    if "agent_pending_areas" not in state:
        state.agent_pending_areas = []
    if "agent_pending_strategy" not in state:
        state.agent_pending_strategy = "balanced"
    if "agent_requires_approval" not in state:
        state.agent_requires_approval = False
    if "lens_expanded" not in state:
        state.lens_expanded = False
    if "insight_view" not in state:
        state.insight_view = "🧪 Signal Lab"

def log_orchestrator(role: str, text: str) -> None:
    """Appends a message to the orchestrator log in session state."""
    st.session_state.orchestrator_log.append({"role": role, "text": text})

def get_session_state(key: str, default: Any = None) -> Any:
    return st.session_state.get(key, default)

def set_session_state(key: str, value: Any) -> None:
    st.session_state[key] = value
