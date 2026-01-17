import sys
import os

# Add project root to path (robustly, for when running from various dirs)
# src/interfaces/dashboard/app.py -> ../.. -> project_root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

# Prevent Mac OMP segfaults (Critical for PyDeck/Torch on Mac)
os.environ["KMP_DUPLICATE_LIB_OK"] = "True"

import streamlit as st
import pandas as pd
import numpy as np

from src.interfaces.api.pipeline import PipelineAPI
from src.interfaces.dashboard.scout_logic import (
    DEFAULT_PRICE_RANGE,
    VIEW_OPTIONS,
    _action_label,
    _build_deal_reasons,
    _build_suggestions,
    _compose_orchestrator_prompt,
    _format_deal_reasons,
    _format_intel_summary,
    _format_location,
    _format_ts,
    _humanize_reason,
    _parse_prompt,
    _resolve_autonomy,
    _resolve_profile_sort,
    _safe_list,
    _safe_num,
    _select_scout_picks,
)
from src.listings.services.listing_adapter import db_listing_to_canonical
from src.listings.services.image_selection import ImageSelector
from src.platform.utils.config import load_app_config_safe
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
    app_config = load_app_config_safe()
    selector = ImageSelector(config=app_config.image_selector)
    return api.storage, api.valuation, api.retriever, selector


storage, valuation, retriever, image_selector = get_services()


@st.cache_data(ttl=600)
def load_filter_options():
    session = storage.get_session()
    try:
        rows = session.query(DBListing.country, DBListing.city).distinct().all()
        cities = sorted({city for _, city in rows if city})
        countries = sorted({country for country, _ in rows if country})
        cities_by_country = {}
        for country, city in rows:
            if not country or not city:
                continue
            cities_by_country.setdefault(country, set()).add(city)
        cities_by_country = {country: sorted(list(cities)) for country, cities in cities_by_country.items()}
        types = [t[0] for t in session.query(DBListing.property_type).distinct().all() if t[0]]
        types = sorted(set(types))
    finally:
        session.close()
    return cities, types, countries, cities_by_country


@st.cache_data(ttl=900)
def _rank_images(image_urls: list[str], max_images: int = 6) -> list[str]:
    if not image_urls:
        return []
    selection = image_selector.select(image_urls, max_images=max_images)
    if selection and selection.selected:
        return [item.url for item in selection.selected]
    return list(image_urls)[:max_images]


@st.cache_data(ttl=120)
def load_pipeline_status():
    try:
        return PipelineStateService().snapshot().to_dict()
    except Exception as e:
        return {"error": str(e), "needs_refresh": False, "reasons": ["status_unavailable"]}


def _ensure_session_defaults(available_cities, available_types, available_countries, cities_by_country):
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


def _log_orchestrator(role: str, text: str) -> None:
    st.session_state.orchestrator_log.append({"role": role, "text": text})


def _reset_filters(available_cities, available_types, available_countries) -> None:
    st.session_state.selected_country = "All"
    st.session_state.selected_city = "All"
    st.session_state.selected_types = list(available_types)
    st.session_state.price_range = DEFAULT_PRICE_RANGE
    st.session_state.max_listings = 300
    st.session_state.sort_by = "Deal Score"
    st.session_state.sort_order = "Desc"
    st.session_state.scout_profile = "Balanced"


def _select_projection(projections: list, target_months: int = 12):
    if not projections:
        return None
    try:
        exact = [p for p in projections if getattr(p, "months_future", None) == target_months]
        if exact:
            return exact[0]
        return min(
            projections,
            key=lambda p: abs(getattr(p, "months_future", target_months) - target_months),
        )
    except Exception:
        return None


def _apply_action(action, available_cities, available_types, available_countries):
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
        _reset_filters(available_cities, available_types, available_countries)
    elif kind == "preflight":
        api = PipelineAPI()
        with st.spinner("Refreshing pipeline artifacts..."):
            api.preflight()
        load_pipeline_status.clear()
        load_filter_options.clear()


available_cities, available_types, available_countries, cities_by_country = load_filter_options()
_ensure_session_defaults(available_cities, available_types, available_countries, cities_by_country)

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

top_nav = st.container()

# --- Sidebar: Mission Control & Filters ---
with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand">
            <span style="font-family:'Fraunces',serif; font-size:1.4rem; color:#0f2136;">Scout OS</span>
            <div style="font-size:0.7rem; color:#6b635c; letter-spacing:0.2em; text-transform:uppercase;">Property Scanner</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("---")
    
    # 1. Lens Filters
    with st.expander("Your Lens", expanded=True):
        selected_country = st.selectbox("Country", ["All"] + available_countries, key="selected_country")
        city_pool = available_cities if selected_country == "All" else cities_by_country.get(selected_country, [])
        selected_city = st.selectbox("City", ["All"] + city_pool, key="selected_city")
        selected_types = st.multiselect(
            "Property Type",
            available_types,
            default=st.session_state.selected_types,
            key="selected_types",
        )
        min_price, max_price = st.slider(
            "Budget", 0, 2000000, (120000, 1200000), key="price_range", step=10000, format="%d€"
        )
        st.caption(f"Scout focus (AI-managed): {st.session_state.scout_profile}")

    # 2. Quick Actions (Condensed)
    st.markdown("##### Quick moves")
    qa_cols = st.columns(2)
    if qa_cols[0].button("Reset lens", use_container_width=True):
        _reset_filters(available_cities, available_types, available_countries)
        st.rerun()
    if qa_cols[1].button("Refresh signals", use_container_width=True):
        _apply_action({"type": "preflight"}, available_cities, available_types, available_countries)
        st.rerun()

    # 3. System Health
    with st.expander("System status", expanded=False):
        st.caption(f"Pipeline: {pipeline_state_text}")
        st.progress(100 if pipeline_badge == "Live" else 50)
        st.text(f"Listings tracked: {pipeline_listings}")
        st.text(f"Listings updated: {pipeline_listings_at}")


# --- Load Data ---
max_listings = st.session_state.max_listings
session = storage.get_session()
raw_rows = []
failed_valuations = 0
try:
    query = session.query(DBListing).order_by(DBListing.updated_at.desc())
    if selected_country != "All":
        query = query.filter(DBListing.country == selected_country)
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

        evidence_payload = None
        if cached_val:
            evidence_payload = cached_val.evidence.get("evidence", {}) if cached_val.evidence else {}
        elif analysis.evidence:
            try:
                evidence_payload = analysis.evidence.dict()
            except Exception:
                evidence_payload = None

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

        projected_value_12m = None
        price_return_12m_pct = None
        if listing.price and listing.price > 0:
            proj_12m = _select_projection(getattr(analysis, "projections", []), 12)
            if proj_12m and getattr(proj_12m, "predicted_value", None):
                projected_value_12m = float(proj_12m.predicted_value)
                price_return_12m_pct = (
                    (projected_value_12m - listing.price) / listing.price
                ) * 100
            elif value_delta_pct is not None:
                price_return_12m_pct = value_delta_pct * 100

        total_return_12m_pct = None
        if price_return_12m_pct is not None or yield_est is not None:
            total_return_12m_pct = (price_return_12m_pct or 0.0) + (yield_est or 0.0)

        ranked_images = _rank_images([str(url) for url in listing.image_urls] if listing.image_urls else [])
        raw_rows.append(
            {
                "ID": listing.id,
                "Title": listing.title,
                "Price": listing.price,
                "Sqm": listing.surface_area_sqm,
                "Bedrooms": listing.bedrooms,
                "City": listing.location.city if listing.location else None,
                "Country": listing.location.country if listing.location else None,
                "Property Type": str(listing.property_type),
                "Deal Score": analysis.deal_score,
                "Fair Value": analysis.fair_value_estimate,
                "Uncertainty %": analysis.fair_value_uncertainty_pct,
                "Value Delta": value_delta,
                "Value Delta %": value_delta_pct,
                "Projected Value 12m": projected_value_12m,
                "Price Return 12m %": price_return_12m_pct,
                "Total Return 12m %": total_return_12m_pct,
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
                "Image": ranked_images[0] if ranked_images else None,
                "Images": ranked_images,
                "Desc": listing.description,
                "VLM Desc": listing.vlm_description,
                "Projections": analysis.projections,
                "Rent Projections": getattr(analysis, "rent_projections", []),
                "Yield Projections": getattr(analysis, "yield_projections", []),
                "Signals": signals,
                "Evidence": evidence_payload,
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
        "<div class='empty-state'><h2>No listings yet</h2><p>Run a harvest or backfill to load listings.</p></div>",
        unsafe_allow_html=True,
    )
    st.stop()

# --- Normalize & Filter ---
for col in [
    "Yield %",
    "Deal Score",
    "Value Delta %",
    "Momentum %",
    "Area Sentiment",
    "Price Return 12m %",
    "Total Return 12m %",
]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

filtered_df = df.copy()
filtered_df["Yield %"] = filtered_df["Yield %"].fillna(0)
filtered_df["Momentum %"] = filtered_df["Momentum %"].fillna(0)
filtered_df["Area Sentiment"] = filtered_df["Area Sentiment"].fillna(0.5)
filtered_df["Value Delta %"] = filtered_df["Value Delta %"].fillna(0)

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

if not filtered_df.empty:
    titles = list(filtered_df["Title"].unique())
    if st.session_state.selected_title not in titles:
        st.session_state.selected_title = titles[0]
else:
    st.session_state.selected_title = None

with top_nav:
    orchestrator_prompt = _compose_orchestrator_prompt(
        filtered_df, pipeline_needs_refresh, pipeline_error
    )
    st.markdown("### Ask the Scout")
    nav_col, suggest_col = st.columns([1.4, 1], gap="large")

    with nav_col:
        st.markdown("#### Tell me what you need")
        st.info(orchestrator_prompt, icon="🤖")
        st.caption(f"Scout focus: {scout_profile} • Ranked by {sort_key}")

        with st.form("mission_form_main", clear_on_submit=True):
            prompt = st.text_area(
                "Your request",
                key="orchestrator_input",
                placeholder="e.g. 'Show me undervalued 2-beds in Madrid'",
                height=90,
                label_visibility="collapsed",
            )
            c1, c2 = st.columns([1, 1])
            autonomy_mode = c1.selectbox(
                "Mode",
                options=["Advisory", "Assisted", "Autopilot"],
                key="autonomy_mode",
                label_visibility="collapsed",
            )
            refresh = c2.checkbox(
                "Allow refreshes", key="allow_refresh", help="Let me pull fresh data when needed"
            )
            submitted = st.form_submit_button("Scout it", use_container_width=True)

        if submitted and prompt:
            _log_orchestrator("user", prompt)
            actions, response = _parse_prompt(
                prompt, available_countries, available_cities, available_types
            )
            _log_orchestrator("assistant", response)
            st.session_state.ai_response = response
            auto_actions, pending = _resolve_autonomy(actions, autonomy_mode, refresh)
            st.session_state.last_plan = [
                {"label": _action_label(a), "status": "auto" if a in auto_actions else "approval"}
                for a in actions
            ]
            st.session_state.pending_actions = pending
            if auto_actions:
                for action in auto_actions:
                    _apply_action(action, available_cities, available_types, available_countries)
                st.rerun()

        if st.session_state.ai_response and not st.session_state.pending_actions:
            st.info(st.session_state.ai_response, icon="🤖")

        if st.session_state.pending_actions:
            st.markdown("##### Awaiting your OK")
            if st.button("Approve all", key="approve_all", use_container_width=True):
                for action in st.session_state.pending_actions:
                    _apply_action(action, available_cities, available_types, available_countries)
                st.session_state.pending_actions = []
                st.rerun()

            for idx, action in enumerate(st.session_state.pending_actions):
                with st.expander(f"{_action_label(action)}", expanded=True):
                    if st.button("Approve", key=f"app_{idx}"):
                        _apply_action(action, available_cities, available_types, available_countries)
                        st.session_state.pending_actions.pop(idx)
                        st.rerun()

    with suggest_col:
        st.markdown("#### Suggested next moves")
        suggestions = _build_suggestions(
            filtered_df,
            pipeline_needs_refresh,
            available_cities,
            available_countries,
            st.session_state.price_range,
        )
        if suggestions:
            action_grid = st.columns(2)
            for idx, suggestion in enumerate(suggestions[:4]):
                col = action_grid[idx % 2]
                col.markdown(f"**{suggestion['title']}**")
                col.caption(suggestion["body"])
                if col.button(
                    suggestion["cta"],
                    key=f"quick_action_{idx}",
                    use_container_width=True,
                    help=suggestion["body"],
                ):
                    log = suggestion.get("log")
                    if log:
                        _log_orchestrator("assistant", log)
                    _apply_action(
                        suggestion["action"],
                        available_cities,
                        available_types,
                        available_countries,
                    )
                    st.rerun()
        else:
            st.caption("No quick moves right now.")

    st.divider()

left_col, right_col = st.columns([1.35, 1], gap="large")

with left_col:
    # --- Scout Briefing (collapsed to keep functionality on top) ---
    with st.expander("Scout Briefing", expanded=False):
        st.markdown("#### Market pulse")
        avg_price = filtered_df["Price"].mean() if not filtered_df.empty else 0
        avg_price = float(avg_price) if pd.notna(avg_price) else 0
        avg_yield = filtered_df["Yield %"].mean() if not filtered_df.empty else 0
        avg_yield = float(avg_yield) if pd.notna(avg_yield) else 0
        median_delta = filtered_df["Value Delta %"].median() if not filtered_df.empty else 0
        median_delta = float(median_delta) if pd.notna(median_delta) else 0
        avg_momentum = filtered_df["Momentum %"].mean() if not filtered_df.empty else 0
        avg_momentum = float(avg_momentum) if pd.notna(avg_momentum) else 0
        avg_return = filtered_df["Total Return 12m %"].mean() if not filtered_df.empty else 0
        avg_return = float(avg_return) if pd.notna(avg_return) else 0
        avg_liquidity = filtered_df["Liquidity"].mean() if not filtered_df.empty else 0.5
        avg_liquidity = float(avg_liquidity) if pd.notna(avg_liquidity) else 0.5
        avg_area = filtered_df["Area Sentiment"].mean() if not filtered_df.empty else 0.5
        avg_area = float(avg_area) if pd.notna(avg_area) else 0.5

        momentum_score = np.tanh((avg_momentum or 0) / 4.0)
        liquidity_score = (avg_liquidity or 0.5) - 0.5
        area_score = (avg_area or 0.5) - 0.5
        market_heat_index = int(np.clip(50 + 30 * momentum_score + 25 * liquidity_score + 20 * area_score, 0, 100))

        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric("Signal pulse", market_heat_index, help="Momentum-driven composite index")
        m2.metric("Opportunities", len(filtered_df))
        m3.metric("Avg yield", f"{avg_yield:.2f}%")
        m4.metric("Avg return 12m", f"{avg_return:+.1f}%")
        m5.metric("Value gap", f"{median_delta * 100:+.1f}%")
        m6.metric("Avg price", f"{avg_price/1000:.0f}k")

    st.divider()

    # --- Main Navigation (Tabs) ---
    tab_flow, tab_memo, tab_lab = st.tabs(["📋 Deal Flow", "📑 Memo", "🧪 Signal Lab"])

    # --- TAB: DEAL FLOW ---
    with tab_flow:
        if scout_picks:
            st.markdown("**Scout picks**")
            pick_cols = st.columns(len(scout_picks))
            for col, pick in zip(pick_cols, scout_picks):
                with col:
                    row = pick["row"]
                    label = pick["label"]

                    img_url = row.get("Image")
                    if img_url and isinstance(img_url, str):
                        st.image(img_url, use_container_width=True)
                    else:
                        st.markdown(
                            "<div style='height: 120px; background: #eee; display:flex; align-items:center; "
                            "justify-content:center; color:#888;'>Image coming soon</div>",
                            unsafe_allow_html=True,
                        )

                    st.caption(label)
                    st.markdown(f"**{row['Title']}**")
                    location = _format_location(row.get("City"), row.get("Country"))
                    st.caption(f"{location} • {row['Price']:,.0f} €")
                    total_return = _safe_num(row.get("Total Return 12m %"), None)
                    total_return_label = f"{total_return:+.1f}%" if total_return is not None else "n/a"
                    st.markdown(
                        f"Return 12m: **{total_return_label}** "
                        f"| Yield: **{row['Yield %']:.2f}%**"
                    )
                    if row.get("Intel Summary"):
                        st.caption(row["Intel Summary"])
                    if st.button("View Memo", key=f"btn_view_{row['ID']}"):
                        st.session_state.selected_title = row["Title"]
                        st.session_state.active_view = "Investment Memo"
                        st.toast(
                            f"Selected {row['Title']}. Open the Memo tab to view details."
                        )
        else:
            st.caption("No picks under this lens yet.")

        st.markdown("---")

        display_cols = [
            "Title",
            "Price",
            "Total Return 12m %",
            "Yield %",
            "Deal Score",
            "Value Delta %",
            "Momentum %",
            "City",
            "Country",
            "Intel Summary",
            "URL",
        ]
        st.dataframe(
            filtered_df[display_cols].style.format(
                {
                    "Price": "{:,.0f} EUR",
                    "Total Return 12m %": "{:+.1f}%",
                    "Yield %": "{:.2f}%",
                    "Deal Score": "{:.2f}",
                    "Value Delta %": "{:+.1f}%",
                    "Momentum %": "{:+.1f}%",
                }
            ),
            use_container_width=True,
            height=500,
            column_config={
                "URL": st.column_config.LinkColumn("Listing", display_text="Open"),
            },
        )

    # --- TAB: MEMO ---
    with tab_memo:
        if not filtered_df.empty:
            current_titles = list(filtered_df["Title"].unique())
            if st.session_state.selected_title not in current_titles:
                st.session_state.selected_title = current_titles[0]

            selected_title = st.selectbox(
                "Pick a property",
                current_titles,
                index=current_titles.index(st.session_state.selected_title),
                key="selected_title_box",
            )
            st.session_state.selected_title = selected_title

            item = filtered_df[filtered_df["Title"] == selected_title].iloc[0]
            reasons = _build_deal_reasons(item, scout_profile)

            m_col1, m_col2 = st.columns([1, 1])

            with m_col1:
                images = _safe_list(item.get("Images"))
                if images:
                    st.image(str(images[0]), use_container_width=True)
                    with st.expander(f"Gallery ({len(images)})"):
                        st.image(images[:5], use_container_width=True)
                else:
                    st.info("No images yet.")

                st.markdown("### Scout Notes")
                st.info(item.get("VLM Desc") or "No vision summary yet.")
                st.text_area(
                    "Listing description", item.get("Desc") or "No description yet.", height=150
                )

            with m_col2:
                st.markdown(f"## {item.get('Title')}")
                location = _format_location(item.get("City"), item.get("Country"))
                st.caption(f"{location} | {item.get('Property Type')}")

                f1, f2, f3 = st.columns(3)
                f1.metric("Ask Price", f"{item.get('Price'):,.0f} €")
                f2.metric(
                    "Fair Value",
                    f"{item.get('Fair Value'):,.0f} €",
                    delta=f"{item.get('Value Delta %') * 100:+.1f}%",
                )
                f3.metric("Deal Score", f"{item.get('Deal Score'):.2f}")

                f4, f5, f6, f7 = st.columns(4)
                f4.metric("Est. Rent", f"{item.get('Rent Est'):,.0f} €")
                f5.metric("Gross Yield", f"{item.get('Yield %'):.2f}%")
                f6.metric("Market Yield", f"{item.get('Market Yield %'):.2f}%")
                total_return = _safe_num(item.get("Total Return 12m %"), None)
                total_return_label = f"{total_return:+.1f}%" if total_return is not None else "n/a"
                f7.metric("Return 12m", total_return_label)

                st.markdown("### Why it matters")
                st.warning(item.get("Thesis") or "Analysis is on its way.")

                if reasons:
                    st.markdown("### Why we like it")
                    st.markdown("\n".join([f"- {reason}" for reason in reasons]))

                intel_summary = item.get("Intel Summary")
                if intel_summary:
                    st.markdown("### Quick take")
                    st.info(intel_summary)

                st.markdown("### Deep signal readout")
                evidence = item.get("Evidence") or {}
                s_col1, s_col2 = st.columns(2, gap="large")

                with s_col1:
                    st.markdown("#### Value stack")
                    ask_price = _safe_num(item.get("Price"), None)
                    fair_value = _safe_num(item.get("Fair Value"), None)
                    uncertainty = _safe_num(item.get("Uncertainty %"), 0.1)
                    anchor_price = _safe_num(
                        evidence.get("anchor_price")
                        if isinstance(evidence, dict)
                        else None,
                        None,
                    )

                    value_rows = []
                    if ask_price:
                        value_rows.append({"Metric": "Ask", "EUR": ask_price})
                    if anchor_price:
                        value_rows.append({"Metric": "Comp Anchor", "EUR": anchor_price})
                    if fair_value:
                        value_rows.append({"Metric": "Fair Value", "EUR": fair_value})

                    if value_rows:
                        value_df = pd.DataFrame(value_rows).set_index("Metric")
                        st.bar_chart(value_df, height=220)
                        if fair_value and uncertainty is not None:
                            low = fair_value * (1 - uncertainty)
                            high = fair_value * (1 + uncertainty)
                            st.caption(f"Fair value range: €{low:,.0f} – €{high:,.0f}")
                    else:
                        st.caption("Not enough data to build the value stack yet.")

                    st.markdown("#### Yield vs market")
                    yield_est = _safe_num(item.get("Yield %"), None)
                    market_yield = _safe_num(item.get("Market Yield %"), None)
                    if yield_est is not None or market_yield is not None:
                        yield_rows = []
                        if yield_est is not None:
                            yield_rows.append({"Metric": "Listing", "Yield %": yield_est})
                        if market_yield is not None:
                            yield_rows.append({"Metric": "Market", "Yield %": market_yield})
                        yield_df = pd.DataFrame(yield_rows).set_index("Metric")
                        st.bar_chart(yield_df, height=180)
                        if yield_est is not None and market_yield is not None:
                            spread = yield_est - market_yield
                            st.caption(f"Yield spread: {spread:+.2f}pp")
                    else:
                        st.caption("Yield signals aren't available yet.")

                with s_col2:
                    st.markdown("#### Comp price map")
                    comp_rows = []
                    if isinstance(evidence, dict) and evidence.get("top_comps"):
                        for comp in evidence.get("top_comps", []):
                            price = _safe_num(
                                comp.get("adj_price") or comp.get("raw_price"), None
                            )
                            similarity = _safe_num(
                                comp.get("similarity_score")
                                or comp.get("attention_weight"),
                                0.0,
                            )
                            if price:
                                comp_rows.append(
                                    {"Price": price, "Similarity": similarity}
                                )
                    if not comp_rows:
                        comps = _safe_list(item.get("Comps"))
                        for comp in comps:
                            price = _safe_num(getattr(comp, "price", None), None)
                            similarity = _safe_num(
                                getattr(comp, "similarity_score", None), 0.0
                            )
                            if price:
                                comp_rows.append(
                                    {"Price": price, "Similarity": similarity}
                                )
                    if comp_rows:
                        comp_df = pd.DataFrame(comp_rows)
                        st.scatter_chart(comp_df, x="Price", y="Similarity", height=240)
                        st.caption(
                            "Higher similarity means closer comps; prices are time-adjusted when available."
                        )
                    else:
                        st.caption("No comps to chart yet.")

                st.markdown("### Forecast")
                projections = _safe_list(item.get("Projections"))
                if projections:
                    proj_df = pd.DataFrame(
                        [
                            {"Month": p.months_future, "Euro": p.predicted_value}
                            for p in projections
                        ]
                    )
                    st.line_chart(proj_df.set_index("Month"), height=200)

                st.markdown("### Comparable sales")
                comps = _safe_list(item.get("Comps"))
                if comps:
                    c_data = []
                    for c in comps[:3]:
                        c_data.append(
                            {
                                "Price": c.price,
                                "Sqm": c.features.get("sqm") if c.features else 0,
                                "Similarity": c.similarity_score,
                            }
                        )
                    st.dataframe(c_data, use_container_width=True)
                else:
                    st.caption("No comps yet.")

        else:
            st.info("No listings match this lens. Try widening the filters.")

    # --- TAB: SIGNAL LAB ---
    with tab_lab:
        l_col1, l_col2 = st.columns(2)
        with l_col1:
            st.markdown("#### Yield vs Value")
            if not filtered_df.empty:
                st.scatter_chart(
                    filtered_df, x="Yield %", y="Value Delta %", color="Deal Score", height=350
                )
        with l_col2:
            st.markdown("#### Momentum spread")
            if not filtered_df.empty:
                st.bar_chart(filtered_df["Momentum %"], height=350)

with right_col:
    st.markdown("### Live map")
    import pydeck as pdk

    map_data = filtered_df.dropna(subset=["lat", "lon"]).copy()
    if not map_data.empty:
        map_pick_rows = []
        for pick in scout_picks:
            row = pick["row"]
            if pd.notna(row.get("lat")) and pd.notna(row.get("lon")):
                map_pick_rows.append(row.to_dict())

        if map_pick_rows:
            top_map_picks = pd.DataFrame(map_pick_rows)
        else:
            top_map_picks = map_data.sort_values(by=sort_key, ascending=ascending).head(4)

        keep_cols = [
            "lat",
            "lon",
            "Title",
            "City",
            "Country",
            "Price",
            "Yield %",
            "Deal Score",
            "Image",
            "Intel Summary",
        ]
        map_data = map_data[keep_cols]
        map_data["Image"] = map_data["Image"].astype(str)

        def get_score_color(score, is_focused: bool = False):
            if is_focused:
                return [209, 136, 69, 255]

            score = _safe_num(score, 0.0) or 0.0
            score = max(0.0, min(score, 1.0))
            base = np.array([55, 80, 107])
            mid = np.array([47, 111, 98])
            peak = np.array([193, 147, 91])
            if score < 0.5:
                ratio = score / 0.5
                color = base + (mid - base) * ratio
            else:
                ratio = (score - 0.5) / 0.5
                color = mid + (peak - mid) * ratio
            return [int(c) for c in color] + [190]

        map_data["color"] = map_data["Deal Score"].apply(lambda x: get_score_color(x))

        focused_row = None
        if "selected_title" in st.session_state and st.session_state.selected_title:
            match = map_data[map_data["Title"] == st.session_state.selected_title]
            if not match.empty:
                focused_row = match.iloc[0]

        if focused_row is not None:
            view_state = pdk.ViewState(
                latitude=focused_row["lat"],
                longitude=focused_row["lon"],
                zoom=14.6,
                pitch=45,
                bearing=-10,
                transition_duration=1200,
                transition_easing="TRANSITION_EASING_CUBIC_IN_OUT",
            )
            map_data["radius"] = map_data["Title"].apply(
                lambda t: 220 if t == st.session_state.selected_title else 70
            )
            map_data["color"] = map_data.apply(
                lambda r: get_score_color(
                    r["Deal Score"],
                    is_focused=(r["Title"] == st.session_state.selected_title),
                ),
                axis=1,
            )
        else:
            view_state = pdk.ViewState(
                latitude=map_data["lat"].mean(),
                longitude=map_data["lon"].mean(),
                zoom=11.4,
                pitch=0,
                bearing=0,
                transition_duration=1200,
            )
            map_data["radius"] = 90

        st.pydeck_chart(
            pdk.Deck(
                map_provider="carto",
                map_style="positron",
                initial_view_state=view_state,
                layers=[
                    pdk.Layer(
                        "ScatterplotLayer",
                        data=map_data,
                        get_position="[lon, lat]",
                        get_fill_color="color",
                        get_radius="radius",
                        pickable=True,
                        auto_highlight=True,
                        stroked=True,
                        get_line_color=[248, 245, 239],
                        line_width_min_pixels=1,
                        opacity=0.9,
                    )
                ],
                tooltip={
                    "html": (
                        "<div style='color:#151310; font-family:\"Sora\", sans-serif;'>"
                        "<b>{Title}</b><br/>{City}<br/>€{Price}"
                        "</div>"
                    )
                },
            ),
            use_container_width=True
        )

        st.markdown("#### Spotlight")
        st.caption("Pick a listing to zoom in and explore.")

        if focused_row is not None:
            if st.button("Reset View", key="reset_map_view"):
                if "selected_title" in st.session_state:
                    del st.session_state.selected_title
                st.rerun()

        cols = st.columns(2)
        for idx, (_, row) in enumerate(top_map_picks.iterrows()):
            col = cols[idx % 2]
            with col:
                is_active = (focused_row is not None) and (row["Title"] == focused_row["Title"])
                border_color = "2px solid var(--accent)" if is_active else "1px solid rgba(21, 19, 16, 0.12)"
                bg_color = "var(--bg-veil)" if is_active else "var(--surface-strong)"
                location = _format_location(row.get("City"), row.get("Country"))

                st.markdown(
                    f"""
                    <div style="
                        border: {border_color};
                        background: {bg_color};
                        padding: 12px;
                        border-radius: 14px;
                        margin-bottom: 10px;
                    ">
                        <div style="font-size:0.85rem; font-weight:bold;">{row['Title']}</div>
                        <div style="font-size:0.75rem; color:var(--muted);">{location}</div>
                        <div style="font-size:0.9rem; color:var(--accent-3); margin-top:4px;">{row['Yield %']:.1f}% Yield</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                if row.get("Intel Summary"):
                    st.caption(row["Intel Summary"])

                if st.button("Focus", key=f"focus_{idx}"):
                    st.session_state.selected_title = row["Title"]
                    st.rerun()

    else:
        st.info("No mapped listings yet.")
