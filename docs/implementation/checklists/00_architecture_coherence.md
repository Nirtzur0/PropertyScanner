# Architecture Coherence Checklist

## Scope & Readiness

- [x] Scope: establish canonical architecture baseline in `docs/manifest/01_architecture.md`.
- [x] Appetite: `medium`.
- [x] Active packet: `prompt-04-architecture-coherence-loop`.
- [x] State: `downhill` (evidence map completed and documentation surfaces are now explicit).
- [x] Readiness verdict: `GO_WITH_RISKS`.
- [x] Rationale captured in `docs/implementation/reports/architecture_coherence_report.md`.

## C4 Coverage (L1/L2/L3 where used)

- [x] C4-1 System Context exists and maps actors/external systems to boundaries.
- [x] C4-2 Containers exist and map responsibilities to real code paths.
- [x] C4-3 Components included for high-risk containers (valuation/retrieval and unified crawl).
- [x] Cross-file consistency check complete across `01_architecture.md`, `04_api_contracts.md`, and `05_data_model.md`.

## Runtime + Deployment Coverage

- [x] Runtime scenario: preflight refresh (happy path) documented with evidence paths.
- [x] Runtime scenario: dashboard/API valuation read path documented.
- [x] Runtime scenario: failure path (insufficient comps / retriever issues) documented.
- [x] Deployment view includes local-first mode and optional Docker mode.
- [x] Trust boundaries are declared for local, external content, and external providers.

## Docs Architecture vs Code Reality (Drift Diff)

- [x] Drift: missing `docs/manifest/01_architecture.md` resolved in this packet.
- [x] Drift: missing `docs/manifest/04_api_contracts.md` resolved in this packet.
- [x] Drift: missing `docs/manifest/05_data_model.md` resolved in this packet.
- [x] Drift: docs index lacked architecture/coherence links; updated in `docs/INDEX.md`.
- [x] Drift: release discipline docs packet executed (`CHANGELOG.md`, versioning policy, release checklist now present).
- [x] Drift: CI workflow guardrail added in `.github/workflows/ci.yml` (resolved in prompt-02 Packet M2).
- [x] Drift: command map moved to `docs/manifest/09_runbook.md` and `.prompt_system.yml` pointer updated (resolved in prompt-02).

## Invariants + Verification Commands

- [x] AC: CLI command surface still exposes canonical workflow commands.
  - Verify: `python3 -m src.interfaces.cli -h`
  - Files: `src/interfaces/cli.py`
  - Docs: `docs/manifest/01_architecture.md`, `docs/manifest/04_api_contracts.md`

- [x] AC: Prefect orchestration surface still exposes preflight/market/index/training/backfill flow entrypoints.
  - Verify: `python3 -m src.platform.workflows.prefect_orchestration -h`
  - Files: `src/platform/workflows/prefect_orchestration.py`
  - Docs: `docs/manifest/01_architecture.md`, `docs/manifest/04_api_contracts.md`

- [x] AC: Marker taxonomy and default test gating remain explicit and documented.
  - Verify: `python3 -m pytest --markers`
  - Files: `pytest.ini`, `tests/conftest.py`
  - Docs: `docs/manifest/10_testing.md`, `docs/manifest/01_architecture.md`

- [x] AC: Prompt router now recognizes architecture artifacts as present.
  - Verify: `python3 prompts/scripts/prompt_router.py --root prompts select --target-root . --phase auto --format json`
  - Files: `prompts/scripts/prompt_router.py`, `docs/manifest/01_architecture.md`
  - Docs: `docs/implementation/reports/prompt_execution_plan.md`, `docs/implementation/reports/architecture_coherence_report.md`

## Now / Not now

### Now

- [x] Create architecture baseline (`01_architecture.md`) with C4 + runtime + deployment sections.
- [x] Create boundary contract map (`04_api_contracts.md`).
- [x] Create data model map (`05_data_model.md`).
- [x] Produce coherence checklist + report and update status/worklog.

### Not now

- [x] Create full release discipline docs packet (`prompt-11`).
- [x] Add CI workflow plus docs/update guardrails.
- [x] Create dedicated command map page (`docs/manifest/09_runbook.md`) and re-point `.prompt_system.yml`.

## Blockers / TODOs

- [x] No blocker for architecture docs completion.
- [x] TODO: run `prompt-03-alignment-review-gate` next to confirm objective alignment at bet stage.
- [x] TODO: run `prompt-07-repo-audit-checklist` to convert remaining gaps into milestone outcomes.
