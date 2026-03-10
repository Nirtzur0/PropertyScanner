# Plan Checklist

- [ ] AC-01: Core objective, non-goals, constraints, and invariants are documented in `docs/manifest/00_overview.md`.
  - Verify: `rg -n "## Core Objective|Non-goals|Constraints|Do-not-break invariants|Primary user journeys" docs/manifest/00_overview.md`
  - Files: `docs/manifest/00_overview.md`
  - Docs: `docs/INDEX.md`, `docs/implementation/reports/prd.md`

- [ ] AC-02: Critical user journeys are represented by runnable commands for dashboard and pipeline operations.
  - Verify: `python3 -m src.interfaces.cli -h`
  - Files: `src/interfaces/cli.py`, `src/interfaces/api/pipeline.py`, `run_dashboard.sh`
  - Docs: `README.md`, `docs/explanation/data_pipeline.md`, `docs/manifest/00_overview.md`

- [ ] AC-03: Preflight remains the canonical freshness orchestrator for local operation.
  - Verify: `python3 -m src.interfaces.cli preflight --help`
  - Files: `src/interfaces/cli.py`, `src/interfaces/api/pipeline.py`, `src/platform/`
  - Docs: `README.md`, `docs/explanation/data_pipeline.md`

- [ ] AC-04: Artifact lifecycle is explicit and consistent with current defaults (DB/index/model outputs).
  - Verify: `python3 -m src.interfaces.cli preflight --help` and confirm documented artifact paths exist after run.
  - Files: `config/paths.yaml`, `src/platform/`, `data/`, `models/`
  - Docs: `README.md`, `docs/explanation/data_pipeline.md`, `docs/manifest/00_overview.md`

- [ ] AC-05: Offline default test workflow is deterministic and command-mapped.
  - Verify: `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest -m "not integration and not e2e and not live"`
  - Files: `pytest.ini`, `tests/conftest.py`, `tests/`
  - Docs: `docs/manifest/10_testing.md`, `docs/implementation/00_status.md`

- [ ] AC-06: Integration and E2E suites are explicitly opt-in and documented.
  - Verify: `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-integration -m integration` and `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e -m e2e`
  - Files: `tests/conftest.py`, `tests/integration/`, `tests/e2e/`
  - Docs: `docs/manifest/10_testing.md`, `docs/implementation/00_status.md`

- [ ] AC-07: PRD requirements map to acceptance criteria with pass/fail semantics.
  - Verify: `rg -n "## Acceptance criteria mapping|AC-0" docs/implementation/reports/prd.md docs/implementation/checklists/01_plan.md`
  - Files: `docs/implementation/reports/prd.md`, `docs/implementation/checklists/01_plan.md`
  - Docs: `docs/implementation/reports/prd.md`, `docs/manifest/00_overview.md`

- [ ] AC-08: Open assumptions and unresolved gaps are explicit for next packet planning.
  - Verify: `rg -n "Open questions / TODOs|Risks and assumptions" docs/implementation/reports/prd.md`
  - Files: `docs/implementation/reports/prd.md`
  - Docs: `docs/implementation/reports/prd.md`, `docs/implementation/reports/prompt_execution_plan.md`

- [x] AC-09: Model routing defaults to ChatMock/OpenAI-compatible backends for shared text, description analysis, and vision requests, with explicit Ollama compatibility mode and explicit unsupported-vision failures.
  - Verify: `python3 -m src.interfaces.cli preflight --help` and `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/platform/test_llm__chatmock_routing.py tests/unit/listings/services/test_description_analyst__chatmock.py tests/unit/listings/services/test_vlm__chatmock.py --run-integration tests/integration/listings/test_feature_fusion__chatmock_paths.py -q`
  - Files: `src/platform/utils/llm.py`, `src/listings/services/description_analyst.py`, `src/listings/services/vlm.py`, `src/platform/settings.py`
  - Docs: `README.md`, `docs/reference/configuration.md`, `docs/how_to/configuration.md`, `docs/manifest/02_tech_stack.md`, `docs/manifest/03_decisions.md`, `docs/manifest/07_observability.md`, `docs/manifest/10_testing.md`
