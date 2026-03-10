# UI Verification Checklist

## Bet Tracking

- Prompt: `prompt-06-ui-e2e-verification-loop`
- Cycle stage: `build` (phase hint `phase_3`)
- Appetite: `medium`
- Now (single active packet): stabilize Streamlit dashboard critical flows with deterministic E2E coverage and fix memo-navigation session-state failures.
- Packet state: `downhill`
- Not now:
  - full browser/manual run against live preflight/crawl services.

## Command Map (UI)

- Canonical command map: `docs/manifest/09_runbook.md`.
- Key command IDs:
  - `CMD-DASHBOARD`: `python3 -m src.interfaces.cli dashboard`
  - `CMD-TEST-E2E-UI`: `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q`
  - `CMD-TEST-E2E`: `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e -m e2e`
  - `CMD-TEST-LIVE-UI`: `RUN_LIVE=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/live/ui/test_dashboard_live_browser__source_support.py -q`
  - `CMD-CI-COMMAND-MAP-CHECK`: `python3 scripts/check_command_map.py`

## Capability Inventory

- [x] **Lens filters (country/city/property-type/budget)**
  - Routes/screens: sidebar filter controls + lens HUD on the single-page dashboard.
  - UI entry code paths: `src/interfaces/dashboard/app.py`, `src/interfaces/dashboard/services/state.py`.
  - Data/API dependencies: `load_filter_options`, `fetch_listings_dataframe` (`src/interfaces/dashboard/services/loaders.py`).
  - Evidence: `tests/e2e/ui/test_dashboard_ui_verification_loop.py::test_dashboard_ui_smoke__renders_core_controls`, `tests/e2e/ui/test_dashboard_ui_verification_loop.py::test_dashboard_ui_country_filter__narrows_city_and_cards`.

- [x] **Scout Command Center (assisted plan + approval)**
  - Routes/screens: `Scout Command` form, `Approval Required` section, run-report surface.
  - UI entry code paths: `src/interfaces/dashboard/app.py` (`scout_command_center`, `_plan_requires_confirmation`, `_run_orchestrator`).
  - Data/API dependencies: `CognitiveOrchestrator.plan/run`, session-state report/trace fields.
  - Evidence: `tests/e2e/ui/test_dashboard_ui_verification_loop.py::test_dashboard_ui_assisted_command__approval_then_run`.

- [x] **Deal Flow and Memo panel transitions**
  - Routes/screens: `📋 Deal Flow` cards + `📑 Memo` detail panel.
  - UI entry code paths: `src/interfaces/dashboard/app.py` (panel radio and memo button handlers).
  - Data/API dependencies: listing dataframe fields (`Title`, `Price`, valuation metrics, images).
  - Evidence: `tests/e2e/ui/test_dashboard_ui_verification_loop.py::test_dashboard_ui_smoke__renders_core_controls`, `tests/e2e/ui/test_dashboard_ui_verification_loop.py::test_dashboard_ui_memo_button__switches_panel_without_session_error`.

- [x] **Insights and Atlas render path**
  - Routes/screens: `🧪 Signal Lab`, `🎯 Scout Picks`, `🧭 Pipeline Status`, `🗺 Atlas`.
  - UI entry code paths: `src/interfaces/dashboard/app.py` (insight selector + map block).
  - Data/API dependencies: filtered listing metrics + `load_pipeline_status`.
  - Evidence: smoke suite (`_assert_no_exceptions`) in `tests/e2e/ui/test_dashboard_ui_verification_loop.py`.

- [x] **Runtime source support/fallback + assumption badges**
  - Routes/screens: API response payloads and dashboard trust/status surfaces.
  - UI entry code paths: `src/interfaces/api/pipeline.py`, `src/interfaces/dashboard/app.py`.
  - Data/API dependencies: `PipelineAPI.pipeline_status` emits `source_support.summary`, `source_support.sources[*].runtime_label`, and `assumption_badges[*]`; dashboard renders labels/examples and assumption caveats in `🧭 Pipeline Status`.
  - Evidence: `tests/unit/interfaces/test_pipeline_api__source_support.py::test_source_support_summary__classifies_supported_blocked_fallback`, `tests/unit/interfaces/test_pipeline_api__source_support.py::test_pipeline_status__embeds_source_support_summary`, `tests/e2e/ui/test_dashboard_ui_verification_loop.py::test_dashboard_ui_pipeline_status__shows_source_support_labels`.

## Critical Flows

- [x] **CF-01: Dashboard boot renders core controls**
  - Preconditions: fixture-backed Streamlit AppTest wrapper.
  - Steps:
    1. Run dashboard wrapper.
    2. Render initial frame.
  - Expected results: no exceptions; `Scout it` and Deal Flow controls visible.
  - Failure signals: Streamlit exception element, missing controls.
  - Gating: none.
  - AC: baseline UI frame is stable and usable.
  - Verify: `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py::test_dashboard_ui_smoke__renders_core_controls -q`
  - Files: `tests/e2e/ui/test_dashboard_ui_verification_loop.py`
  - Docs: `docs/implementation/checklists/05_ui_verification.md`, `docs/implementation/reports/ui_verification_final_report.md`
  - Alternatives: browser-only harness (rejected for this packet due higher flake/cost).

- [x] **CF-02: Country filter narrows city options and cards**
  - Preconditions: fixture listings across Spain/Portugal.
  - Steps:
    1. Set `Country` to `Portugal`.
    2. Re-render frame.
  - Expected results: city options reduce to `All/Lisbon`; non-Portugal cards disappear.
  - Failure signals: stale city options, cross-country cards still visible.
  - Gating: none.
  - AC: selector and rendered listing set stay consistent.
  - Verify: `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py::test_dashboard_ui_country_filter__narrows_city_and_cards -q`
  - Files: `tests/e2e/ui/test_dashboard_ui_verification_loop.py`
  - Docs: `docs/implementation/checklists/05_ui_verification.md`, `docs/implementation/reports/ui_verification_final_report.md`
  - Alternatives: assert session-state only (rejected; misses user-visible behavior).

- [x] **CF-03: Assisted command requires approval then executes**
  - Preconditions: command input present; orchestrator reachable (fixture fake).
  - Steps:
    1. Enter scout prompt.
    2. Click `Scout it`.
    3. Confirm `Approval Required`.
    4. Click `Approve & Run Plan`.
  - Expected results: approval gate appears; run stores report/run-id; approval flag clears.
  - Failure signals: missing approval state, stale pending state, missing report.
  - Gating: none.
  - AC: assisted flow preserves two-step trust gate.
  - Verify: `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py::test_dashboard_ui_assisted_command__approval_then_run -q`
  - Files: `tests/e2e/ui/test_dashboard_ui_verification_loop.py`
  - Docs: `docs/implementation/checklists/05_ui_verification.md`, `docs/implementation/reports/ui_verification_final_report.md`
  - Alternatives: bypass approval path in tests (rejected).

- [x] **CF-04: Memo action switches to memo panel without session-state crash**
  - Preconditions: at least one deal card with `Memo` action.
  - Steps:
    1. Click `Memo` on a card.
    2. Re-render frame.
  - Expected results: panel switches to `📑 Memo`; selected title remains valid.
  - Failure signals: `StreamlitAPIException` about mutating `left_panel_view` after widget instantiation.
  - Gating: none.
  - AC: memo navigation path is exception-free and panel state is correct.
  - Verify: `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py::test_dashboard_ui_memo_button__switches_panel_without_session_error -q`
  - Files: `src/interfaces/dashboard/app.py`, `tests/e2e/ui/test_dashboard_ui_verification_loop.py`
  - Docs: `docs/implementation/checklists/05_ui_verification.md`, `docs/implementation/reports/ui_verification_final_report.md`
  - Alternatives: keep shared widget/session key (`left_panel_view`) (rejected: reproducible runtime exception).
  - State: `uphill` -> `downhill` after root-cause isolation and patch.

- [x] **CF-05: Pipeline Status panel exposes source labels and assumption badges**
  - Preconditions: pipeline status payload includes `source_support.summary` and per-source `runtime_label`.
  - Steps:
    1. Open `🧭 Pipeline Status` in Insights.
    2. Inspect support counts, example captions, and assumption badge captions.
  - Expected results: UI displays explicit `supported`, `blocked`, and `fallback` labels with source examples plus artifact-backed assumption badge lines and guide paths.
  - Failure signals: missing labels, empty example captions despite payload data, missing assumption badge captions, missing guide path.
  - Gating: none.
  - AC: trust labels and assumption caveat badges are visible in runtime UI surface.
  - Verify: `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py::test_dashboard_ui_pipeline_status__shows_source_support_labels -q`
  - Files: `src/interfaces/api/pipeline.py`, `src/interfaces/dashboard/services/loaders.py`, `src/interfaces/dashboard/app.py`, `tests/e2e/ui/test_dashboard_ui_verification_loop.py`
  - Docs: `docs/crawler_status.md`, `docs/manifest/07_observability.md`, `docs/implementation/reports/ui_verification_final_report.md`
  - Alternatives: keep labels in docs only (rejected: runtime trust ambiguity).

## Gated Items

- [x] **G-02: Live browser run against real Streamlit server**
  - Resolution: added live-browser verification test (`tests/live/ui/test_dashboard_live_browser__source_support.py`) that launches real dashboard runtime and validates source labels + assumption badges.
  - Verification evidence: `RUN_LIVE=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/live/ui/test_dashboard_live_browser__source_support.py -q`
