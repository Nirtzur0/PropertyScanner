# UI Verification Final Report

## 1) UI entrypoints and run commands

- UI entrypoint:
  - `src/interfaces/dashboard/app.py` (single-page Streamlit dashboard)
- UI launch command:
  - `python3 -m src.interfaces.cli dashboard` (source: `src/interfaces/cli.py`)
- Canonical command map:
  - `docs/manifest/09_runbook.md`
- Packet verification commands:
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q`
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e -m e2e -q`

## 2) Capability inventory summary

- Validated in this packet:
  - lens filters and HUD controls,
  - assisted Scout approval flow,
  - Deal Flow -> Memo transitions,
  - insights/pipeline/map render paths,
  - runtime source support/fallback labels in pipeline status surfaces,
  - live-browser verification against a real Streamlit server.
- Remaining/gated:
  - none.

Detailed inventory and evidence mapping: `docs/implementation/checklists/05_ui_verification.md`.

## 3) Critical flow validation

- CF-01 Dashboard render smoke:
  - Evidence: `tests/e2e/ui/test_dashboard_ui_verification_loop.py::test_dashboard_ui_smoke__renders_core_controls`
- CF-02 Country filter narrowing:
  - Evidence: `tests/e2e/ui/test_dashboard_ui_verification_loop.py::test_dashboard_ui_country_filter__narrows_city_and_cards`
- CF-03 Assisted scout approval then run:
  - Evidence: `tests/e2e/ui/test_dashboard_ui_verification_loop.py::test_dashboard_ui_assisted_command__approval_then_run`
- CF-04 Memo navigation:
  - Evidence: `tests/e2e/ui/test_dashboard_ui_verification_loop.py::test_dashboard_ui_memo_button__switches_panel_without_session_error`
- CF-05 Pipeline source-support labels and assumption badges:
  - Evidence: `tests/e2e/ui/test_dashboard_ui_verification_loop.py::test_dashboard_ui_pipeline_status__shows_source_support_labels`

## 4) Tests added/changed

- Added:
  - `tests/e2e/ui/test_dashboard_ui_verification_loop.py`
    - fixture-backed Streamlit AppTest harness
    - five deterministic E2E checks for core UI flows (including source-support and assumption-badge rendering)
  - `tests/live/ui/test_dashboard_live_browser__source_support.py`
    - live-browser Playwright verification against a real Streamlit server runtime
    - validates source-support and assumption-badge trust captions in UI status surfaces
  - `tests/unit/interfaces/test_dashboard_loaders__stale_cached_valuations.py`
    - validates the dashboard loader can render a listing from an older persisted valuation instead of dropping to the empty state
- Changed:
  - `src/interfaces/api/pipeline.py`
    - added runtime source-support classification and `pipeline_status()` payload surface
  - `src/interfaces/dashboard/services/loaders.py`
    - switched pipeline status loading to `PipelineAPI.pipeline_status()`
    - now uses the latest persisted valuation for dashboard rendering, even when freshness is stale
  - `src/interfaces/dashboard/app.py`
    - fixed panel-state synchronization for memo navigation
    - rendered source-support `supported|blocked|fallback` labels and source examples in status views
  - `src/valuation/services/valuation_persister.py`
    - accepts `max_age_days=None` to fetch the latest persisted valuation without freshness filtering

Stability notes:
- UI E2E file: `5 passed`.
- Live UI browser check: `1 passed`.
- Full E2E marker suite (offline): `6 passed, 134 deselected`.
- Fixture harness remains deterministic; live check is isolated under `@pytest.mark.live`.

## 5) Bugs found/fixed

- Bug: clicking `Memo` in Deal Flow could raise `StreamlitAPIException`.
  - Symptom: memo action failed with session-state mutation error.
  - Root cause: shared key collision between radio widget key and mutable `left_panel_view` state.
  - Fix:
    - use dedicated widget key `left_panel_view_selector`,
    - sync selector state from canonical `left_panel_view` before rendering radio.
  - Paths: `src/interfaces/dashboard/app.py`.
  - Regression coverage: `tests/e2e/ui/test_dashboard_ui_verification_loop.py::test_dashboard_ui_memo_button__switches_panel_without_session_error`.

- Gap: runtime source trust labels were missing from user-facing status surfaces.
  - Symptom: users could not see which crawl sources were supported, blocked, or fallback at runtime.
  - Root cause: pipeline status payload only exposed freshness metadata, and dashboard status view had no source-label surface.
  - Fix:
    - added `PipelineAPI.source_support_summary()` + `PipelineAPI.pipeline_status()`,
    - mapped source labels from `config/sources.yaml` + `docs/crawler_status.md`,
    - rendered labels/examples in dashboard `🧭 Pipeline Status`.
  - Paths: `src/interfaces/api/pipeline.py`, `src/interfaces/dashboard/services/loaders.py`, `src/interfaces/dashboard/app.py`.
  - Regression coverage: `tests/unit/interfaces/test_pipeline_api__source_support.py`, `tests/e2e/ui/test_dashboard_ui_verification_loop.py::test_dashboard_ui_pipeline_status__shows_source_support_labels`.

- Gap: artifact-backed assumption caveats were not visible in runtime API/dashboard status payloads.
  - Symptom: operators could not see load-bearing literature caveats and open gaps while reviewing pipeline health.
  - Root cause: `pipeline_status` exposed freshness + source support only; no assumption badge payload existed.
  - Fix:
    - added `PipelineAPI.assumption_badges(...)` and embedded badges in `PipelineAPI.pipeline_status(...)`,
    - rendered assumption badge lines in dashboard system-status and pipeline-status views,
    - linked badges to artifact IDs and guide docs.
  - Paths: `src/interfaces/api/pipeline.py`, `src/interfaces/dashboard/app.py`.
  - Regression coverage: `tests/unit/interfaces/test_pipeline_api__source_support.py::test_pipeline_status__embeds_source_support_summary`, `tests/e2e/ui/test_dashboard_ui_verification_loop.py::test_dashboard_ui_pipeline_status__shows_source_support_labels`.

- Bug: live dashboard rendered `No listings yet` even though the repo DB already contained listings and persisted valuations.
  - Symptom: Playwright MCP showed `Listings tracked: 7851` in pipeline status while the main page stopped at the empty state.
  - Root cause: `fetch_listings_dataframe(...)` only accepted cached valuations newer than 7 days; the repo’s persisted valuations were all older, so the dashboard skipped every row once live valuation fallback failed.
  - Fix:
    - allow `ValuationPersister.get_latest_valuation(..., max_age_days=None)` to bypass age filtering,
    - use that path from the dashboard loader so existing persisted valuations still populate deal cards while freshness is shown separately in pipeline status.
  - Paths: `src/interfaces/dashboard/services/loaders.py`, `src/valuation/services/valuation_persister.py`.
  - Regression coverage: `tests/unit/interfaces/test_dashboard_loaders__stale_cached_valuations.py`, live manual Playwright rerun on `2026-03-10`.

## 6) How to run everything

- UI launch:
  - `python3 -m src.interfaces.cli dashboard`
- UI verification loop tests:
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q`
- Full offline E2E:
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e -m e2e -q`
- Full offline test gate:
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-integration --run-e2e -m "not live"`

## 7) Gating

- No open gating items remain for the current trust-surface UI scope.
- `G-02` closure evidence:
  - `RUN_LIVE=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/live/ui/test_dashboard_live_browser__source_support.py -q`
