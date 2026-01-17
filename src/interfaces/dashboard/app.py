import sys
import os

# Add project root to path (robustly, for when running from various dirs)
# src/interfaces/dashboard/app.py -> ../.. -> project_root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Prevent Mac OMP segfaults (Critical for PyDeck/Torch on Mac)
os.environ["KMP_DUPLICATE_LIB_OK"] = "True"

import streamlit as st
import pandas as pd
import numpy as np

from src.interfaces.api.pipeline import PipelineAPI
from src.listings.services.listing_adapter import db_listing_to_canonical
from src.platform.pipeline.state import PipelineStateService
from src.platform.domain.models import DBListing
from src.platform.domain.schema import DealAnalysis, ValuationProjection

# Page Config
st.set_page_config(page_title="Property Scanner | The Scout", layout="wide", page_icon="🦅")


# Custom CSS
def load_css():
    with open(os.path.join(os.path.dirname(__file__), "assets/style.css")) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


load_css()


@st.cache_resource
def get_services():
    api = PipelineAPI()
    return api.storage, api.valuation, api.retriever


storage, valuation, retriever = get_services()


@st.cache_data(ttl=600)
def load_filter_options():
    session = storage.get_session()
    try:
        cities = [c[0] for c in session.query(DBListing.city).distinct().all() if c[0]]
        cities = sorted(set(cities))
        types = [t[0] for t in session.query(DBListing.property_type).distinct().all() if t[0]]
        types = sorted(set(types))
    finally:
        session.close()
    return cities, types


@st.cache_data(ttl=120)
def load_pipeline_status():
    try:
        return PipelineStateService().snapshot().to_dict()
    except Exception as e:
        return {"error": str(e), "needs_refresh": False, "reasons": ["status_unavailable"]}


def _format_ts(value):
    if not value:
        return "unknown"
    dt = pd.to_datetime(value, errors="coerce")
    if pd.isna(dt):
        return "unknown"
    # Ensure input is timezone-aware UTC
    if getattr(dt, "tzinfo", None) is None:
        dt = dt.tz_localize("UTC")
    else:
        dt = dt.tz_convert("UTC")

    now = pd.Timestamp.utcnow()
    delta = now - dt
    days = max(delta.days, 0)
    label = dt.strftime("%Y-%m-%d")
    if days <= 0:
        return f"{label} (today)"
    return f"{label} ({days}d ago)"


def _safe_num(value, default: float | None = 0.0) -> float | None:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_label(value, fallback: str = "Unknown") -> str:
    if value is None:
        return fallback
    try:
        if pd.isna(value):
            return fallback
    except Exception:
        pass
    text = str(value).strip()
    return text if text else fallback


def _safe_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _humanize_reason(reason: str) -> str:
    if not reason:
        return ""
    mapping = {
        "needs_harvest": "new listings needed",
        "needs_market_data": "market data stale",
        "needs_index": "search index stale",
        "needs_training": "model refresh needed",
        "needs_refresh": "signals stale",
        "status_unavailable": "status unavailable",
        "pipeline_status_failed": "status check failed",
    }
    return mapping.get(reason, reason.replace("_", " ").strip())


VIEW_OPTIONS = ["Atlas", "Deal Flow", "Signal Lab", "Investment Memo"]
DEFAULT_PRICE_RANGE = (120000, 1200000)


def _ensure_session_defaults(available_cities, available_types):
    state = st.session_state
    if "selected_city" not in state:
        state.selected_city = "All"
    if state.selected_city != "All" and state.selected_city not in available_cities:
        state.selected_city = "All"

    if "selected_types" not in state:
        state.selected_types = list(available_types)
    else:
        state.selected_types = [t for t in state.selected_types if t in available_types]
        if not state.selected_types and available_types:
            state.selected_types = list(available_types)

    if "price_range" not in state:
        state.price_range = DEFAULT_PRICE_RANGE
    if "min_score" not in state:
        state.min_score = 0.55
    if "min_yield" not in state:
        state.min_yield = 3.5
    if "min_momentum" not in state:
        state.min_momentum = -1.0
    if "min_area_sentiment" not in state:
        state.min_area_sentiment = 0.4
    if "max_listings" not in state:
        state.max_listings = 300
    if "sort_by" not in state:
        state.sort_by = "Deal Score"
    if "sort_order" not in state:
        state.sort_order = "Desc"
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


def _log_orchestrator(role: str, text: str) -> None:
    st.session_state.orchestrator_log.append({"role": role, "text": text})


def _reset_filters(available_cities, available_types) -> None:
    st.session_state.selected_city = "All"
    st.session_state.selected_types = list(available_types)
    st.session_state.price_range = DEFAULT_PRICE_RANGE
    st.session_state.min_score = 0.55
    st.session_state.min_yield = 3.5
    st.session_state.min_momentum = -1.0
    st.session_state.min_area_sentiment = 0.4
    st.session_state.max_listings = 300
    st.session_state.sort_by = "Deal Score"
    st.session_state.sort_order = "Desc"


def _apply_action(action, available_cities, available_types):
    kind = action.get("type")
    if kind == "set_filters":
        for key, value in action.get("payload", {}).items():
            if key in st.session_state:
                st.session_state[key] = value
    elif kind == "set_view":
        st.session_state.active_view = action.get("view", VIEW_OPTIONS[0])
    elif kind == "select_listing":
        st.session_state.selected_title = action.get("title")
        st.session_state.active_view = "Investment Memo"
    elif kind == "reset_filters":
        _reset_filters(available_cities, available_types)
    elif kind == "preflight":
        api = PipelineAPI()
        with st.spinner("Refreshing pipeline artifacts..."):
            api.preflight()
        load_pipeline_status.clear()
        load_filter_options.clear()


def _action_label(action: dict) -> str:
    kind = action.get("type")
    if kind == "preflight":
        return "Refresh signals"
    if kind == "reset_filters":
        return "Reset lens"
    if kind == "set_view":
        view = action.get("view") or "view"
        return f"Open {view}"
    if kind == "select_listing":
        title = action.get("title") or "listing"
        return f"Open memo: {title}"
    if kind == "set_filters":
        payload = action.get("payload", {})
        parts = []
        if "selected_city" in payload:
            parts.append(f"City = {payload['selected_city']}")
        if "selected_types" in payload:
            types = payload["selected_types"] or []
            if types:
                parts.append(f"Types = {', '.join(types)}")
        if "min_yield" in payload:
            parts.append(f"Min yield {payload['min_yield']:.1f}%")
        if "sort_by" in payload:
            parts.append(f"Sort by {payload['sort_by']}")
        if "sort_order" in payload:
            parts.append(f"Order {payload['sort_order']}")
        if parts:
            return "Adjust filters: " + ", ".join(parts)
        return "Adjust filters"
    return "Run action"


def _resolve_autonomy(actions, autonomy_mode: str, allow_refresh: bool):
    auto_actions = []
    pending = []
    safe_actions = {"set_filters", "set_view", "select_listing"}
    for action in actions:
        kind = action.get("type")
        if autonomy_mode == "Autopilot":
            if kind == "preflight" and not allow_refresh:
                pending.append(action)
            else:
                auto_actions.append(action)
        elif autonomy_mode == "Assisted":
            if kind in safe_actions:
                auto_actions.append(action)
            else:
                pending.append(action)
        else:
            pending.append(action)
    return auto_actions, pending


def _parse_prompt(prompt, available_cities, available_types):
    actions = []
    responses = []
    if not prompt:
        return actions, "Tell me what to explore: yield leaders, value gap, momentum, a city, or the map."

    lower = prompt.lower().strip()

    if "refresh" in lower or "preflight" in lower:
        actions.append({"type": "preflight"})
        responses.append("Running a refresh to sync signals.")

    if "reset" in lower or "clear filters" in lower:
        actions.append({"type": "reset_filters"})
        responses.append("Resetting to the default lens.")

    for city in available_cities:
        if city.lower() in lower:
            actions.append({"type": "set_filters", "payload": {"selected_city": city}})
            responses.append(f"Locking on {city}.")
            break

    for prop_type in available_types:
        if prop_type.lower() in lower:
            actions.append({"type": "set_filters", "payload": {"selected_types": [prop_type]}})
            responses.append(f"Filtering to {prop_type} only.")
            break

    if "yield" in lower:
        actions.append(
            {"type": "set_filters", "payload": {"sort_by": "Yield %", "min_yield": max(st.session_state.min_yield, 4.0)}}
        )
        responses.append("Ranking by yield leaders.")
    if "value gap" in lower or "undervalued" in lower:
        actions.append({"type": "set_filters", "payload": {"sort_by": "Value Delta %", "sort_order": "Asc"}})
        responses.append("Sorting by value gap to surface undervalued deals.")
    if "momentum" in lower:
        actions.append({"type": "set_filters", "payload": {"sort_by": "Momentum %"}})
        responses.append("Ranking by momentum.")
    if "deal flow" in lower or "table" in lower:
        actions.append({"type": "set_view", "view": "Deal Flow"})
        responses.append("Opening the Deal Flow table.")
    if "signal" in lower or "lab" in lower:
        actions.append({"type": "set_view", "view": "Signal Lab"})
        responses.append("Opening Signal Lab.")
    if "map" in lower or "atlas" in lower:
        actions.append({"type": "set_view", "view": "Atlas"})
        responses.append("Opening the map.")
    if "memo" in lower or "analysis" in lower:
        actions.append({"type": "set_view", "view": "Investment Memo"})
        responses.append("Opening the investment memo.")

    response = " ".join(responses) if responses else "Try: yield leaders, value gap, momentum, a city name, or open the map."
    return actions, response


def _compose_orchestrator_prompt(filtered_df, pipeline_needs_refresh, pipeline_error):
    if pipeline_error:
        return "Pipeline status is unavailable. I can refresh to recover, or keep scouting on cached signals."
    if pipeline_needs_refresh:
        return "Signals are stale. Want me to refresh, or keep scouting with what we have?"
    if filtered_df.empty:
        return "No matches under this lens. Want me to widen filters, lower the score floor, or switch cities?"
    return (
        f"{len(filtered_df)} opportunities match this lens. Want yield leaders, undervalued deals, momentum, or the map?"
    )


def _build_suggestions(filtered_df, pipeline_needs_refresh, available_cities):
    suggestions = []
    if pipeline_needs_refresh:
        suggestions.append(
            {
                "title": "Refresh signals",
                "body": "Sync listings, market data, indices, and valuations.",
                "cta": "Run refresh",
                "action": {"type": "preflight"},
                "log": "Refreshing pipeline signals.",
            }
        )

    if filtered_df.empty:
        suggestions.extend(
            [
                {
                    "title": "Broaden the lens",
                    "body": "Lower the minimum deal score to expand coverage.",
                    "cta": "Lower score floor",
                    "action": {"type": "set_filters", "payload": {"min_score": 0.4}},
                    "log": "Lowered the deal score floor.",
                },
                {
                    "title": "Reset lens",
                    "body": "Return to the default scout profile.",
                    "cta": "Reset lens",
                    "action": {"type": "reset_filters"},
                    "log": "Reset to the default lens.",
                },
            ]
        )
        return suggestions

    top_city = (
        filtered_df["City"].dropna().value_counts().index[0]
        if "City" in filtered_df.columns and not filtered_df["City"].dropna().empty
        else None
    )
    top_pick_title = filtered_df.iloc[0]["Title"] if not filtered_df.empty else None

    suggestions.extend(
        [
            {
                "title": "Lead with yield",
                "body": "Sort by income yield with a 4%+ floor.",
                "cta": "Show yields",
                "action": {"type": "set_filters", "payload": {"sort_by": "Yield %", "min_yield": max(st.session_state.min_yield, 4.0)}},
                "log": "Sorting by yield leaders.",
            },
            {
                "title": "Find mispricing",
                "body": "Sort by value gap to surface undervalued deals.",
                "cta": "Find value gaps",
                "action": {"type": "set_filters", "payload": {"sort_by": "Value Delta %", "sort_order": "Asc"}},
                "log": "Sorting by value gap.",
            },
            {
                "title": "Momentum scan",
                "body": "Rank by market momentum to spot rising areas.",
                "cta": "Show momentum",
                "action": {"type": "set_filters", "payload": {"sort_by": "Momentum %"}},
                "log": "Ranking by momentum.",
            },
            {
                "title": "Map the shortlist",
                "body": "See where the strongest deals cluster.",
                "cta": "Open map",
                "action": {"type": "set_view", "view": "Atlas"},
                "log": "Opening the map.",
            },
        ]
    )

    if top_city:
        suggestions.append(
            {
                "title": f"Focus on {top_city}",
                "body": "Filter to the city with the most matches.",
                "cta": "Focus city",
                "action": {"type": "set_filters", "payload": {"selected_city": top_city}},
                "log": f"Filtering to {top_city}.",
            }
        )
    if top_pick_title:
        suggestions.append(
            {
                "title": "Open top memo",
                "body": "Jump to the highest-ranked listing.",
                "cta": "View memo",
                "action": {"type": "select_listing", "title": top_pick_title},
                "log": "Opening the top memo.",
            }
        )

    return suggestions


available_cities, available_types = load_filter_options()
_ensure_session_defaults(available_cities, available_types)

# --- Pipeline Status ---
pipeline_status = load_pipeline_status()
pipeline_needs_refresh = bool(pipeline_status.get("needs_refresh"))
pipeline_error = pipeline_status.get("error")
pipeline_reasons = pipeline_status.get("reasons") or []
if pipeline_error:
    pipeline_state_text = "Degraded"
    pipeline_reason_text = f"Status unavailable: {pipeline_error}"
    pipeline_badge = "Error"
    pipeline_badge_class = "pipeline-badge pipeline-badge--stale"
else:
    pipeline_state_text = "Refresh due" if pipeline_needs_refresh else "Live"
    reason_parts = [_humanize_reason(reason) for reason in pipeline_reasons if reason]
    pipeline_reason_text = ", ".join(reason_parts) if reason_parts else "Signals are current"
    pipeline_badge = "Refresh" if pipeline_needs_refresh else "Live"
    pipeline_badge_class = "pipeline-badge pipeline-badge--fresh" if not pipeline_needs_refresh else "pipeline-badge pipeline-badge--stale"

pipeline_listings = int(pipeline_status.get("listings_count", 0) or 0)
pipeline_listings_at = _format_ts(pipeline_status.get("listings_last_seen"))
pipeline_market_at = _format_ts(pipeline_status.get("market_data_at"))
pipeline_index_at = _format_ts(pipeline_status.get("index_at"))
pipeline_model_at = _format_ts(pipeline_status.get("model_at"))

# --- Top Controls ---
st.markdown(
    f"""
    <div class="app-bar">
        <div class="app-brand">
            <span>Property Scanner</span>
            <small>Scout OS</small>
        </div>
        <div class="app-actions">
            <span class="{pipeline_badge_class}">{pipeline_badge}</span>
            <span class="app-chip">{pipeline_listings} listings</span>
            <span class="app-chip">Listings {pipeline_listings_at}</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.caption(pipeline_reason_text)

st.markdown(
    f"""
    <div class="lux-hero">
        <div>
            <div class="lux-brand">AI ORCHESTRATOR</div>
            <div class="lux-title">Mission Control</div>
            <div class="lux-subtitle">
                The system listens, proposes moves, and keeps you in command. Blend automation with manual override.
            </div>
            <div class="lux-tags">
                <span class="pill">Autonomy: {st.session_state.autonomy_mode}</span>
                <span class="pill">Status: {pipeline_state_text}</span>
                <span class="pill">{pipeline_listings} listings</span>
            </div>
        </div>
        <div class="hero-metric">
            <div class="hero-metric-label">Signal Pulse</div>
            <div class="hero-metric-value">{pipeline_badge}</div>
            <div class="hero-metric-sub">{pipeline_listings_at}</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("#### Command Deck")
mission_col, control_col = st.columns([1.6, 1.1], gap="large")

with mission_col:
    st.caption("Describe your intent. The Scout drafts a plan and queues approvals based on your autonomy level.")
    with st.form("mission_form", clear_on_submit=False):
        prompt = st.text_area(
            "Mission",
            key="orchestrator_input",
            placeholder="Find undervalued two-bed listings in Madrid and map the clusters.",
            height=80,
        )
        autonomy_mode = st.select_slider(
            "Autonomy",
            options=["Advisory", "Assisted", "Autopilot"],
            key="autonomy_mode",
        )
        allow_refresh = st.checkbox("Allow data refresh", key="allow_refresh")
        submitted = st.form_submit_button("Engage Scout")

    if submitted and prompt:
        _log_orchestrator("user", prompt)
        actions, response = _parse_prompt(prompt, available_cities, available_types)
        _log_orchestrator("assistant", response)
        st.session_state.ai_response = response
        auto_actions, pending = _resolve_autonomy(actions, autonomy_mode, allow_refresh)
        st.session_state.last_plan = [
            {
                "label": _action_label(action),
                "status": "auto" if action in auto_actions else "approval",
            }
            for action in actions
        ]
        st.session_state.pending_actions = pending
        if auto_actions:
            for action in auto_actions:
                _apply_action(action, available_cities, available_types)
            st.rerun()

    if st.session_state.ai_response:
        st.info(st.session_state.ai_response, icon="🤖")

    if st.session_state.last_plan:
        st.markdown("**Plan**")
        for step in st.session_state.last_plan:
            status_label = "Auto" if step["status"] == "auto" else "Approval"
            st.markdown(
                f"<div class='signal-pill'><span>{step['label']}</span><span>{status_label}</span></div>",
                unsafe_allow_html=True,
            )

    if st.session_state.pending_actions:
        st.markdown("**Approval Queue**")
        approve_cols = st.columns([1, 1])
        if approve_cols[0].button("Approve all", key="approve_all"):
            for action in st.session_state.pending_actions:
                _apply_action(action, available_cities, available_types)
            st.session_state.pending_actions = []
            st.rerun()
        if approve_cols[1].button("Clear queue", key="clear_queue"):
            st.session_state.pending_actions = []
            st.rerun()

        for idx, action in enumerate(st.session_state.pending_actions):
            label = _action_label(action)
            if st.button(f"Approve: {label}", key=f"approve_{idx}"):
                _apply_action(action, available_cities, available_types)
                remaining = [
                    a for j, a in enumerate(st.session_state.pending_actions) if j != idx
                ]
                st.session_state.pending_actions = remaining
                st.rerun()

    if st.session_state.orchestrator_log:
        with st.expander("Scout Memory", expanded=False):
            for msg in st.session_state.orchestrator_log[-6:]:
                role_icon = "👤" if msg["role"] == "user" else "🤖"
                st.markdown(f"**{role_icon}**: {msg['text']}")

with control_col:
    st.caption("Backstage intelligence and manual override.")
    st.markdown(f"<span class='{pipeline_badge_class}'>{pipeline_badge}</span>", unsafe_allow_html=True)
    st.caption(pipeline_reason_text)
    status_cols = st.columns(2)
    status_cols[0].metric("Listings", pipeline_listings)
    status_cols[1].metric("Signals", pipeline_state_text)
    st.text(f"Listings update: {pipeline_listings_at}")
    st.text(f"Market data: {pipeline_market_at}")
    st.text(f"Index: {pipeline_index_at}")
    st.text(f"Model: {pipeline_model_at}")

    action_cols = st.columns(2)
    refresh_clicked = action_cols[0].button("Refresh Signals", use_container_width=True, key="refresh_signals_top")
    reset_clicked = action_cols[1].button("Reset Lens", use_container_width=True, key="reset_lens_top")

    if refresh_clicked:
        _apply_action({"type": "preflight"}, available_cities, available_types)
        st.rerun()
    if reset_clicked:
        _reset_filters(available_cities, available_types)
        st.rerun()

    with st.expander("Manual Override", expanded=True):
        selected_city = st.selectbox("City", ["All"] + available_cities, key="selected_city")
        selected_types = st.multiselect("Property type", available_types, key="selected_types")
        min_price, max_price = st.slider(
            "Budget range (EUR)", 0, 2000000, key="price_range", step=10000
        )
        manual_cols = st.columns(2)
        with manual_cols[0]:
            min_score = st.slider("Minimum deal score", 0.0, 1.0, key="min_score", step=0.05)
            sort_by = st.selectbox(
                "Sort by",
                ["Deal Score", "Yield %", "Value Delta %", "Fair Value", "Momentum %"],
                key="sort_by",
            )
        with manual_cols[1]:
            min_yield = st.slider("Minimum yield (%)", 0.0, 12.0, key="min_yield", step=0.1)
            sort_order = st.selectbox("Sort order", ["Desc", "Asc"], key="sort_order")
            ascending = sort_order == "Asc"
        max_listings = st.slider("Max listings", 50, 1500, key="max_listings", step=50)

# --- Sidebar: Advanced Filters & Health ---
st.sidebar.markdown("<div class='sidebar-title'>Advanced</div>", unsafe_allow_html=True)
with st.sidebar.expander("Signal Filters", expanded=False):
    min_momentum = st.slider("Momentum floor (annual %)", -8.0, 12.0, key="min_momentum", step=0.5)
    min_area_sentiment = st.slider("Area sentiment floor", 0.0, 1.0, key="min_area_sentiment", step=0.05)

with st.sidebar.expander("System Health", expanded=False):
    st.markdown(f"**Status**: {pipeline_state_text}")
    st.caption(pipeline_reason_text)
    st.text(f"Listings: {pipeline_listings}")
    st.text(f"Listings update: {pipeline_listings_at}")
    st.text(f"Market data: {pipeline_market_at}")
    st.text(f"Index: {pipeline_index_at}")
    st.text(f"Model: {pipeline_model_at}")

# --- Load Data ---
session = storage.get_session()
raw_rows = []
failed_valuations = 0
try:
    query = session.query(DBListing)
    if selected_city != "All":
        query = query.filter(DBListing.city == selected_city)
    if selected_types:
        query = query.filter(DBListing.property_type.in_(selected_types))
    listings_db = query.limit(max_listings).all()

    if listings_db:
        progress_bar = st.progress(0, text="Scoring listings and signals...")

    persister = None
    try:
        from src.valuation.services.valuation_persister import ValuationPersister

        persister = ValuationPersister(session)
    except Exception:
        persister = None

    for i, db_item in enumerate(listings_db):
        listing = db_listing_to_canonical(db_item)

        cached_val = persister.get_latest_valuation(db_item.id) if persister else None
        comps = []
        ext_signals = {}

        if cached_val:
            projections = [
                ValuationProjection(**p) for p in cached_val.evidence.get("projections", [])
            ]
            rent_projections = [
                ValuationProjection(**p) for p in cached_val.evidence.get("rent_projections", [])
            ]
            yield_projections = [
                ValuationProjection(**p) for p in cached_val.evidence.get("yield_projections", [])
            ]
            rent_est = None
            if rent_projections:
                rent_est = min(rent_projections, key=lambda p: p.months_future).predicted_value

            yield_est = None
            if yield_projections:
                yield_est = min(yield_projections, key=lambda p: p.months_future).predicted_value
            elif db_item.gross_yield:
                yield_est = db_item.gross_yield

            analysis = DealAnalysis(
                listing_id=db_item.id,
                fair_value_estimate=cached_val.fair_value,
                fair_value_uncertainty_pct=0.10,
                deal_score=cached_val.confidence_score,
                investment_thesis=cached_val.evidence.get("thesis", "Cached Analysis"),
                market_signals=cached_val.evidence.get("signals", {}),
                projections=projections,
                rent_projections=rent_projections,
                yield_projections=yield_projections,
                evidence=None,
                rental_yield_estimate=yield_est,
            )
            ext_signals = (
                cached_val.evidence.get("evidence", {}).get("external_signals", {})
                if cached_val.evidence
                else {}
            )
        else:
            try:
                comps = retriever.retrieve_comps(listing, k=3)
                analysis = valuation.evaluate_deal(listing, comps=comps)
                if persister:
                    try:
                        persister.save_valuation(db_item.id, analysis)
                    except Exception:
                        pass
                if analysis.evidence and analysis.evidence.external_signals:
                    ext_signals = analysis.evidence.external_signals
            except Exception:
                failed_valuations += 1
                continue

        signals = analysis.market_signals or {}
        momentum = signals.get("momentum")
        liquidity = signals.get("liquidity")
        catchup = signals.get("catchup")
        market_yield = signals.get("market_yield")
        area_sentiment = signals.get("area_sentiment")
        area_development = signals.get("area_development")

        rent_est = db_item.estimated_rent
        if not rent_est and getattr(analysis, "rent_projections", None):
            rent_est = min(analysis.rent_projections, key=lambda p: p.months_future).predicted_value

        yield_est = getattr(analysis, "rental_yield_estimate", None)
        if yield_est is None and db_item.gross_yield:
            yield_est = db_item.gross_yield
        if yield_est is None and getattr(analysis, "yield_projections", None):
            yield_est = min(analysis.yield_projections, key=lambda p: p.months_future).predicted_value

        value_delta = None
        value_delta_pct = None
        if listing.price and listing.price > 0 and analysis.fair_value_estimate:
            value_delta = analysis.fair_value_estimate - listing.price
            value_delta_pct = value_delta / listing.price

        raw_rows.append(
            {
                "ID": listing.id,
                "Title": listing.title,
                "Price": listing.price,
                "Sqm": listing.surface_area_sqm,
                "Bedrooms": listing.bedrooms,
                "City": listing.location.city if listing.location else None,
                "Property Type": str(listing.property_type),
                "Deal Score": analysis.deal_score,
                "Fair Value": analysis.fair_value_estimate,
                "Value Delta": value_delta,
                "Value Delta %": value_delta_pct,
                "Rent Est": rent_est,
                "Yield %": yield_est,
                "Market Yield %": market_yield,
                "Momentum %": (momentum * 100) if momentum is not None else None,
                "Liquidity": liquidity,
                "Catchup": catchup,
                "Area Sentiment": area_sentiment,
                "Area Development": area_development,
                "Income Weight": ext_signals.get("income_weight"),
                "Area Adjustment": ext_signals.get("area_adjustment"),
                "Thesis": analysis.investment_thesis,
                "URL": str(listing.url),
                "lat": listing.location.lat if listing.location else None,
                "lon": listing.location.lon if listing.location else None,
                "Image": listing.image_urls[0] if listing.image_urls else None,
                "Images": listing.image_urls,
                "Desc": listing.description,
                "VLM Desc": listing.vlm_description,
                "Projections": analysis.projections,
                "Rent Projections": getattr(analysis, "rent_projections", []),
                "Yield Projections": getattr(analysis, "yield_projections", []),
                "Signals": signals,
                "Comps": comps if comps else [],
            }
        )

        if listings_db:
            progress_bar.progress((i + 1) / len(listings_db))

    if listings_db:
        progress_bar.empty()

finally:
    session.close()

if failed_valuations:
    st.warning(f"{failed_valuations} listings could not be valued and were skipped.")

df = pd.DataFrame(raw_rows)

if df.empty:
    st.markdown(
        "<div class='empty-state'><h2>No listings yet</h2><p>Run harvest or backfill to load listings.</p></div>",
        unsafe_allow_html=True,
    )
    st.stop()

# --- Normalize & Filter ---
for col in ["Yield %", "Deal Score", "Value Delta %", "Momentum %", "Area Sentiment"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

filtered_df = df.copy()
filtered_df["Yield %"] = filtered_df["Yield %"].fillna(0)
filtered_df["Momentum %"] = filtered_df["Momentum %"].fillna(0)
filtered_df["Area Sentiment"] = filtered_df["Area Sentiment"].fillna(0.5)

filtered_df = filtered_df[
    (filtered_df["Price"] >= min_price)
    & (filtered_df["Price"] <= max_price)
    & (filtered_df["Deal Score"] >= min_score)
    & (filtered_df["Yield %"] >= min_yield)
    & (filtered_df["Momentum %"] >= min_momentum)
    & (filtered_df["Area Sentiment"] >= min_area_sentiment)
]

sort_key = sort_by
if sort_key not in filtered_df.columns:
    sort_key = "Deal Score"
filtered_df = filtered_df.sort_values(by=sort_key, ascending=ascending)

if not filtered_df.empty:
    titles = list(filtered_df["Title"].unique())
    if st.session_state.selected_title not in titles:
        st.session_state.selected_title = titles[0]
else:
    st.session_state.selected_title = None

# --- AI Guidance ---
st.markdown("#### AI Guidance")
guide_col, action_col = st.columns([1.8, 1.2], gap="large")
with guide_col:
    orchestrator_prompt = _compose_orchestrator_prompt(filtered_df, pipeline_needs_refresh, pipeline_error)
    st.info(orchestrator_prompt, icon="🤖")
    if st.session_state.ai_response:
        st.markdown("**Latest Guidance**")
        st.caption(st.session_state.ai_response)
    if st.session_state.pending_actions:
        st.caption(f"{len(st.session_state.pending_actions)} actions awaiting approval.")

with action_col:
    st.caption("Next Steps")
    suggestions = _build_suggestions(filtered_df, pipeline_needs_refresh, available_cities)
    if suggestions:
        action_grid = st.columns(2)
        for idx, suggestion in enumerate(suggestions[:4]):
            col = action_grid[idx % 2]
            if col.button(
                suggestion["cta"],
                key=f"quick_action_{idx}",
                use_container_width=True,
                help=suggestion["body"],
            ):
                log = suggestion.get("log")
                if log:
                    _log_orchestrator("assistant", log)
                _apply_action(suggestion["action"], available_cities, available_types)
                st.rerun()
    else:
        st.caption("No quick actions right now.")

with st.expander("Market Snapshot", expanded=False):
    avg_price = filtered_df["Price"].mean() if not filtered_df.empty else 0
    avg_price = float(avg_price) if pd.notna(avg_price) else 0
    avg_yield = filtered_df["Yield %"].mean() if not filtered_df.empty else 0
    avg_yield = float(avg_yield) if pd.notna(avg_yield) else 0
    median_delta = filtered_df["Value Delta %"].median() if not filtered_df.empty else 0
    median_delta = float(median_delta) if pd.notna(median_delta) else 0
    avg_momentum = filtered_df["Momentum %"].mean() if not filtered_df.empty else 0
    avg_momentum = float(avg_momentum) if pd.notna(avg_momentum) else 0
    avg_liquidity = filtered_df["Liquidity"].mean() if not filtered_df.empty else 0.5
    avg_liquidity = float(avg_liquidity) if pd.notna(avg_liquidity) else 0.5
    avg_area = filtered_df["Area Sentiment"].mean() if not filtered_df.empty else 0.5
    avg_area = float(avg_area) if pd.notna(avg_area) else 0.5

    momentum_score = np.tanh((avg_momentum or 0) / 4.0)
    liquidity_score = (avg_liquidity or 0.5) - 0.5
    area_score = (avg_area or 0.5) - 0.5
    market_heat_index = int(np.clip(50 + 30 * momentum_score + 25 * liquidity_score + 20 * area_score, 0, 100))

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Signal Pulse", market_heat_index, help="Momentum-driven composite index")
    m2.metric("Opps", len(filtered_df))
    m3.metric("Avg Yield", f"{avg_yield:.2f}%")
    m4.metric("Value Gap", f"{median_delta * 100:+.1f}%")
    m5.metric("Avg Price", f"{avg_price/1000:.0f}k")

st.divider()

# --- Main Navigation (Tabs) ---
# Order: Atlas (Map) -> Deal Flow (Table) -> Analysis -> Lab
tab_atlas, tab_flow, tab_memo, tab_lab = st.tabs(["🗺️ Atlas", "📋 Deal Flow", "📑 Memo", "🧪 Signal Lab"])

# --- TAB: ATLAS ---
with tab_atlas:
    map_data = filtered_df.dropna(subset=["lat", "lon"]).copy()
    if not map_data.empty:
        import pydeck as pdk
        
        # Color scale logic
        def score_color(score):
            score = max(0.0, min(score, 1.0))
            # Green to Gold gradient
            # Low score: Dark Blue/Grey (40, 44, 56)
            # High score: Gold/Amber (205, 165, 92)
            base = np.array([40, 44, 56])
            peak = np.array([205, 165, 92])
            color = base + (peak - base) * score
            return [int(c) for c in color] + [200]

        map_data["color"] = map_data["Deal Score"].apply(score_color)
        
        # Map Style
        deck_style = "mapbox://styles/mapbox/light-v11"
        try:
            if st.get_option("theme.base") == "dark":
                deck_style = "mapbox://styles/mapbox/dark-v11"
        except Exception:
            pass

        st.pydeck_chart(
            pdk.Deck(
                map_style=deck_style,
                initial_view_state=pdk.ViewState(
                    latitude=map_data["lat"].mean(),
                    longitude=map_data["lon"].mean(),
                    zoom=12,
                    pitch=45,
                ),
                layers=[
                    pdk.Layer(
                        "ScatterplotLayer",
                        data=map_data,
                        get_position="[lon, lat]",
                        get_fill_color="color",
                        get_radius=150,
                        pickable=True,
                        auto_highlight=True,
                        stroked=True,
                        get_line_color=[255, 255, 255],
                        line_width_min_pixels=1,
                        opacity=0.8,
                    )
                ],
                tooltip={
                    "html": "<div style='background: white; color: black; padding: 8px; border-radius: 4px; font-family: sans-serif;'>"
                            "<b>{Title}</b><br/>"
                            "{City}<br/>"
                            "Price: {Price} EUR<br/>"
                            "Yield: {Yield %}%</div>"
                },
            ),
            use_container_width=True
        )
    else:
        st.info("No geocoded listings found for this lens.")

# --- TAB: DEAL FLOW ---
with tab_flow:
    # Top 3 Cards
    if not filtered_df.empty:
        st.markdown("**Top Picks**")
        top_picks = filtered_df.head(3)
        pick_cols = st.columns(len(top_picks))
        for col, (_, row) in zip(pick_cols, top_picks.iterrows()):
             with col:
                # Mini Deal Card
                img_url = row.get("Image")
                if img_url and isinstance(img_url, str):
                    st.image(img_url, use_container_width=True)
                else:
                    st.markdown("<div style='height: 120px; background: #eee; display:flex; align-items:center; justify-content:center; color:#888;'>No Image</div>", unsafe_allow_html=True)
                
                st.markdown(f"**{row['Title']}**")
                st.caption(f"{row['City']} • {row['Price']:,.0f} €")
                st.markdown(f"Yield: **{row['Yield %']:.2f}%** | Score: **{row['Deal Score']:.2f}**")
                if st.button("View Memo", key=f"btn_view_{row['ID']}"):
                     st.session_state.selected_title = row['Title']
                     st.session_state.active_view = "Investment Memo" # Fallback if we were using radio, but now we might need to verify tab switching logic.
                     # Since tabs are stateless in selection, we can't force switch tab easily without rerunning and some hacks.
                     # For now, we will just set the title so if they go to Memo tab it's there.
                     st.toast(f"Selected {row['Title']}. Switch to 'Memo' tab to view details.")

    st.markdown("---")
    
    display_cols = [
        "Title", "Price", "Yield %", "Deal Score", 
        "Value Delta %", "Momentum %", "City", "URL"
    ]
    st.dataframe(
        filtered_df[display_cols].style.format({
            "Price": "{:,.0f} EUR",
            "Yield %": "{:.2f}%",
            "Deal Score": "{:.2f}",
            "Value Delta %": "{:+.1f}%",
            "Momentum %": "{:+.1f}%",
        }),
        use_container_width=True,
        height=500,
        column_config={
            "URL": st.column_config.LinkColumn("Listing", display_text="Open"),
        },
    )

# --- TAB: MEMO ---
with tab_memo:
    if not filtered_df.empty:
        # Resolve selection
        current_titles = list(filtered_df["Title"].unique())
        if st.session_state.selected_title not in current_titles:
            st.session_state.selected_title = current_titles[0]
            
        selected_title = st.selectbox(
            "Select Property",
            current_titles,
            index=current_titles.index(st.session_state.selected_title),
            key="selected_title_box"
        )
        # Sync selection back to state
        st.session_state.selected_title = selected_title
        
        item = filtered_df[filtered_df["Title"] == selected_title].iloc[0]
        
        # Memo Layout
        m_col1, m_col2 = st.columns([1, 1])
        
        with m_col1:
            # Images & Desc
            images = _safe_list(item.get("Images"))
            if images:
                st.image(str(images[0]), use_container_width=True)
                with st.expander(f"Gallery ({len(images)})"):
                     st.image(images[:5], use_container_width=True)
            else:
                st.info("No images.")
            
            st.markdown("### Analyst Notes")
            st.info(item.get("VLM Desc") or "No AI vision summary available.")
            st.text_area("Description", item.get("Desc") or "No description.", height=150)

        with m_col2:
            st.markdown(f"## {item.get('Title')}")
            st.caption(f"{item.get('City')} | {item.get('Property Type')}")
            
            # Financial Grid
            f1, f2, f3 = st.columns(3)
            f1.metric("Ask Price", f"{item.get('Price'):,.0f} €")
            f2.metric("Fair Value", f"{item.get('Fair Value'):,.0f} €", delta=f"{item.get('Value Delta %')*100:+.1f}%")
            f3.metric("Deal Score", f"{item.get('Deal Score'):.2f}")
            
            f4, f5, f6 = st.columns(3)
            f4.metric("Est. Rent", f"{item.get('Rent Est'):,.0f} €")
            f5.metric("Gross Yield", f"{item.get('Yield %'):.2f}%")
            f6.metric("Market Yield", f"{item.get('Market Yield %'):.2f}%")
            
            st.markdown("### Thesis")
            st.warning(item.get("Thesis") or "Analysis pending.")
            
            # Projections
            st.markdown("### Projections")
            projections = _safe_list(item.get("Projections"))
            if projections:
                proj_df = pd.DataFrame([{"Month": p.months_future, "Euro": p.predicted_value} for p in projections])
                st.line_chart(proj_df.set_index("Month"), height=200)
            
            # Comps
            st.markdown("### Comps")
            comps = _safe_list(item.get("Comps"))
            if comps:
                c_data = []
                for c in comps[:3]:
                    c_data.append({
                        "Price": c.price,
                        "Sqm": c.features.get("sqm") if c.features else 0,
                        "Similarity": c.similarity_score
                    })
                st.dataframe(c_data, use_container_width=True)
            else:
                st.caption("No comps found.")

    else:
        st.info("No listings match your lens. Adjust filters in the sidebar.")

# --- TAB: SIGNAL LAB ---
with tab_lab:
    l_col1, l_col2 = st.columns(2)
    with l_col1:
         st.markdown("#### Yield vs Value")
         if not filtered_df.empty:
             st.scatter_chart(filtered_df, x="Yield %", y="Value Delta %", color="Deal Score", height=350)
    with l_col2:
         st.markdown("#### Momentum Distribution")
         if not filtered_df.empty:
             st.bar_chart(filtered_df["Momentum %"], height=350)
