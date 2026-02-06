# Testing

## Test Runner

- Runner: `pytest`
- Preferred invocation: use the project venv Python:
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest`

Note: in this environment, pytest may auto-load some third-party plugins that are installed in the venv (for example `langsmith`). The test suite is expected to remain stable even when those plugins are present.

## Markers and Gating

Markers are declared in `pytest.ini` and applied via `tests/conftest.py`.

- `integration`: offline integration tests (SQLite/filesystem), no live network.
- `e2e`: end-to-end tests (offline, minimal mocks).
- `live`: real network/browser tests, always opt-in.
- `network`: hits the network.
- `slow`: long-running tests.

Default run behavior:
- `integration`, `e2e`, and `live` are skipped unless explicitly enabled.

Enable opt-in suites:
- Integration: `--run-integration` or `RUN_INTEGRATION=1`
- E2E: `--run-e2e` or `RUN_E2E=1`
- Live: `--run-live` or `RUN_LIVE=1`

## Command Map

- Unit (default deterministic suite):
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest -m "not integration and not e2e and not live"`

- Unit data contracts only:
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/data_contracts -m "not integration and not e2e and not live"`

- Integration suite (offline DB/filesystem):
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-integration -m integration`

- E2E suite (offline critical flows):
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e -m e2e`

- Live suite (network/browser diagnostics, opt-in):
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-live -m live`

- All offline suites (unit + integration + e2e):
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-integration --run-e2e -m "not live"`

## Environment Needs

- Unit: no external services; uses local fixtures and `tmp_path`.
- Integration: local SQLite + filesystem only.
- E2E: local SQLite + fixture HTML + filesystem only.
- Live: real network, and may require Playwright/Pydoll browsers depending on crawler configuration.
