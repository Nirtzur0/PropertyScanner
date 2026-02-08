import sys
import os
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import html
import math
from typing import Optional, List, Dict, Any

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
os.environ["KMP_DUPLICATE_LIB_OK"] = "True"

from src.interfaces.dashboard.scout_logic import (
    DEFAULT_PRICE_RANGE,
    _build_deal_reasons,
    _format_deal_reasons,
    _format_intel_summary,
    _format_location,
    _format_ts,
    _resolve_profile_sort,
    _select_scout_picks,
)

# New Modular Imports
from src.interfaces.dashboard.utils.formatting import (
    escape_html,
    truncate_text,
    format_listing_description,
    format_vlm_notes,
    safe_num,
    normalize_text,
    format_list
)
from src.interfaces.dashboard.services.state import (
    ensure_session_defaults,
    log_orchestrator,
    get_session_state,
    set_session_state
)
from src.interfaces.dashboard.services.loaders import (
    get_services,
    load_filter_options,
    load_pipeline_status,
    rank_images,
    rank_images_sample,
    fetch_listings_dataframe
)
from src.interfaces.dashboard.components.visualizers import (
    build_lens_chips,
    resolve_plotly_selection
)
from src.interfaces.dashboard.components.cards import (
    build_scorecard_items,
    build_swot
)
from src.agentic.orchestrator import CognitiveOrchestrator
from src.agentic.memory import AgentMemoryStore

# Page Config
st.set_page_config(page_title="Property Scanner | The Scout", layout="wide", page_icon="🦅")

# Custom CSS
def load_css():
    css_path = os.path.join(os.path.dirname(__file__), "assets/style.css")
    if os.path.exists(css_path):
        with open(css_path) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

load_css()

# Initialize Services
storage, valuation, retriever, image_selector = get_services()

# Load Data Filters
cities, available_types, available_countries, cities_by_country = load_filter_options(storage)

# Initialize Session
ensure_session_defaults(cities, available_types, available_countries, cities_by_country)

def _safe_list(val):
    return val if isinstance(val, list) else []

def _is_finite_num(val: object) -> bool:
    try:
        num = float(val)  # type: ignore[arg-type]
    except Exception:
        return False
    return math.isfinite(num)

def _fmt_eur(val: object, digits: int = 0) -> str:
    num = safe_num(val, None)
    if num is None or not math.isfinite(float(num)):
        return "N/A"
    if digits <= 0:
        return f"{float(num):,.0f} €"
    return f"{float(num):,.{digits}f} €"

def _fmt_pct(val: object, digits: int = 1) -> str:
    num = safe_num(val, None)
    if num is None or not math.isfinite(float(num)):
        return "N/A"
    return f"{float(num):.{digits}%}"

def _resolve_target_areas(selected_city: str, selected_country: str) -> list[str]:
    if selected_city and selected_city != "All":
        return [selected_city]
    if selected_country and selected_country != "All":
        return [selected_country]
    return []

def _compute_map_view_state(map_data: pd.DataFrame, selected_title: Optional[str]):
    lat_series = pd.to_numeric(map_data["lat"], errors="coerce").dropna()
    lon_series = pd.to_numeric(map_data["lon"], errors="coerce").dropna()
    if selected_title:
        match = map_data[map_data["Title"] == selected_title]
        if not match.empty:
            lat_val = pd.to_numeric(match.iloc[0].get("lat"), errors="coerce")
            lon_val = pd.to_numeric(match.iloc[0].get("lon"), errors="coerce")
            if pd.notna(lat_val) and pd.notna(lon_val):
                return float(lat_val), float(lon_val), 14.0

    if lat_series.empty or lon_series.empty:
        return 40.4168, -3.7038, 5.0

    lat_min, lat_max = lat_series.quantile([0.05, 0.95]).tolist()
    lon_min, lon_max = lon_series.quantile([0.05, 0.95]).tolist()
    center_lat = float((lat_min + lat_max) / 2)
    center_lon = float((lon_min + lon_max) / 2)
    span = max(float(lat_max - lat_min), float(lon_max - lon_min), 0.01)
    zoom = math.log2(360.0 / span) - 1.0
    zoom = float(min(15.5, max(3.0, zoom)))
    return center_lat, center_lon, zoom


def _resolve_strategy(profile: str) -> str:
    mapping = {
        "Balanced": "balanced",
        "Yield": "cash_flow_investor",
        "Value": "bargain_hunter",
        "Momentum": "safe_bet",
    }
    return mapping.get(profile, "balanced")


def _plan_requires_confirmation(plan: Dict[str, Any]) -> bool:
    sensitive = {"preflight", "build_market_data", "build_index", "train_model"}
    steps = plan.get("steps") or []
    for step in steps:
        action = step.get("action") if isinstance(step, dict) else getattr(step, "action", None)
        if action in sensitive:
            return True
    return False


def _render_plan(plan_payload: Dict[str, Any]) -> None:
    steps = plan_payload.get("steps", [])
    for idx, step in enumerate(steps, start=1):
        action = step.get("action", "unknown")
        params = step.get("params", {})
        rationale = step.get("rationale")
        st.markdown(f"**{idx}. {action}**")
        if params:
            st.json(params)
        if rationale:
            st.caption(rationale)


def _render_ui_blocks(ui_blocks: List[Dict[str, Any]], data_df: pd.DataFrame) -> None:
    if not ui_blocks:
        return

    st.markdown("#### Agent Lens")
    for idx, block in enumerate(ui_blocks):
        block_type = block.get("type") or "unknown"
        title = block.get("title") or block_type.replace("_", " ").title()
        st.markdown(f"**{title}**")

        listing_ids = block.get("listing_ids") or []
        block_df = data_df[data_df["ID"].isin(listing_ids)].copy()
        if not block_df.empty and listing_ids:
            order = {str(listing_id): i for i, listing_id in enumerate(listing_ids)}
            block_df["__order"] = block_df["ID"].astype(str).map(order)
            block_df = block_df.sort_values("__order").drop(columns=["__order"])

        if block_type == "comparison_table":
            if block_df.empty:
                st.info("No listings matched the comparison block.")
            else:
                cols = block.get("columns") or []
                display_cols = ["Title"] + [c for c in cols if c in block_df.columns and c != "Title"]
                st.dataframe(block_df[display_cols], use_container_width=True)

        elif block_type == "deal_score_chart":
            if "Deal Score" in block_df.columns and not block_df.empty:
                fig = px.bar(block_df, x="Title", y="Deal Score")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No deal score data for chart.")

        elif block_type == "map_focus":
            if block_df.empty:
                st.info("No listings matched the map focus block.")
            else:
                st.caption("Map focus targets:")
                st.write(", ".join(block_df["Title"].tolist()))
                if st.button("Focus first on map", key=f"map_focus_{idx}"):
                    st.session_state.selected_title = block_df.iloc[0]["Title"]
                    st.rerun()

        else:
            st.caption("Unsupported block type.")


def _run_orchestrator(
    prompt: str,
    areas: List[str],
    strategy: str,
    plan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    orchestrator = CognitiveOrchestrator()
    result = orchestrator.run(prompt, areas=areas, plan=plan, strategy=strategy)

    st.session_state.agent_plan = result.get("plan") or plan
    st.session_state.agent_messages = result.get("messages", [])
    st.session_state.agent_report = result.get("final_report") or ""
    st.session_state.agent_evaluations = result.get("evaluations", [])
    st.session_state.agent_error = result.get("error")
    st.session_state.agent_trace = result.get("trace", [])
    st.session_state.agent_ui_blocks = result.get("ui_blocks", [])
    st.session_state.agent_quality_checks = result.get("quality_checks", [])
    st.session_state.agent_run_id = result.get("run_id")

    if result.get("plan_status") in {"failed", "budget_exhausted"}:
        errors = result.get("errors") or []
        st.session_state.agent_error = ", ".join(errors) if errors else "plan_failed"

    return result

# --- Sidebar ---
with st.sidebar:
    st.markdown("### 🔭 The Scout V2")
    
    # Mode Selection
    raw_mode = st.radio(
        "Mode", 
        ["Assisted", "Autonomous"], 
        index=0 if st.session_state.autonomy_mode == "Assisted" else 1,
        help="Assisted: AI suggests. Autonomous: AI acts.",
        label_visibility="collapsed"
    )
    if raw_mode != st.session_state.autonomy_mode:
        st.session_state.autonomy_mode = raw_mode
        st.rerun()

    st.divider()

    # Geo Filters
    sel_country = st.selectbox(
        "Country", 
        ["All"] + available_countries, 
        index=0 if st.session_state.selected_country == "All" else (available_countries.index(st.session_state.selected_country) + 1)
    )
    if sel_country != st.session_state.selected_country:
        st.session_state.selected_country = sel_country
        st.session_state.selected_city = "All"
        st.rerun()

    city_options = (
        cities 
        if st.session_state.selected_country == "All" 
        else cities_by_country.get(st.session_state.selected_country, [])
    )
    
    sel_city = st.selectbox(
        "City", 
        ["All"] + city_options, 
        index=0 if st.session_state.selected_city == "All" else (city_options.index(st.session_state.selected_city) + 1)
    )
    if sel_city != st.session_state.selected_city:
        st.session_state.selected_city = sel_city
        st.rerun()

    # Property Type
    sel_types = st.multiselect(
        "Property Type", 
        available_types, 
        default=st.session_state.selected_types
    )
    if sel_types != st.session_state.selected_types:
        st.session_state.selected_types = sel_types

    # Price Range
    min_p, max_p = st.slider(
        "Budget", 
        min_value=50000, 
        max_value=2000000, 
        value=st.session_state.price_range, 
        step=25000, 
        format="€%d"
    )
    if (min_p, max_p) != st.session_state.price_range:
        st.session_state.price_range = (min_p, max_p)

    st.divider()

# --- Pipeline Status ---
pipeline_status = load_pipeline_status()
pipeline_needs_refresh = bool(pipeline_status.get("needs_refresh"))
pipeline_error = pipeline_status.get("error")
pipeline_listings = int(pipeline_status.get("listings_count", 0) or 0)
pipeline_listings_at = _format_ts(pipeline_status.get("listings_last_seen"))

if pipeline_error:
    pipeline_state_text = "Degraded"
    pipeline_badge = "Error"
else:
    pipeline_state_text = "Refresh due" if pipeline_needs_refresh else "Live"
    pipeline_badge = "Refresh" if pipeline_needs_refresh else "Live"

# --- Main Layout ---
left_col = st.container()

selected_country = st.session_state.selected_country
selected_city = st.session_state.selected_city
selected_types = st.session_state.selected_types
min_price, max_price = st.session_state.price_range

with left_col:
    # Lens HUD
    lens_chips = build_lens_chips(
        selected_country,
        selected_city,
        selected_types,
        min_price,
        max_price,
        DEFAULT_PRICE_RANGE,
        available_types,
    )
    chips_html = "".join([f"<span class='lens-chip'>{html.escape(c)}</span>" for c in lens_chips])
    
    hud_cols = st.columns([5, 1], gap="small", vertical_alignment="center")
    with hud_cols[0]:
        st.markdown(
            f"""
            <div class="lens-hud-bar">
                <span class="lens-hud-title">Lens</span>
                <div class="lens-hud-chips">{chips_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with hud_cols[1]:
        toggle_label = "Hide" if st.session_state.lens_expanded else "Tune"
        if st.button(toggle_label, key="lens_toggle", use_container_width=True):
            st.session_state.lens_expanded = not st.session_state.lens_expanded
            st.rerun()

    if st.session_state.lens_expanded:
        # Quick filter controls directly in main view
        lens_cols = st.columns([1.1, 1.1, 1.6])
        with lens_cols[0]:
            st.selectbox(
                "Country", ["All"] + available_countries, key="selected_country_dupe",
                index=0 if selected_country == "All" else available_countries.index(selected_country) + 1,
                on_change=lambda: setattr(st.session_state, 'selected_country', st.session_state.selected_country_dupe)
            )

        with st.expander("System status", expanded=False):
            st.caption(f"Pipeline: {pipeline_state_text}")
            st.progress(100 if pipeline_badge == "Live" else 50)
            st.text(f"Listings tracked: {pipeline_listings}")
            st.text(f"Listings updated: {pipeline_listings_at}")

# --- Load Data ---
with st.spinner("Scouting listings..."):
    try:
        df = fetch_listings_dataframe(
            storage, valuation, retriever,
            selected_country, selected_city, selected_types,
            max_listings=st.session_state.max_listings
        )
    except Exception as exc:
        st.error(f"Failed to load listings: {exc}")
        st.stop()

if df.empty:
    st.markdown(
        "<div class='empty-state'><h2>No listings yet</h2><p>Run a crawl or backfill to load listings.</p></div>",
        unsafe_allow_html=True,
    )
    st.stop()

# --- Normalize & Filter ---
for col in ["Yield %", "Deal Score", "Value Delta %", "Momentum %", "Area Sentiment", 
            "Price Return 12m %", "Total Return 12m %", "Price-to-Rent (yrs)", "Market P/R (yrs)"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

filtered_df = df.copy()
filtered_df = filtered_df[
    (filtered_df["Price"] >= min_price)
    & (filtered_df["Price"] <= max_price)
]

scout_profile = st.session_state.scout_profile
sort_key, ascending = _resolve_profile_sort(scout_profile)
if sort_key not in filtered_df.columns:
    sort_key = "Deal Score"
filtered_df = filtered_df.sort_values(by=sort_key, ascending=ascending)

filtered_df["Why"] = filtered_df.apply(lambda row: _format_deal_reasons(row, scout_profile), axis=1)
filtered_df["Intel Summary"] = filtered_df.apply(lambda row: _format_intel_summary(row, scout_profile), axis=1)
scout_picks = _select_scout_picks(filtered_df, scout_profile, max_picks=4)

if "Images" in filtered_df.columns:
    deal_df = filtered_df[filtered_df["Images"].apply(lambda value: len(_safe_list(value)) > 0)].copy()
else:
    deal_df = filtered_df.iloc[0:0].copy()

if not deal_df.empty:
    titles = list(deal_df["Title"].unique())
    if st.session_state.selected_title not in titles:
        st.session_state.selected_title = titles[0]
elif not filtered_df.empty:
    titles = list(filtered_df["Title"].unique())
    if st.session_state.selected_title not in titles:
        st.session_state.selected_title = titles[0]
else:
    st.session_state.selected_title = None

# --- Scout Command Center ---
st.markdown('<div id="scout-command-center"></div>', unsafe_allow_html=True)
with st.form("scout_command_center", clear_on_submit=False):
    st.markdown('<span id="scout-form-marker"></span>', unsafe_allow_html=True)
    input_cols = st.columns([3, 1], vertical_alignment="bottom")
    with input_cols[0]:
        # Check for preset prompt
        default_prompt = st.session_state.get("scout_prompt_preset", "")
        # Reset preset after consumption to avoid sticking
        if default_prompt:
             del st.session_state.scout_prompt_preset
        
        prompt_val = default_prompt
        prompt = st.text_input(
            "Scout Command", 
            value=prompt_val,
            key="orchestrator_input", 
            placeholder="Ask the Scout... (⌘K)", 
            label_visibility="collapsed"
        )
    with input_cols[1]:
        submitted = st.form_submit_button("Scout it", use_container_width=True)

    # Examples (Inside the floating panel)
    if not submitted and not st.session_state.agent_plan:
        st.caption("Try an example:")
        example_cols = st.columns(2)
        examples = [
            "💰 High Yield deals",
            "📉 Undervalued gems",
            "🚀 High Momentum",
            "📍 Only Barcelona"
        ]
        chosen_example = None
        for i, ex in enumerate(examples):
            with example_cols[i % 2]:
                # In a form, buttons sumbit the form. We check which one was clicked.
                if st.form_submit_button(ex, use_container_width=True):
                    chosen_example = ex
                    submitted = True
        
        if chosen_example:
            prompt = chosen_example

if submitted and prompt:
    log_orchestrator("user", prompt)
    target_areas = _resolve_target_areas(selected_city, selected_country)
    if not target_areas:
        # Default to all cities if no specific area is selected
        target_areas = cities
        st.toast(f"Scouting across {len(cities)} cities...", icon="🌍")

    if not target_areas:
        st.session_state.agent_error = "target_area_required"
        st.error("No cities available to scout. Please check your data.")
        st.stop()

    strategy = _resolve_strategy(scout_profile)
    orchestrator = CognitiveOrchestrator()
    try:
        plan_payload = orchestrator.plan(prompt, areas=target_areas, strategy=strategy)
    except Exception as exc:
        st.session_state.agent_error = str(exc)
        st.error(st.session_state.agent_error)
        st.stop()

    st.session_state.agent_pending_plan = plan_payload
    st.session_state.agent_pending_prompt = prompt
    st.session_state.agent_pending_areas = target_areas
    st.session_state.agent_pending_strategy = strategy
    st.session_state.agent_requires_approval = _plan_requires_confirmation(plan_payload)

    if not st.session_state.agent_requires_approval:
        result = _run_orchestrator(prompt, target_areas, strategy, plan_payload)

        if st.session_state.agent_report:
            log_orchestrator("assistant", st.session_state.agent_report)

        if st.session_state.agent_error:
            st.error(st.session_state.agent_error)
            st.stop()

        top_eval = None
        if st.session_state.agent_evaluations:
            top_eval = max(
                st.session_state.agent_evaluations,
                key=lambda item: item.get("deal_score", 0),
            )
        top_listing_id = top_eval.get("listing_id") if isinstance(top_eval, dict) else None
        if top_listing_id:
            matched = filtered_df[filtered_df["ID"] == top_listing_id]
            if matched.empty:
                st.error("Top evaluated listing is not in the current lens.")
                st.stop()
            st.session_state.selected_title = matched.iloc[0]["Title"]
        st.session_state.agent_pending_plan = None
        st.session_state.agent_requires_approval = False
        st.rerun()

pending_plan = st.session_state.agent_pending_plan
if pending_plan and st.session_state.agent_requires_approval:
    st.markdown("#### Approval Required")
    _render_plan(pending_plan)

    action_cols = st.columns([1, 1])
    with action_cols[0]:
        if st.button("Approve & Run Plan", use_container_width=True):
            result = _run_orchestrator(
                st.session_state.agent_pending_prompt,
                st.session_state.agent_pending_areas,
                st.session_state.agent_pending_strategy,
                pending_plan,
            )
            if st.session_state.agent_report:
                log_orchestrator("assistant", st.session_state.agent_report)

            st.session_state.agent_pending_plan = None
            st.session_state.agent_requires_approval = False

            if st.session_state.agent_error:
                st.error(st.session_state.agent_error)
                st.stop()

            top_eval = None
            if st.session_state.agent_evaluations:
                top_eval = max(
                    st.session_state.agent_evaluations,
                    key=lambda item: item.get("deal_score", 0),
                )
            top_listing_id = top_eval.get("listing_id") if isinstance(top_eval, dict) else None
            if top_listing_id:
                matched = filtered_df[filtered_df["ID"] == top_listing_id]
                if matched.empty:
                    st.error("Top evaluated listing is not in the current lens.")
                    st.stop()
                st.session_state.selected_title = matched.iloc[0]["Title"]
            st.rerun()
    with action_cols[1]:
        if st.button("Cancel", use_container_width=True):
            st.session_state.agent_pending_plan = None
            st.session_state.agent_requires_approval = False
            st.rerun()

if st.session_state.agent_report:
    st.markdown("#### Agent Report")
    st.write(st.session_state.agent_report)

if st.session_state.agent_quality_checks:
    with st.expander("Quality Gates", expanded=False):
        for check in st.session_state.agent_quality_checks:
            status = check.get("status")
            icon = "✅" if status == "pass" else "⚠️"
            st.write(f"{icon} **{check.get('check')}** — {check.get('detail')}")

if st.session_state.agent_ui_blocks:
    _render_ui_blocks(st.session_state.agent_ui_blocks, filtered_df)

if st.session_state.agent_plan:
    with st.expander("Agent Plan", expanded=False):
        plan_payload = st.session_state.agent_plan or {}
        _render_plan(plan_payload)

if st.session_state.agent_trace:
    with st.expander("Execution Trace", expanded=False):
        trace_df = pd.DataFrame(st.session_state.agent_trace)
        if not trace_df.empty:
            display_cols = ["action", "status", "duration_ms", "error"]
            display_cols = [c for c in display_cols if c in trace_df.columns]
            st.dataframe(trace_df[display_cols], use_container_width=True)
        else:
            st.caption("No trace data.")

if st.session_state.agent_messages:
    with st.expander("Agent Messages", expanded=False):
        for message in st.session_state.agent_messages:
            role = message.get("role", "agent")
            content = message.get("content", "")
            st.markdown(f"**{role}** — {content}")

with st.expander("Agent Memory", expanded=False):
    try:
        memory = AgentMemoryStore()
        recent_runs = memory.list_recent(limit=5)
        if not recent_runs:
            st.caption("No saved agent runs yet.")
        else:
            for run in recent_runs:
                status_icon = "✅" if run.get("status") == "success" else "⚠️"
                areas = ", ".join(run.get("target_areas") or [])
                st.markdown(f"{status_icon} **{run.get('query')}** — {areas}")
                if run.get("summary"):
                    st.caption(run.get("summary"))
    except Exception as exc:
        st.caption(f"Memory unavailable: {exc}")

# --- Layout ---
left_panel, right_panel = st.columns([1.35, 1], gap="large")

with left_panel:
    panel_choice = st.radio(
        "Panel",
        ["📋 Deal Flow", "📑 Memo"],
        index=0 if st.session_state.left_panel_view == "📋 Deal Flow" else 1,
        horizontal=True,
        label_visibility="collapsed",
        key="left_panel_view",
    )

    if panel_choice == "📋 Deal Flow":
        st.markdown("### 📋 Deal Flow")
        # Pagination & View Logic
        total_deals = len(deal_df)
        page_size = max(1, int(st.session_state.deal_page_size))
        total_pages = max(1, int(math.ceil(total_deals / page_size))) if total_deals > 0 else 1
        current_page = min(max(1, int(st.session_state.deal_page)), total_pages)
        
        start_idx = (current_page - 1) * page_size
        end_idx = min(start_idx + page_size, total_deals)

        # Controls Toolbar
        ctrl_cols = st.columns([1.5, 1, 0.7, 0.9, 0.7, 2.5], vertical_alignment="center")
        
        # 1. View Mode
        with ctrl_cols[0]:
            deal_view = st.radio(
                "View", ["Grid", "List"],
                index=0 if st.session_state.deal_view_mode == "Grid" else 1,
                horizontal=True,
                label_visibility="collapsed",
                key="deal_view_ctrl"
            )
            if deal_view != st.session_state.deal_view_mode:
                st.session_state.deal_view_mode = deal_view
                st.rerun()

        # 2. Page Size
        with ctrl_cols[1]:
            page_size_sel = st.selectbox(
                "Size", [6, 8, 10, 12, 24],
                index=[6, 8, 10, 12, 24].index(st.session_state.deal_page_size) if st.session_state.deal_page_size in [6, 8, 10, 12, 24] else 1,
                label_visibility="collapsed",
                key="page_size_ctrl"
            )
            if page_size_sel != st.session_state.deal_page_size:
                st.session_state.deal_page_size = page_size_sel
                st.session_state.deal_page = 1
                st.rerun()

        # 3. Prev
        with ctrl_cols[2]:
            if st.button("◀", disabled=current_page <= 1, use_container_width=True):
                st.session_state.deal_page = max(1, current_page - 1)
                st.rerun()

        # 4. Page Selector
        with ctrl_cols[3]:
            page_sel = st.selectbox(
                "Page", list(range(1, total_pages + 1)),
                index=current_page - 1,
                label_visibility="collapsed",
                key="page_sel_ctrl"
            )
            if page_sel != current_page:
                st.session_state.deal_page = page_sel
                st.rerun()

        # 5. Next
        with ctrl_cols[4]:
            if st.button("▶", disabled=current_page >= total_pages, use_container_width=True):
                st.session_state.deal_page = min(total_pages, current_page + 1)
                st.rerun()

        # 6. Status Info
        with ctrl_cols[5]:
            if total_deals > 0:
                st.caption(f"{start_idx + 1}-{end_idx} of {total_deals} • {sort_key}")
            else:
                st.caption("No matches")

        if total_deals == 0:
            st.info("No listings with photos match the current lens.")
        else:
            page_df = deal_df.iloc[start_idx:end_idx]

            if st.session_state.deal_view_mode == "Grid":
                grid_cols = st.columns(2, gap="large")
                for idx, row in page_df.reset_index(drop=True).iterrows():
                    col = grid_cols[idx % 2]
                    with col:
                        imgs = _safe_list(row.get("Images"))
                        ranked = rank_images_sample(imgs, sample_size=4, _image_selector=image_selector)
                        if ranked:
                            st.image(ranked[0], use_container_width=True)
                        st.markdown(f"**{row['Title']}**")
                        st.caption(f"{row['City']}, {row['Country']} • {_fmt_eur(row.get('Price'))}")
                        why = row.get("Why")
                        if isinstance(why, str) and why:
                            st.caption(why)
                        if st.button("Memo", key=f"memo_grid_{row['ID']}", use_container_width=True):
                            st.session_state.selected_title = row["Title"]
                            st.session_state.left_panel_view = "📑 Memo"
                            st.rerun()
                        st.divider()
            else:
                for _, row in page_df.iterrows():
                    row_cols = st.columns([1, 3, 1])
                    with row_cols[0]:
                        imgs = _safe_list(row.get("Images"))
                        ranked = rank_images_sample(imgs, sample_size=3, _image_selector=image_selector)
                        if ranked:
                            st.image(ranked[0], use_container_width=True)
                    with row_cols[1]:
                        st.markdown(f"**{row['Title']}**")
                        st.caption(f"{row['City']}, {row['Country']} • {_fmt_eur(row.get('Price'))}")
                        why = row.get("Why")
                        if isinstance(why, str) and why:
                            st.caption(why)
                    with row_cols[2]:
                        if st.button("Memo", key=f"memo_list_{row['ID']}", use_container_width=True):
                            st.session_state.selected_title = row["Title"]
                            st.session_state.left_panel_view = "📑 Memo"
                            st.rerun()
                    st.divider()
    else:
        st.markdown("### 📑 Memo")
        if st.session_state.selected_title:
            selected_items = filtered_df[filtered_df["Title"] == st.session_state.selected_title]
            if selected_items.empty:
                st.info("Selected listing is not in the current lens.")
                st.stop()
            item = selected_items.iloc[0]
            st.markdown(f"**{item['Title']}**")
            st.caption(f"{item['City']}, {item['Country']} • {_fmt_eur(item.get('Price'))}")
            intel = item.get("Intel Summary")
            if isinstance(intel, str) and intel:
                st.caption(intel)

            imgs = _safe_list(item.get("Images"))
            ranked = rank_images(imgs, _image_selector=image_selector)
            if ranked:
                st.image(ranked[0], use_container_width=True)

            st.markdown("#### Scorecard")
            items = build_scorecard_items(item)
            for i in items:
                icon = "✅" if i["positive"] else "⚠️"
                st.write(f"{icon} **{i['label']}**: {i['detail']}")

            ask_price = item.get("Price")
            fair_value = item.get("Fair Value")
            value_delta = item.get("Value Delta %")
            st.metric("Asking Price", _fmt_eur(ask_price))
            if _is_finite_num(fair_value):
                delta_text = _fmt_pct(value_delta, digits=1) if _is_finite_num(value_delta) else None
                st.metric("Fair Value", _fmt_eur(fair_value), delta=delta_text)
            else:
                st.metric("Fair Value", "N/A")

            st.markdown("#### SWOT")
            swot = build_swot(item, [], "")
            for k, v in swot.items():
                st.write(f"**{k}**: {', '.join(v)}")
        else:
            st.info("Select a listing in Deal Flow to open its memo.")

    st.markdown("### 🔎 Insights")
    insight_options = ["🧪 Signal Lab", "🎯 Scout Picks", "🧭 Pipeline Status"]
    insight_choice = st.selectbox(
        "Insights",
        insight_options,
        index=insight_options.index(st.session_state.insight_view)
        if st.session_state.insight_view in insight_options
        else 0,
        key="insight_view",
        label_visibility="collapsed",
    )

    if insight_choice == "🧪 Signal Lab":
        required_cols = ["Yield %", "Value Delta %", "ID", "Title"]
        missing = [c for c in required_cols if c not in filtered_df.columns]
        if missing:
            st.info(f"Signal Lab unavailable (missing: {', '.join(missing)}).")
        else:
            plot_df = filtered_df.dropna(subset=["Yield %", "Value Delta %"]).copy()
            if plot_df.empty:
                st.info("No signal points available for the current lens.")
            else:
                scatter_kwargs: Dict[str, Any] = dict(
                    data_frame=plot_df,
                    x="Yield %",
                    y="Value Delta %",
                    hover_data=["Title"],
                )
                if "Deal Score" in plot_df.columns:
                    scatter_kwargs["color"] = "Deal Score"
                if "Price" in plot_df.columns:
                    scatter_kwargs["size"] = "Price"

                fig = px.scatter(**scatter_kwargs)
                selection = st.plotly_chart(
                    fig, on_select="rerun", selection_mode="lasso", use_container_width=True
                )
                selected = resolve_plotly_selection(selection, plot_df, id_col="ID")
                if not selected.empty:
                    st.dataframe(selected, use_container_width=True)
                else:
                    st.info("Select points to drill down.")

    elif insight_choice == "🎯 Scout Picks":
        if not scout_picks:
            st.info("Scout picks are empty for this lens.")
        else:
            for pick in scout_picks:
                row = pick["row"]
                st.caption(pick["label"])
                st.markdown(f"**{row['Title']}**")
                st.caption(_format_location(row.get("City"), row.get("Country")))
                why = row.get("Why")
                if isinstance(why, str) and why:
                    st.caption(why)
                if st.button("Open memo", key=f"pick_{row['ID']}"):
                    st.session_state.selected_title = row["Title"]
                    st.session_state.left_panel_view = "📑 Memo"
                    st.rerun()
                st.divider()

    else:
        st.metric("Pipeline State", pipeline_state_text)
        st.caption(f"Listings tracked: {pipeline_listings}")
        st.caption(f"Listings updated: {pipeline_listings_at}")
        if pipeline_error:
            st.error(pipeline_error)
        elif pipeline_needs_refresh:
            st.warning("Pipeline refresh recommended.")
        else:
            st.success("Pipeline healthy.")

with right_panel:
    st.markdown("### 🗺 Atlas")
    import pydeck as pdk
    map_data = filtered_df.dropna(subset=["lat", "lon"]).copy()
    if map_data.empty:
        st.info("No listings to map.")
    else:
        map_data["lat"] = pd.to_numeric(map_data["lat"], errors="coerce")
        map_data["lon"] = pd.to_numeric(map_data["lon"], errors="coerce")
        map_data = map_data.dropna(subset=["lat", "lon"])
        if map_data.empty:
            st.info("No listings to map.")
        else:
            st.caption(f"{len(map_data)} listings on map")
            center_lat, center_lon, zoom = _compute_map_view_state(
                map_data, st.session_state.selected_title
            )
            map_is_dark = str(st.get_option("theme.base") or "").lower() == "dark"
            tooltip_style = {
                "color": "#f8f6f0" if map_is_dark else "#1a1a1a",
                "backgroundColor": "rgba(15, 18, 24, 0.9)" if map_is_dark else "rgba(255, 255, 255, 0.95)",
            }

            selected_title = st.session_state.selected_title
            map_data["radius"] = np.where(map_data["Title"] == selected_title, 360, 220)
            if selected_title:
                map_data["color"] = map_data["Title"].apply(
                    lambda title: [255, 255, 255, 230] if title == selected_title else [255, 140, 0, 180]
                )
            else:
                map_data["color"] = [[255, 140, 0, 180]] * len(map_data)
            map_data["price_label"] = map_data["Price"].apply(
                lambda value: f"€{value:,.0f}" if pd.notna(value) else "N/A"
            )
            if "Deal Score" in map_data.columns:
                map_data["score_label"] = map_data["Deal Score"].apply(
                    lambda value: f"{value:.2f}" if pd.notna(value) else "N/A"
                )
            else:
                map_data["score_label"] = "N/A"

            layer = pdk.Layer(
                "ScatterplotLayer",
                data=map_data,
                get_position="[lon, lat]",
                get_fill_color="color",
                get_line_color="[255, 255, 255, 120]",
                get_radius="radius",
                pickable=True,
                line_width_min_pixels=1,
                filled=True,
                stroked=True,
            )
            carto_light = "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json"
            carto_dark = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
            st.pydeck_chart(
                pdk.Deck(
                    # Use CARTO basemaps to avoid requiring a Mapbox token.
                    map_style=carto_dark if map_is_dark else carto_light,
                    initial_view_state=pdk.ViewState(
                        latitude=center_lat,
                        longitude=center_lon,
                        zoom=zoom,
                        pitch=45,
                        bearing=0,
                    ),
                    layers=[layer],
                    tooltip={
                        "html": (
                            "<b>{Title}</b><br/>"
                            "{City}, {Country}<br/>"
                            "Price: {price_label}<br/>"
                            "Deal Score: {score_label}"
                        ),
                        "style": tooltip_style,
                    },
                ),
                use_container_width=True,
            )
