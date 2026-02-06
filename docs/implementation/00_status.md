# Test Stabilization Status

## Current

- Status: Complete (all offline suites green; live suite remains opt-in)
- Goal: clean, stable, meaningful green across unit/integration/e2e + data contracts.

## Latest Results (Baseline)

- Unit (excluding integration/e2e/live): pass (62 passed; 2026-02-06)
- Unit data contracts: pass (9 passed; 2026-02-06)
- Integration (`--run-integration -m integration`): pass (19 passed; 2026-02-06)
- E2E (`--run-e2e -m e2e`): pass (1 passed; 2026-02-06)

## Latest Results (Flake-Proof Verification)

- Unit: pass (3 consecutive runs; 62 passed each; 2026-02-06)
- Unit data contracts: pass (3 consecutive runs; 9 passed each; 2026-02-06)
- Integration: pass (1 run; 19 passed; 2026-02-06)
- E2E: pass (1 run; 1 passed; 2026-02-06)

## Commands

- Unit:
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest -m "not integration and not e2e and not live"`
- Unit data contracts:
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/data_contracts -m "not integration and not e2e and not live"`
- Integration:
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-integration -m integration`
- E2E:
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e -m e2e`
- All offline:
  - `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-integration --run-e2e -m "not live"`

## Next

- Optional: decide whether to keep `@pytest.mark.live` tests in CI (currently opt-in only).
