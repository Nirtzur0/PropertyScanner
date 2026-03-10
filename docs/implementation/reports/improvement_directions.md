# Improvement Directions Report

## Current-State Snapshot

- Objective alignment remains intact with explicit trust/reliability gaps (`docs/manifest/00_overview.md`, `docs/implementation/reports/alignment_review.md`).
- External artifact evidence is present and now mapped to features, but several high-impact gaps remain (`docs/artifacts/index.json`, `docs/implementation/reports/artifact_feature_alignment.md`).
- Reliability and CI baselines exist, while key operator/runtime trust surfaces are still incomplete (`docs/manifest/11_ci.md`, `.github/workflows/ci.yml`, `docs/implementation/checklists/02_milestones.md`).
- Research-backed valuation architecture is implemented and tested at core math/contract level, but production-facing confidence/coverage signaling is incomplete (`tests/unit/paper/test_paper_verification.py`, `paper/verification_log.md`, `src/valuation/services/valuation_persister.py`).

## Opportunity Inventory

| ID | Direction | Type | Evidence | Gap | Impact | Confidence | Effort | Deferral Risk | Suggested Prompt Chain |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D-01 | Replace placeholder confidence persistence with calibration-derived semantics | Reliability/Trust | `src/valuation/services/valuation_persister.py`, `docs/implementation/checklists/08_artifact_feature_alignment.md` | Persisted confidence still uses placeholder logic | H | H | M | H | `prompt-02 -> prompt-09 -> prompt-03` |
| D-02 | Add segmented conformal coverage reporting and runbook thresholds | Validation/Observability | `src/valuation/services/conformal_calibrator.py`, `docs/manifest/20_literature_review.md` | Coverage caveats documented but not operationalized per segment | H | M | M | H | `prompt-02 -> prompt-10 -> prompt-03` |
| D-03 | Implement spatial residual diagnostics and triage wiring | Observability/Quality | `docs/manifest/20_literature_review.md`, `docs/manifest/07_observability.md` | Spatial diagnostics are planned but not emitted as runtime checks | M | M | M | M | `prompt-04 -> prompt-02 -> prompt-03` |
| D-04 | Add fusion-vs-RF/XGBoost benchmark gate under time+geo splits | Modeling/Quality Gate | `docs/manifest/20_literature_review.md`, `src/ml/services/modeling.py` | Baseline expectation exists but no enforced benchmark gate | H | M | M | H | `prompt-02 -> prompt-09 -> prompt-03` |
| D-05 | Make top-level preflight help actionable and close lockfile-policy drift | UX/DevEx | `src/interfaces/cli.py`, `docs/manifest/02_tech_stack.md`, `docs/implementation/checklists/02_milestones.md` | Operator UX and install path consistency are still open | M | H | S | M | `prompt-02 -> prompt-11 -> prompt-03` |
| D-06 | Add artifact-feature mapping contract check into docs/CI gates | Process/Integration | `docs/implementation/reports/artifact_feature_alignment.md`, `.github/workflows/ci.yml` | Alignment gate is present but not yet automatically enforced | M | H | S | M | `prompt-15 -> prompt-02 -> prompt-11` |
| D-07 | Surface source support/fallback status in user-facing outputs | UX/Trust | `docs/crawler_status.md`, `src/listings/agents/processors/*.py`, `docs/implementation/checklists/07_alignment_review.md` | Runtime output does not clearly expose supported/blocked/fallback source states | H | H | M | H | `prompt-02 -> prompt-06 -> prompt-03` |

## Selected Directions (Top 6)

### D-01 Confidence semantics (selected)

- Outcome statement: persisted confidence is derived from calibration/model evidence, not placeholders.
- Why now: this is a load-bearing trust gap across valuation outputs and downstream decision quality.
- Implementation surface: `src/valuation/services/valuation_persister.py`, `src/valuation/services/calibration.py`, `docs/how_to/interpret_outputs.md`.
- Integration dependencies: coverage diagnostics (`D-02`), docs interpretation alignment, milestone gating.
- Testing strategy: unit tests for confidence derivation, integration test for persisted fields, contract check on response schema.
- Observability/release/docs updates: update confidence semantics in interpretability docs and runbook check commands.
- Done signal: no static placeholder confidence assignment remains; persisted confidence fields are traceable to diagnostics and covered by tests.

### D-02 Segmented coverage reporting (selected)

- Outcome statement: interval coverage is reported and thresholded by `region_id`, listing type, and price band.
- Why now: literature-backed caveats are known but currently not enforced operationally.
- Implementation surface: `src/valuation/services/conformal_calibrator.py`, valuation workflow/reporting output, runbook/observability docs.
- Integration dependencies: D-01 confidence semantics, D-03 diagnostics channel, milestone gating.
- Testing strategy: unit tests for segment aggregations, integration tests for report outputs, docs check for runbook command references.
- Observability/release/docs updates: add coverage SLI entries and triage thresholds.
- Done signal: per-run segmented coverage artifact exists and fails gates when thresholds are violated.

### D-04 Baseline benchmark gate (selected)

- Outcome statement: fusion model claims are guarded by RF/XGBoost benchmark comparison under leak-safe splits.
- Why now: architectural complexity requires benchmark discipline to prevent unjustified model drift.
- Implementation surface: model evaluation harness, benchmark report artifact, testing docs/milestones.
- Integration dependencies: D-02 coverage metrics, CI/docs gating.
- Testing strategy: integration benchmark run + deterministic report generation checks.
- Observability/release/docs updates: add benchmark pass/fail acceptance criteria in testing/release docs.
- Done signal: benchmark report is generated and milestone acceptance includes explicit regression thresholds.

### D-05 CLI+lockfile UX convergence (selected)

- Outcome statement: top-level preflight help is actionable and dependency install policy is lockfile-backed and unambiguous.
- Why now: operator friction and environment drift are recurring execution blockers.
- Implementation surface: `src/interfaces/cli.py`, install-policy docs, dependency manifests.
- Integration dependencies: runbook command map and CI install flow.
- Testing strategy: CLI help snapshot check + docs sync checks.
- Observability/release/docs updates: update runbook, tech stack doc, README install guidance.
- Done signal: `python3 -m src.interfaces.cli preflight --help` surfaces actionable options and docs declare a single canonical install policy.

### D-06 Artifact-feature contract automation (selected)

- Outcome statement: artifact-feature alignment mapping is enforced by an automated docs/CI contract check.
- Why now: prompt-15 produced alignment outputs that need continuous guardrails.
- Implementation surface: docs check script(s), CI docs guardrail step, alignment docs references.
- Integration dependencies: existing docs-sync/command-map checks.
- Testing strategy: contract/docs check job fails when mappings are missing.
- Observability/release/docs updates: CI docs check section and troubleshooting notes.
- Done signal: CI/docs check validates load-bearing artifact IDs map to active feature/test outcomes.

### D-07 Source support runtime visibility (selected)

- Outcome statement: run outputs explicitly annotate source support, fallback, and blocked states.
- Why now: source reliability constraints are known yet not consistently visible to operators/users.
- Implementation surface: pipeline status payloads, dashboard status surfaces, source config/docs.
- Integration dependencies: CLI/API/dashboard consistency and docs updates.
- Testing strategy: integration checks on status payload fields and UI/e2e checks for visibility.
- Observability/release/docs updates: add source-state metrics and runbook triage guidance.
- Done signal: runtime/user-facing outputs expose source support status with links to crawler-status guidance.

## Packeting Plan

- Appetite: `medium`

### Now (Packet 1)

1. D-01 confidence semantics
2. D-02 segmented coverage reporting
3. D-05 CLI+lockfile convergence

### Next (Packet 2)

1. D-04 baseline benchmark gate
2. D-06 artifact-feature contract automation
3. D-07 source support runtime visibility

### Not now

1. D-03 spatial residual diagnostics (keep scoped until D-02 reporting baseline is stable)

## Routing Notes

- Final packet routing should be refreshed with `prompt-00` after Packet 1 closure.
- Use `prompt-03` at packet boundary to re-check objective drift before executing Packet 2.
