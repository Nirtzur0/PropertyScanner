# Test Stabilization Final Report

## What was failing

Nothing was failing at stabilization time: all unit, integration (offline), and e2e (offline) suites ran green.

## Root causes

N/A (no failing tests encountered during this stabilization pass).

## Fixes applied

- Documentation/audit trail added under `docs/` (status, checklist, worklog).
- `pytest.ini` addopts updated to include `-p no:langsmith.pytest_plugin` as a best-effort attempt to prevent LangSmith pytest plugin side-effects.

## Contract changes (thresholds/fields/ranges)

None. All data contract tests passed as-is.

## How to run

Preferred runner:
- `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest`

Unit (default deterministic suite):
- `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest -m "not integration and not e2e and not live"`

Unit data contracts:
- `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/data_contracts -m "not integration and not e2e and not live"`

Integration (offline):
- `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-integration -m integration`

E2E (offline):
- `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e -m e2e`

Live (network/browser, opt-in):
- `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-live -m live`

## Remaining gated tests (if any)

- `@pytest.mark.live` tests are opt-in and require `--run-live` (and typically real network and a browser/tooling stack depending on crawler configuration).
