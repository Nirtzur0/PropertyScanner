# Alignment Review Checklist

## Gate Summary

- Verdict: `ALIGNED_WITH_RISKS`
- Review stage: `build` (`phase_3`)
- Date: 2026-02-09
- Objective source: `docs/manifest/00_overview.md#Core Objective`
- Routing evidence: `docs/implementation/reports/prompt_execution_plan.md` + `docs/implementation/checklists/02_milestones.md` (`M8` implementation step completed; this gate closes `M8` routing evidence and activates next packet for `C-10`).
- Rerun context: post retriever ablation/decomposition decision packet (`C-08`, `C-09`, `O-02`, `O-03` marked closed in artifact-alignment docs).

## Required Questions (Explicit Answers)

### 1) Are we still building the same thing defined by `Core Objective`?

- Answer: **Yes.**
- Evidence:
  - Core objective, non-goals, and success metrics remain explicit in `docs/manifest/00_overview.md`.
  - Runtime entrypoints still align to the same workflow in `src/interfaces/cli.py`, `src/interfaces/api/pipeline.py`, and `src/interfaces/dashboard/app.py`.
  - `M8` packet scope stayed inside objective-aligned reliability/model-trust work (`docs/implementation/checklists/02_milestones.md`).

### 2) Is the main user journey usable end-to-end right now?

- Answer: **Yes for the core journey, with one remaining modeling-policy gap.**
- Evidence:
  - UI verification artifacts exist: `docs/implementation/checklists/05_ui_verification.md` and `docs/implementation/reports/ui_verification_final_report.md`.
  - Dashboard UI verification loop is green: `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q` (`5 passed`).
  - Retriever decision packet output is generated and reviewable from the CLI path: `docs/implementation/reports/retriever_ablation_report.md`.
  - Runtime source labels and assumption badges remain exposed in API/dashboard (`src/interfaces/api/pipeline.py`, `src/interfaces/dashboard/app.py`).

### 3) Are we measuring the right success metrics from the objective?

- Answer: **Yes, and runtime enforcement improved this cycle.**
- Evidence:
  - Objective SLI/SLO mapping remains in `docs/manifest/07_observability.md`.
  - Runtime source-trust metric is explicitly tracked in observability (`docs/manifest/07_observability.md`).
  - Retrieval accuracy/coverage tradeoff is now measured with explicit thresholds in `docs/implementation/reports/retriever_ablation_report.json`.

### 4) Are we spending meaningful effort on explicit non-goals?

- Answer: **No meaningful non-goal drift detected.**
- Evidence:
  - Non-goals in `docs/manifest/00_overview.md` remain unchanged (no hosted SaaS, no automated trade execution).
  - Current packet stayed within reliability/trust boundaries and docs governance updates (`docs/implementation/00_status.md`).

## Evidence-Backed Misalignment Checklist

- [x] Distribution-free interval fallback policy is now explicit in runtime/runbook surfaces (`C-10`).
  - Evidence: `lit-jackknifeplus-2021` row is mapped to supported runtime policy in `docs/implementation/reports/artifact_feature_alignment.md`.
- [ ] Retriever ablation rerun cadence and escalation trigger are not explicitly codified as an operational policy.
  - Evidence: `CMD-RETRIEVER-ABLATION` exists in `docs/manifest/09_runbook.md`, but no periodic cadence/escalation gate is documented in `docs/manifest/07_observability.md`.
- [ ] Decomposition diagnostics re-evaluation trigger (sample-floor recovery path) is not explicitly mapped in runbook/observability docs.
  - Evidence: current decision is `insufficient_segment_samples` in `docs/implementation/reports/retriever_ablation_report.json`, but no explicit re-evaluation trigger is documented in `docs/manifest/09_runbook.md`.

## Top 3 Next Corrections

- [x] C-10: Define fallback interval strategy for weak-regime segments (`lit-jackknifeplus-2021` gap).
  - Owner-type: maintainer
  - Effort: S
  - Target files: `src/valuation/services/conformal_calibrator.py`, `docs/manifest/09_runbook.md`, `docs/manifest/20_literature_review.md`
  - Acceptance signal: fallback interval policy is explicit with trigger thresholds and operational runbook mapping.

- [ ] C-11: Codify retriever ablation rerun cadence and escalation gate.
  - Owner-type: maintainer
  - Effort: S
  - Target files: `docs/manifest/07_observability.md`, `docs/manifest/09_runbook.md`, `docs/implementation/checklists/02_milestones.md`
  - Acceptance signal: rerun cadence and explicit escalation criteria (`simplify`/`warn` conditions) are documented and linked to packet routing.

- [ ] C-12: Codify decomposition diagnostics re-evaluation trigger after sample-floor recovery.
  - Owner-type: maintainer
  - Effort: S
  - Target files: `docs/manifest/09_runbook.md`, `docs/manifest/07_observability.md`, `docs/implementation/reports/retriever_ablation_report.md`
  - Acceptance signal: runbook includes explicit trigger to rerun decomposition diagnostics when `land_n`/`structure_n` sample floors are met.

## Next Execution Packet Mapping (`docs/implementation/checklists/02_milestones.md`)

Reference target: `docs/implementation/checklists/02_milestones.md` (`M9` remains active until the prompt-03 follow-up closes routing evidence).

- Keep `C-10` closed and rerun `prompt-03` to finalize `M9` routing evidence.
- Keep `C-11` and `C-12` explicitly in `Not now` unless `M9` packet appetite allows inclusion.

## Keep-the-Slate-Clean Decision

- Decision: `Reshape Next Bet`
- Leftovers:
  - close `M8` as complete,
  - activate `M9` as the single active packet,
  - carry `C-11`/`C-12` as bounded follow-ons if `M9` scope remains small.

## Residual Risks

- Remaining policy gaps are now operational cadence issues (`C-11`, `C-12`), not interval fallback ambiguity.
- Ablation outputs can drift over time without a defined rerun cadence.
- Decomposition diagnostics can remain stale if sample-floor recovery is not operationalized.
