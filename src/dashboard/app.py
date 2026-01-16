import sys
import os

# Add project root to path (robustly, for when running from various dirs)
# src/dashboard/app.py -> ../.. -> project_root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Prevent Mac OMP segfaults (Critical for PyDeck/Torch on Mac)
os.environ["KMP_DUPLICATE_LIB_OK"] = "True"

import streamlit as st
import pandas as pd
import numpy as np

from src.api.pipeline import PipelineAPI
from src.services.listing_adapter import db_listing_to_canonical
from src.services.pipeline_state import PipelineStateService
from src.core.domain.models import DBListing
from src.core.domain.schema import DealAnalysis, ValuationProjection

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
    if getattr(dt, "tzinfo", None):
        try:
            dt = dt.tz_convert(None)
        except Exception:
            dt = dt.tz_localize(None)
    delta = pd.Timestamp.utcnow().to_pydatetime() - dt.to_pydatetime()
    days = max(delta.days, 0)
    label = dt.strftime("%Y-%m-%d")
    if days <= 0:
        return f"{label} (today)"
    return f"{label} ({days}d ago)"


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


def _parse_prompt(prompt, available_cities, available_types):
    actions = []
    responses = []
    if not prompt:
        return actions, "Ask me to navigate the live intel."

    lower = prompt.lower().strip()

    if "refresh" in lower or "preflight" in lower:
        actions.append({"type": "preflight"})
        responses.append("Refreshing pipeline artifacts.")

    if "reset" in lower or "clear filters" in lower:
        actions.append({"type": "reset_filters"})
        responses.append("Resetting filters to the default mandate.")

    for city in available_cities:
        if city.lower() in lower:
            actions.append({"type": "set_filters", "payload": {"selected_city": city}})
            responses.append(f"Focusing on {city}.")
            break

    for prop_type in available_types:
        if prop_type.lower() in lower:
            actions.append({"type": "set_filters", "payload": {"selected_types": [prop_type]}})
            responses.append(f"Filtering to {prop_type} listings.")
            break

    if "yield" in lower:
        actions.append(
            {"type": "set_filters", "payload": {"sort_by": "Yield %", "min_yield": max(st.session_state.min_yield, 4.0)}}
        )
        responses.append("Ranking by yield leaders.")
    if "value gap" in lower or "undervalued" in lower:
        actions.append({"type": "set_filters", "payload": {"sort_by": "Value Delta %", "sort_order": "Asc"}})
        responses.append("Sorting for undervalued opportunities.")
    if "momentum" in lower:
        actions.append({"type": "set_filters", "payload": {"sort_by": "Momentum %"}})
        responses.append("Prioritizing market momentum.")
    if "deal flow" in lower or "table" in lower:
        actions.append({"type": "set_view", "view": "Deal Flow"})
        responses.append("Opening Deal Flow.")
    if "signal" in lower or "lab" in lower:
        actions.append({"type": "set_view", "view": "Signal Lab"})
        responses.append("Opening Signal Lab.")
    if "map" in lower or "atlas" in lower:
        actions.append({"type": "set_view", "view": "Atlas"})
        responses.append("Opening Atlas.")
    if "memo" in lower or "analysis" in lower:
        actions.append({"type": "set_view", "view": "Investment Memo"})
        responses.append("Opening the Investment Memo.")

    response = " ".join(responses) if responses else "Give me a focus: yield, value gap, momentum, or a city."
    return actions, response


def _compose_orchestrator_prompt(filtered_df, pipeline_needs_refresh, pipeline_error):
    if pipeline_error:
        return "Pipeline telemetry is degraded. Want a refresh, or should we operate on cached signals?"
    if pipeline_needs_refresh:
        return "Signals are drifting. Want me to refresh the pipeline or keep scouting with current intel?"
    if filtered_df.empty:
        return "No matches in the current lens. Should I widen filters or switch cities?"
    return (
        f"I found {len(filtered_df)} opportunities. Do you want yield leaders, undervalued deals, "
        "or momentum plays?"
    )


def _build_suggestions(filtered_df, pipeline_needs_refresh, available_cities):
    suggestions = []
    if pipeline_needs_refresh:
        suggestions.append(
            {
                "title": "Refresh the pipeline",
                "body": "Run preflight to sync indices, comps, and valuations.",
                "cta": "Run refresh",
                "action": {"type": "preflight"},
                "log": "Queued a pipeline refresh.",
            }
        )

    if filtered_df.empty:
        suggestions.extend(
            [
                {
                    "title": "Widen the lens",
                    "body": "Lower the minimum deal score to expand coverage.",
                    "cta": "Loosen filters",
                    "action": {"type": "set_filters", "payload": {"min_score": 0.4}},
                    "log": "Lowered the minimum deal score to broaden results.",
                },
                {
                    "title": "Reset filters",
                    "body": "Return to the default scouting mandate.",
                    "cta": "Reset",
                    "action": {"type": "reset_filters"},
                    "log": "Reset filters to the default mandate.",
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
                "title": "Yield leaders",
                "body": "Sort by income strength with a 4%+ yield floor.",
                "cta": "Show yields",
                "action": {"type": "set_filters", "payload": {"sort_by": "Yield %", "min_yield": max(st.session_state.min_yield, 4.0)}},
                "log": "Surfacing yield leaders.",
            },
            {
                "title": "Undervalued focus",
                "body": "Sort by deepest value gaps versus ask.",
                "cta": "Find mispricing",
                "action": {"type": "set_filters", "payload": {"sort_by": "Value Delta %", "sort_order": "Asc"}},
                "log": "Hunting undervalued listings.",
            },
            {
                "title": "Momentum sweep",
                "body": "Rank by market momentum to spot rising zones.",
                "cta": "Show momentum",
                "action": {"type": "set_filters", "payload": {"sort_by": "Momentum %"}},
                "log": "Prioritizing momentum-driven zones.",
            },
            {
                "title": "Atlas view",
                "body": "Explore geospatial distribution of the short list.",
                "cta": "Open map",
                "action": {"type": "set_view", "view": "Atlas"},
                "log": "Opening Atlas view.",
            },
        ]
    )

    if top_city:
        suggestions.append(
            {
                "title": f"Lock on {top_city}",
                "body": "Filter to the city with the densest opportunity set.",
                "cta": "Focus city",
                "action": {"type": "set_filters", "payload": {"selected_city": top_city}},
                "log": f"Locking on {top_city}.",
            }
        )
    if top_pick_title:
        suggestions.append(
            {
                "title": "Open investment memo",
                "body": "Jump to the most promising listing.",
                "cta": "View memo",
                "action": {"type": "select_listing", "title": top_pick_title},
                "log": "Opening the top investment memo.",
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
    pipeline_state_text = "Status Error"
    pipeline_reason_text = f"{pipeline_error}"
    pipeline_badge = "Error"
    pipeline_badge_class = "pipeline-badge pipeline-badge--stale"
else:
    pipeline_state_text = "Stale" if pipeline_needs_refresh else "Fresh"
    pipeline_reason_text = ", ".join(pipeline_reasons) if pipeline_reasons else "All systems aligned"
    pipeline_badge = "Refresh" if pipeline_needs_refresh else "Live"
    pipeline_badge_class = "pipeline-badge pipeline-badge--fresh" if not pipeline_needs_refresh else "pipeline-badge pipeline-badge--stale"

pipeline_listings = int(pipeline_status.get("listings_count", 0) or 0)
pipeline_listings_at = _format_ts(pipeline_status.get("listings_last_seen"))
pipeline_market_at = _format_ts(pipeline_status.get("market_data_at"))
pipeline_index_at = _format_ts(pipeline_status.get("index_at"))
pipeline_model_at = _format_ts(pipeline_status.get("model_at"))

st.markdown(
    f"""
    <div class="app-bar">
        <div class="app-brand">
            <span>Property Scanner</span>
            <small>Scout OS</small>
        </div>
        <div class="app-actions">
            <span class="app-chip">{pipeline_state_text}</span>
            <span class="app-chip">{st.session_state.active_view}</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# --- Sidebar Controls ---
st.sidebar.markdown("<div class='sidebar-title'>Control Room</div>", unsafe_allow_html=True)

with st.sidebar.expander("Lens", expanded=True):
    selected_city = st.selectbox("Location", ["All"] + available_cities, key="selected_city")
    selected_types = st.multiselect("Type", available_types, key="selected_types")
    min_price, max_price = st.slider(
        "Budget (EUR)", 0, 2000000, key="price_range", step=10000
    )

with st.sidebar.expander("Performance", expanded=True):
    min_score = st.slider("Conviction Score", 0.0, 1.0, key="min_score", step=0.05)
    min_yield = st.slider("Income Yield (%)", 0.0, 12.0, key="min_yield", step=0.1)

with st.sidebar.expander("Signals", expanded=False):
    min_momentum = st.slider("Momentum Floor (Annual %)", -8.0, 12.0, key="min_momentum", step=0.5)
    min_area_sentiment = st.slider("Area Sentiment Floor", 0.0, 1.0, key="min_area_sentiment", step=0.05)

with st.sidebar.expander("Results", expanded=False):
    max_listings = st.slider("Max Results", 50, 1500, key="max_listings", step=50)
    sort_by = st.selectbox(
        "Rank By",
        ["Deal Score", "Yield %", "Value Delta %", "Fair Value", "Momentum %"],
        key="sort_by",
    )
    ascending = st.radio("Order", ["Desc", "Asc"], key="sort_order", horizontal=True) == "Asc"

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
        progress_bar = st.progress(0, text="Synthesizing intelligence...")

    persister = None
    try:
        from src.services.valuation_persister import ValuationPersister

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
    st.warning(f"{failed_valuations} listings failed valuation and were skipped.")

df = pd.DataFrame(raw_rows)

if df.empty:
    st.markdown(
        "<div class='empty-state'><h2>No listings found</h2><p>Run the harvest or backfill workflows first.</p></div>",
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

# --- Orchestrator Console ---
orchestrator_prompt = _compose_orchestrator_prompt(filtered_df, pipeline_needs_refresh, pipeline_error)
suggestions = _build_suggestions(filtered_df, pipeline_needs_refresh, available_cities)

st.markdown(
    f"""
    <div class="orchestrator-panel">
        <div class="orchestrator-header">
            <div>
                <div class="orchestrator-label">LLM Orchestrator</div>
                <div class="orchestrator-title">Scout Dialogue</div>
            </div>
            <div class="orchestrator-status">{pipeline_state_text}</div>
        </div>
        <div class="orchestrator-prompt">{orchestrator_prompt}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.form("orchestrator_form", clear_on_submit=True):
    prompt = st.text_input(
        "Ask the Scout",
        placeholder="e.g. show undervalued apartments in Alicante, open the map",
        key="orchestrator_input",
        label_visibility="collapsed",
    )
    submitted = st.form_submit_button("Send")

if submitted and prompt:
    _log_orchestrator("user", prompt)
    actions, response = _parse_prompt(prompt, available_cities, available_types)
    _log_orchestrator("assistant", response)
    for action in actions:
        _apply_action(action, available_cities, available_types)
    st.rerun()

if suggestions:
    st.markdown("<div class='section-title'>Suggested Responses</div>", unsafe_allow_html=True)
    cols = st.columns(3)
    for idx, suggestion in enumerate(suggestions):
        col = cols[idx % 3]
        with col:
            st.markdown(
                f"""
                <div class="answer-banner">
                    <div class="answer-title">{suggestion['title']}</div>
                    <div class="answer-body">{suggestion['body']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(suggestion["cta"], key=f"suggestion_{idx}"):
                log = suggestion.get("log")
                if log:
                    _log_orchestrator("assistant", log)
                _apply_action(suggestion["action"], available_cities, available_types)
                st.rerun()

st.markdown("<div class='section-title'>Navigator</div>", unsafe_allow_html=True)
st.radio("", VIEW_OPTIONS, key="active_view", horizontal=True, label_visibility="collapsed")

with st.expander("Dialogue Log"):
    if st.session_state.orchestrator_log:
        for msg in st.session_state.orchestrator_log[-6:]:
            st.markdown(
                f"<div class='orchestrator-log orchestrator-log--{msg['role']}'>{msg['text']}</div>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("No dialogue yet. Ask the Scout above.")

# --- Lens Summary ---
type_label = "All types"
if selected_types:
    type_label = ", ".join(selected_types[:2])
    if len(selected_types) > 2:
        type_label = f"{type_label} +{len(selected_types) - 2}"

lens_tags = [
    f"Location: {selected_city}",
    f"Type: {type_label}",
    f"Budget: €{min_price:,.0f}–€{max_price:,.0f}",
    f"Score ≥ {min_score:.2f}",
    f"Yield ≥ {min_yield:.1f}%",
]

lens_cols = st.columns([4, 1])
with lens_cols[0]:
    st.markdown(
        f"""
        <div class="lens-card">
            <div class="lens-title">Active Lens</div>
            <div class="lens-tags">
                {"".join([f"<span class='lens-tag'>{tag}</span>" for tag in lens_tags])}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with lens_cols[1]:
    if st.button("Reset Lens"):
        _reset_filters(available_cities, available_types)
        st.rerun()

# --- Hero ---
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

st.markdown(
    f"""
    <div class="lux-hero">
        <div>
            <div class="lux-brand">Scout OS</div>
            <h1 class="lux-title">Property Scanner</h1>
            <p class="lux-subtitle">A private-market command layer for valuation, rental strength, and neighborhood momentum.</p>
            <div class="lux-tags">
                <span class="pill">Comp-Fusion Valuation</span>
                <span class="pill">Income-Adjusted Yield</span>
                <span class="pill">Area Intelligence</span>
            </div>
        </div>
        <div class="hero-metric">
            <div class="hero-metric-label">Signal Pulse</div>
            <div class="hero-metric-value">{market_heat_index}</div>
            <div class="hero-metric-sub">Momentum-driven composite</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# --- System Health ---
with st.expander("System Health", expanded=False):
    st.markdown(
        f"""
        <div class="system-card">
            <div class="pipeline-head">
                <div>
                    <div class="pipeline-label">Pipeline Health</div>
                    <div class="pipeline-title">{pipeline_state_text}</div>
                    <div class="pipeline-reason">{pipeline_reason_text}</div>
                </div>
                <div class="{pipeline_badge_class}">{pipeline_badge}</div>
            </div>
            <div class="pipeline-grid">
                <div><span>Listings</span><strong>{pipeline_listings}</strong></div>
                <div><span>Listings Last Seen</span><strong>{pipeline_listings_at}</strong></div>
                <div><span>Market Data</span><strong>{pipeline_market_at}</strong></div>
                <div><span>Index</span><strong>{pipeline_index_at}</strong></div>
                <div><span>Model</span><strong>{pipeline_model_at}</strong></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# --- Highlights ---
kpi_label = "Highlights"
kpi_note = "A curated pulse from your active lens."
st.markdown(
    f"""
    <div class="section-intro">
        <div class="section-title">{kpi_label}</div>
        <div class="section-subtitle">{kpi_note}</div>
    </div>
    """,
    unsafe_allow_html=True,
)
kpi_cols = st.columns(4)

kpi_data = [
    ("Opportunities", f"{len(filtered_df)}", "Curated to your filters"),
    ("Median Value Gap", f"{median_delta * 100:+.1f}%", "Fair value vs ask"),
    ("Average Yield", f"{avg_yield:.2f}%", "Income profile"),
    ("Avg. Ask Price", f"{avg_price:,.0f} EUR", "Prime band"),
]

for col, (label, value, note) in zip(kpi_cols, kpi_data):
    with col:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-label">{label}</div>
                <div class="kpi-value">{value}</div>
                <div class="kpi-note">{note}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# --- Signal Strip ---
strip_cols = st.columns(5)
signal_blocks = [
    ("Momentum", f"{avg_momentum:+.1f}%"),
    ("Liquidity", f"{avg_liquidity:.2f}"),
    ("Area Sentiment", f"{avg_area:.2f}"),
    ("Yield Premium", f"{avg_yield - (filtered_df['Market Yield %'].mean() or 0):+.2f} pp"),
    ("Intelligence", "Live")
]

for col, (label, value) in zip(strip_cols, signal_blocks):
    with col:
        st.markdown(
            f"""
            <div class="signal-pill">
                <span>{label}</span>
                <strong>{value}</strong>
            </div>
            """,
            unsafe_allow_html=True,
        )

# --- Featured Selection ---
if not filtered_df.empty:
    st.markdown("<div class='section-title'>Featured Selection</div>", unsafe_allow_html=True)
    top_picks = filtered_df.head(3)
    pick_cols = st.columns(len(top_picks))
    for col, (_, row) in zip(pick_cols, top_picks.iterrows()):
        image_html = (
            f"<img src='{row['Image']}' class='deal-image'/>"
            if row["Image"]
            else "<div class='image-placeholder'>No Image</div>"
        )
        with col:
            st.markdown(
                f"""
                <div class="deal-card">
                    {image_html}
                    <div class="deal-title">{row['Title']}</div>
                    <div class="deal-meta">{row['City']} · {row['Sqm'] or 0:.0f} m² · {row['Bedrooms'] or 0} bed</div>
                    <div class="deal-metrics">
                        <span>Score <strong>{row['Deal Score']:.2f}</strong></span>
                        <span>Yield <strong>{row['Yield %']:.2f}%</strong></span>
                    </div>
                    <div class="deal-price">{row['Price']:,.0f} EUR</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

# --- Intel Views ---
active_view = st.session_state.active_view

if active_view == "Atlas":
    map_data = filtered_df.dropna(subset=["lat", "lon"]).copy()
    if not map_data.empty:
        def score_color(score):
            score = max(0.0, min(score, 1.0))
            base = np.array([40, 44, 56])
            peak = np.array([205, 165, 92])
            color = base + (peak - base) * score
            return [int(c) for c in color] + [190]

        map_data["color"] = map_data["Deal Score"].apply(score_color)

        import pydeck as pdk

        st.pydeck_chart(
            pdk.Deck(
                map_style="mapbox://styles/mapbox/light-v11",
                initial_view_state=pdk.ViewState(
                    latitude=map_data["lat"].mean(),
                    longitude=map_data["lon"].mean(),
                    zoom=12,
                    pitch=40,
                ),
                layers=[
                    pdk.Layer(
                        "ScatterplotLayer",
                        data=map_data,
                        get_position="[lon, lat]",
                        get_fill_color="color",
                        get_radius=120,
                        pickable=True,
                        auto_highlight=True,
                        stroked=True,
                        get_line_color=[255, 255, 255],
                        line_width_min_pixels=1,
                    )
                ],
                tooltip={
                    "html": "<div class='map-tip'><strong>{Title}</strong><br/>{City}<br/>{Price:,.0f} EUR<br/>Yield {Yield %:.2f}%</div>"
                },
            )
        )
    else:
        st.info("No geocoded listings available for the current filters.")

elif active_view == "Deal Flow":
    display_cols = [
        "Title",
        "Price",
        "Yield %",
        "Deal Score",
        "Value Delta %",
        "Momentum %",
        "City",
        "URL",
    ]
    table_df = filtered_df[display_cols].copy()
    st.dataframe(
        table_df.style.format(
            {
                "Price": "{:,.0f} EUR",
                "Yield %": "{:.2f}%",
                "Deal Score": "{:.2f}",
                "Value Delta %": "{:+.1f}%",
                "Momentum %": "{:+.1f}%",
            }
        ),
        use_container_width=True,
        height=420,
    )

elif active_view == "Signal Lab":
    left, right = st.columns(2)
    with left:
        st.markdown("### Yield vs Value Gap")
        scatter_df = filtered_df[["Yield %", "Value Delta %", "Deal Score"]].dropna()
        if not scatter_df.empty:
            st.scatter_chart(scatter_df, x="Yield %", y="Value Delta %")
        else:
            st.caption("Not enough data for scatter view.")

    with right:
        st.markdown("### Deal Score Distribution")
        if not filtered_df.empty:
            hist, edges = np.histogram(filtered_df["Deal Score"].fillna(0), bins=10, range=(0, 1))
            hist_df = pd.DataFrame({"Score": edges[:-1], "Count": hist})
            st.bar_chart(hist_df, x="Score", y="Count")
        else:
            st.caption("No deal scores available.")

# --- Investment Memo ---
if active_view == "Investment Memo":
    st.markdown("<div class='section-title'>Investment Memo</div>", unsafe_allow_html=True)

    if not filtered_df.empty:
        selected_title = st.selectbox(
            "Select Opportunity",
            filtered_df["Title"].unique(),
            key="selected_title",
        )
        if selected_title:
            item = filtered_df[filtered_df["Title"] == selected_title].iloc[0]

        header_left, header_right = st.columns([3, 1])
        with header_left:
            st.markdown(f"### {item['Title']}")
            st.caption(f"{item['City']} · {item['Sqm'] or 0:.0f} m² · {item['Bedrooms'] or 0} bed")
        with header_right:
            st.markdown(
                f"""
                <div class="score-block">
                    <div class="score-value">{item['Deal Score']:.2f}</div>
                    <div class="score-label">Deal Score</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        col_media, col_fin = st.columns([1.2, 1])

        with col_media:
            if item["Images"]:
                st.image(str(item["Images"][0]), use_container_width=True)
                with st.expander(f"View {len(item['Images'])} images"):
                    img_cols = st.columns(3)
                    for idx, img in enumerate(item["Images"]):
                        img_cols[idx % 3].image(str(img), use_container_width=True)
            else:
                st.info("No imagery available for this asset.")

            st.markdown("#### Intelligence Notes")
            tab_vis, tab_txt = st.tabs(["Vision", "Listing"])
            with tab_vis:
                if item["VLM Desc"]:
                    st.success(item["VLM Desc"])
                else:
                    st.caption("Vision model has not processed this listing yet.")
            with tab_txt:
                st.text_area("Original Description", item.get("Desc", "No description."), height=160, disabled=True)

        with col_fin:
            st.markdown(
                f"""
                <div class="glass-card">
                    <h3>Financial Outline</h3>
                    <div class="stat-row"><span>Asking Price</span><strong>{item['Price']:,.0f} EUR</strong></div>
                    <div class="stat-row"><span>Fair Value</span><strong>{item['Fair Value']:,.0f} EUR</strong></div>
                    <div class="stat-row"><span>Value Gap</span><strong>{item['Value Delta %'] * 100:+.1f}%</strong></div>
                    <div class="stat-row"><span>Rent Estimate</span><strong>{item['Rent Est'] or 0:,.0f} EUR/mo</strong></div>
                    <div class="stat-row"><span>Gross Yield</span><strong>{item['Yield %']:.2f}%</strong></div>
                    <div class="stat-row"><span>Market Yield</span><strong>{item['Market Yield %'] or 0:.2f}%</strong></div>
                    <div class="divider"></div>
                    <div class="thesis-block">{item['Thesis']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            st.markdown("#### Signal Stack")
            signal_rows = st.columns(2)
            signal_rows[0].metric("Momentum", f"{item['Momentum %'] or 0:+.1f}%")
            signal_rows[1].metric("Liquidity", f"{item['Liquidity'] or 0:.2f}")
            signal_rows = st.columns(2)
            signal_rows[0].metric("Area Sentiment", f"{item['Area Sentiment'] or 0:.2f}")
            signal_rows[1].metric("Area Development", f"{item['Area Development'] or 0:.2f}")

            st.markdown("#### Performance Horizon")
            if item["Projections"]:
                proj_df = pd.DataFrame(
                    [{"Month": p.months_future, "Value": p.predicted_value} for p in item["Projections"]]
                )
                st.area_chart(proj_df.set_index("Month"), color="#c9a16a")
            else:
                st.warning("No valuation projections available.")

            if item["Yield Projections"]:
                yield_df = pd.DataFrame(
                    [
                        {"Month": p.months_future, "Yield": p.predicted_value}
                        for p in item["Yield Projections"]
                    ]
                )
                st.line_chart(yield_df.set_index("Month"), color="#6f8f82")

        st.markdown("#### Comparable Evidence")
        if item["Comps"]:
            comp_rows = []
            for comp in item["Comps"][:5]:
                sqm = comp.features.get("sqm") if comp.features else None
                comp_rows.append(
                    {
                        "Price": comp.price,
                        "Sqm": sqm,
                        "Similarity": comp.similarity_score,
                        "ID": comp.id,
                    }
                )
            comps_df = pd.DataFrame(comp_rows)
            st.dataframe(
                comps_df.style.format(
                    {"Price": "{:,.0f} EUR", "Similarity": "{:.2f}", "Sqm": "{:.0f}"}
                ),
                use_container_width=True,
            )
        else:
            st.caption("No direct comparables available for this asset.")
    else:
        st.caption("No listings match the current filters.")
