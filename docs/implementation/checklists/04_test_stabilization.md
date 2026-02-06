# Checklist: Test Stabilization

## Phase 0: Identify The Test Interface

- [x] Identify runner + how CI runs it (or confirm CI missing)
  - AC: runner and CI mapping documented in `docs/manifest/10_testing.md` and `docs/manifest/11_ci.md`.
  - Verify: confirmed no CI workflows found (see `docs/manifest/11_ci.md`).
  - Files: `pytest.ini`, `tests/conftest.py`
  - Docs: `docs/manifest/10_testing.md`, `docs/manifest/11_ci.md`

- [x] Identify markers/tags + gating flags/env vars
  - AC: markers + gating documented; command map exists.
  - Verify: `pytest.ini` markers + `tests/conftest.py` opt-in flags (`--run-integration`, `--run-e2e`, `--run-live`) verified.
  - Files: `pytest.ini`, `tests/conftest.py`
  - Docs: `docs/manifest/10_testing.md`

- [x] Identify environment needs (DB/network/browser/etc)
  - AC: env requirements documented per suite type.
  - Verify: N/A (document-only)
  - Files: N/A
  - Docs: `docs/manifest/10_testing.md`

## Phase 1: Establish Baseline Signal

- [x] Run unit suite (baseline)
  - AC: unit suite result recorded; failures categorized if any.
  - Verify: `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest -m "not integration and not e2e and not live"` (1 run; 62 passed).
  - Files: N/A
  - Docs: `docs/implementation/03_worklog.md`, `docs/implementation/00_status.md`

- [x] Run unit data contracts suite (baseline)
  - AC: `tests/unit/data_contracts` passes; any contract failures triaged.
  - Verify: `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/data_contracts -m "not integration and not e2e and not live"` (1 run; 9 passed).
  - Files: N/A
  - Docs: `docs/implementation/03_worklog.md`, `docs/implementation/00_status.md`

- [x] Run integration suite (baseline)
  - AC: integration passes in intended env OR skips are documented and correctly marked.
  - Verify: `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-integration -m integration` (1 run; 19 passed).
  - Files: N/A
  - Docs: `docs/implementation/03_worklog.md`, `docs/implementation/00_status.md`

- [x] Run e2e suite (baseline)
  - AC: e2e passes in intended env OR gating requirements documented.
  - Verify: `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e -m e2e` (1 run; 1 passed).
  - Files: N/A
  - Docs: `docs/implementation/03_worklog.md`, `docs/implementation/00_status.md`

## Phase 3: Debug Loop

- [ ] Fix Bucket A infra issues (if any)
- [ ] Fix Bucket B contract violations (if any)
- [ ] Fix Bucket C behavioral mismatches (if any)
- [ ] Fix Bucket D brittle tests (if any)

## Phase 5: Final Verification

- [x] Unit suite passes 3x (0 flakes)
  - Verify: `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest -m "not integration and not e2e and not live"` (3 runs; all green).
- [x] Unit data contracts pass 3x (0 flakes)
  - Verify: `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/data_contracts -m "not integration and not e2e and not live"` (3 runs; all green).
- [x] Integration suite passes once (or intended skips)
  - Verify: `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-integration -m integration` (1 run; 19 passed).
- [x] E2E suite passes once (or intended gating)
  - Verify: `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e -m e2e` (1 run; 1 passed).
- [x] Write final report
  - Files: `docs/implementation/reports/test_stabilization_final_report.md`
