from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
from streamlit.testing.v1 import AppTest


_DASHBOARD_WRAPPER_SCRIPT = dedent(
    """
    import sys

    import pandas as pd

    _IMAGE_DATA = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4//8/AwAI/AL+X4VpWQAAAABJRU5ErkJggg=="
    )


    def _fixture_df():
        return pd.DataFrame(
            [
                {
                    "ID": "l1",
                    "Title": "Madrid Center Loft",
                    "Price": 250000.0,
                    "Sqm": 75.0,
                    "Bedrooms": 2,
                    "City": "Madrid",
                    "Country": "Spain",
                    "Property Type": "apartment",
                    "Deal Score": 0.82,
                    "Fair Value": 275000.0,
                    "Uncertainty %": 0.08,
                    "Value Delta": 25000.0,
                    "Value Delta %": 0.10,
                    "Projected Value 12m": 285000.0,
                    "Price Return 12m %": 14.0,
                    "Total Return 12m %": 18.0,
                    "Rent Est": 1250.0,
                    "Yield %": 4.8,
                    "Market Yield %": 4.1,
                    "Price-to-Rent (yrs)": 17.0,
                    "Market P/R (yrs)": 19.0,
                    "Momentum %": 3.1,
                    "Area Sentiment": 0.63,
                    "Area Development": 0.58,
                    "Intel": "Central location",
                    "Evidence": {},
                    "Images": [_IMAGE_DATA],
                    "lat": 40.4168,
                    "lon": -3.7038,
                },
                {
                    "ID": "l2",
                    "Title": "Barcelona Beach Flat",
                    "Price": 410000.0,
                    "Sqm": 90.0,
                    "Bedrooms": 3,
                    "City": "Barcelona",
                    "Country": "Spain",
                    "Property Type": "apartment",
                    "Deal Score": 0.77,
                    "Fair Value": 430000.0,
                    "Uncertainty %": 0.09,
                    "Value Delta": 20000.0,
                    "Value Delta %": 0.049,
                    "Projected Value 12m": 445000.0,
                    "Price Return 12m %": 8.5,
                    "Total Return 12m %": 12.3,
                    "Rent Est": 1650.0,
                    "Yield %": 3.8,
                    "Market Yield %": 3.5,
                    "Price-to-Rent (yrs)": 20.7,
                    "Market P/R (yrs)": 21.2,
                    "Momentum %": 2.4,
                    "Area Sentiment": 0.66,
                    "Area Development": 0.64,
                    "Intel": "Near transport",
                    "Evidence": {},
                    "Images": [_IMAGE_DATA],
                    "lat": 41.3874,
                    "lon": 2.1686,
                },
                {
                    "ID": "l3",
                    "Title": "Lisbon Value Deal",
                    "Price": 180000.0,
                    "Sqm": 68.0,
                    "Bedrooms": 2,
                    "City": "Lisbon",
                    "Country": "Portugal",
                    "Property Type": "apartment",
                    "Deal Score": 0.88,
                    "Fair Value": 220000.0,
                    "Uncertainty %": 0.10,
                    "Value Delta": 40000.0,
                    "Value Delta %": 0.222,
                    "Projected Value 12m": 235000.0,
                    "Price Return 12m %": 30.6,
                    "Total Return 12m %": 35.1,
                    "Rent Est": 980.0,
                    "Yield %": 6.0,
                    "Market Yield %": 4.9,
                    "Price-to-Rent (yrs)": 15.3,
                    "Market P/R (yrs)": 18.5,
                    "Momentum %": 4.9,
                    "Area Sentiment": 0.71,
                    "Area Development": 0.70,
                    "Intel": "Strong spread",
                    "Evidence": {},
                    "Images": [_IMAGE_DATA],
                    "lat": 38.7223,
                    "lon": -9.1393,
                },
            ]
        )


    def _fetch_listings_dataframe(
        _storage,
        _valuation,
        _retriever,
        selected_country,
        selected_city,
        selected_types,
        max_listings=300,
    ):
        df = _fixture_df()
        if selected_country != "All":
            df = df[df["Country"] == selected_country]
        if selected_city != "All":
            df = df[df["City"] == selected_city]
        if selected_types:
            df = df[df["Property Type"].isin(selected_types)]
        return df.head(max_listings).reset_index(drop=True)


    class _FakeOrchestrator:
        def plan(self, prompt, areas, strategy):
            return {
                "steps": [
                    {
                        "action": "preflight",
                        "params": {"max_pages": 1},
                        "rationale": "refresh first",
                    }
                ]
            }

        def run(self, prompt, areas, plan=None, strategy="balanced"):
            return {
                "plan": plan,
                "final_report": "Done",
                "evaluations": [{"listing_id": "l3", "deal_score": 0.91}],
                "messages": [{"role": "assistant", "content": "ok"}],
                "quality_checks": [{"check": "coverage", "status": "pass", "detail": "ok"}],
                "trace": [{"action": "evaluate", "status": "ok", "duration_ms": 10}],
                "ui_blocks": [
                    {
                        "type": "comparison_table",
                        "title": "Top picks",
                        "listing_ids": ["l3", "l1"],
                        "columns": ["Deal Score", "Price"],
                    }
                ],
                "run_id": "run-1",
            }


    class _FakeMemoryStore:
        def list_recent(self, limit=5):
            return [{"status": "success", "query": "q1", "target_areas": ["Madrid"], "summary": "s1"}]


    import src.interfaces.dashboard.services.loaders as loaders
    import src.agentic.memory as memory_module
    import src.agentic.orchestrator as orchestrator_module

    loaders.get_services = lambda: (object(), object(), object(), object())
    loaders.load_filter_options = lambda _storage: (
        ["Madrid", "Barcelona", "Lisbon"],
        ["apartment"],
        ["Portugal", "Spain"],
        {"Spain": ["Barcelona", "Madrid"], "Portugal": ["Lisbon"]},
    )
    loaders.load_pipeline_status = lambda: {
        "needs_refresh": False,
        "error": None,
        "listings_count": 3,
        "listings_last_seen": "2026-02-09T12:00:00Z",
        "source_support": {
            "doc_path": "docs/crawler_status.md",
            "summary": {"supported": 3, "blocked": 2, "experimental": 1},
            "sources": [
                {"id": "pisos", "name": "Pisos.com", "runtime_label": "supported"},
                {"id": "onthemarket_uk", "name": "OnTheMarket", "runtime_label": "supported"},
                {"id": "rightmove_uk", "name": "Rightmove UK", "runtime_label": "supported"},
                {"id": "realtor_us", "name": "Realtor.com", "runtime_label": "blocked"},
                {"id": "redfin_us", "name": "Redfin", "runtime_label": "blocked"},
                {"id": "idealista", "name": "Idealista", "runtime_label": "experimental"},
            ],
        },
        "assumption_badges": [
            {
                "id": "source_coverage",
                "label": "Source coverage caveat",
                "status": "CAUTION",
                "artifact_ids": ["lit-case-shiller-1988"],
                "summary": "3 supported, 2 blocked, 1 experimental sources; review crawler caveats.",
                "guide_path": "docs/crawler_status.md",
            },
            {
                "id": "conditional_coverage",
                "label": "Conformal coverage scope",
                "status": "CAUTION",
                "artifact_ids": ["lit-conformal-tutorial-2021"],
                "summary": "Coverage is marginal and should be monitored by segment.",
                "guide_path": "docs/manifest/07_observability.md",
            },
        ],
    }
    loaders.fetch_listings_dataframe = _fetch_listings_dataframe
    loaders.rank_images = lambda image_urls, max_images=6, _image_selector=None: list(image_urls)[:max_images]
    loaders.rank_images_sample = (
        lambda image_urls, sample_size=5, _image_selector=None: list(image_urls)[:sample_size]
    )

    orchestrator_module.CognitiveOrchestrator = _FakeOrchestrator
    memory_module.AgentMemoryStore = _FakeMemoryStore

    # Force app module re-exec on each AppTest rerun.
    sys.modules.pop("src.interfaces.dashboard.app", None)
    import src.interfaces.dashboard.app  # noqa: F401
    """
)


def _write_dashboard_wrapper(tmp_path: Path) -> Path:
    wrapper = tmp_path / "dashboard_app_wrapper.py"
    wrapper.write_text(_DASHBOARD_WRAPPER_SCRIPT, encoding="utf-8")
    return wrapper


def _assert_no_exceptions(app: AppTest) -> None:
    assert len(app.exception) == 0, [exc.message for exc in app.exception]


def _find_button_index(app: AppTest, label: str) -> int:
    for index, button in enumerate(app.button):
        if button.label == label:
            return index
    raise AssertionError(f"Button not found: {label}")


def _find_selectbox(app: AppTest, label: str):
    for selectbox in app.selectbox:
        if selectbox.label == label:
            return selectbox
    raise AssertionError(f"Selectbox not found: {label}")


def _find_radio(app: AppTest, label: str):
    for radio in app.radio:
        if radio.label == label:
            return radio
    raise AssertionError(f"Radio not found: {label}")


@pytest.mark.e2e
def test_dashboard_ui_smoke__renders_core_controls(tmp_path: Path) -> None:
    wrapper = _write_dashboard_wrapper(tmp_path)
    app = AppTest.from_file(str(wrapper))
    app.run(timeout=120)

    _assert_no_exceptions(app)
    assert any(button.label == "Scout it" for button in app.button)
    assert any("scout-command-center" in str(markdown.value) for markdown in app.markdown)
    assert any("### 📋 Deal Flow" in str(markdown.value) for markdown in app.markdown)
    assert list(_find_selectbox(app, "Country").options) == ["All", "Portugal", "Spain"]


@pytest.mark.e2e
def test_dashboard_ui_country_filter__narrows_city_and_cards(tmp_path: Path) -> None:
    wrapper = _write_dashboard_wrapper(tmp_path)
    app = AppTest.from_file(str(wrapper))
    app.run(timeout=120)
    _assert_no_exceptions(app)

    country = _find_selectbox(app, "Country")
    country.set_value("Portugal")
    app.run(timeout=120)

    _assert_no_exceptions(app)
    assert list(_find_selectbox(app, "City").options) == ["All", "Lisbon"]
    assert any("Lisbon Value Deal" in str(markdown.value) for markdown in app.markdown)
    assert not any("Madrid Center Loft" in str(markdown.value) for markdown in app.markdown)


@pytest.mark.e2e
def test_dashboard_ui_assisted_command__approval_then_run(tmp_path: Path) -> None:
    wrapper = _write_dashboard_wrapper(tmp_path)
    app = AppTest.from_file(str(wrapper))
    app.run(timeout=120)
    _assert_no_exceptions(app)

    assert len(app.text_input) == 1
    app.text_input[0].set_value("Find undervalued listings")
    app.run(timeout=120)
    _assert_no_exceptions(app)

    app.button[_find_button_index(app, "Scout it")].click()
    app.run(timeout=120)
    _assert_no_exceptions(app)
    assert any("Approval Required" in str(markdown.value) for markdown in app.markdown)
    assert any(button.label == "Approve & Run Plan" for button in app.button)

    app.button[_find_button_index(app, "Approve & Run Plan")].click()
    app.run(timeout=120)

    _assert_no_exceptions(app)
    assert app.session_state.agent_report == "Done"
    assert app.session_state.agent_run_id == "run-1"
    assert app.session_state.agent_requires_approval is False
    assert any("Agent Report" in str(markdown.value) for markdown in app.markdown)


@pytest.mark.e2e
def test_dashboard_ui_memo_button__switches_panel_without_session_error(tmp_path: Path) -> None:
    wrapper = _write_dashboard_wrapper(tmp_path)
    app = AppTest.from_file(str(wrapper))
    app.run(timeout=120)
    _assert_no_exceptions(app)

    app.button[_find_button_index(app, "Memo")].click()
    app.run(timeout=120)

    _assert_no_exceptions(app)
    assert _find_radio(app, "Panel").value == "📑 Memo"
    assert any("### 📑 Memo" in str(markdown.value) for markdown in app.markdown)
    assert app.session_state.selected_title in {"Madrid Center Loft", "Barcelona Beach Flat", "Lisbon Value Deal"}


@pytest.mark.e2e
def test_dashboard_ui_pipeline_status__shows_source_support_labels(tmp_path: Path) -> None:
    wrapper = _write_dashboard_wrapper(tmp_path)
    app = AppTest.from_file(str(wrapper))
    app.run(timeout=120)
    _assert_no_exceptions(app)

    _find_selectbox(app, "Insights").set_value("🧭 Pipeline Status")
    app.run(timeout=120)

    _assert_no_exceptions(app)
    caption_values = [str(caption.value) for caption in app.caption]
    assert any("Source labels: supported / blocked / experimental" in value for value in caption_values)
    assert any("Blocked examples: Realtor.com" in value for value in caption_values)
    assert any("Assumption badges:" in value for value in caption_values)
    assert any("lit-case-shiller-1988" in value for value in caption_values)
