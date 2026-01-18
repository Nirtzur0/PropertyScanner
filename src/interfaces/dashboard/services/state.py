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
        state.deal_page_size = 12
    if "lens_expanded" not in state:
        state.lens_expanded = False

def log_orchestrator(role: str, text: str) -> None:
    """Appends a message to the orchestrator log in session state."""
    st.session_state.orchestrator_log.append({"role": role, "text": text})

def get_session_state(key: str, default: Any = None) -> Any:
    return st.session_state.get(key, default)

def set_session_state(key: str, value: Any) -> None:
    st.session_state[key] = value
