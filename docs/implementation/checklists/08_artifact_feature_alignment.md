# Artifact-Feature Alignment Checklist

## Gate Summary

- Verdict: `ALIGNED_WITH_GAPS`
- Date: 2026-02-09
- Prompt: `prompt-15-artifact-feature-alignment-gate`
- Artifact source: `docs/artifacts/index.json` (`14` entries)
- Report: `docs/implementation/reports/artifact_feature_alignment.md`

## Corrective Outcomes

- [x] C-01: Confidence persistence becomes calibration-derived (not placeholder).
  - Owner type: `maintainer`
  - Effort: `M`
  - Target files/areas: `src/valuation/services/valuation_persister.py`, `src/valuation/services/calibration.py`, `docs/how_to/interpret_outputs.md`
  - Acceptance signal: static placeholder confidence assignment is removed; persisted confidence references calibration/model diagnostics.
  - Verification method: `unit`, `integration`, `contract`, `docs check`

- [x] C-02: Segmented conformal coverage reporting is implemented and gated.
  - Owner type: `maintainer`
  - Effort: `M`
  - Target files/areas: `src/valuation/services/conformal_calibrator.py`, valuation workflows/reporting layer, `docs/manifest/09_runbook.md`, `docs/manifest/07_observability.md`
  - Acceptance signal: per-run coverage report exists for `region_id`, listing type, and price band with threshold checks.
  - Verification method: `unit`, `integration`, `e2e`, `docs check`

- [x] C-03: Spatial residual diagnostics are operationalized.
  - Owner type: `maintainer`
  - Effort: `M`
  - Target files/areas: valuation diagnostics/reporting layer, `docs/manifest/07_observability.md`, `docs/manifest/09_runbook.md`
  - Acceptance signal: spatial drift/outlier diagnostics are emitted and triage instructions are documented.
  - Verification method: `integration`, `contract`, `docs check`

- [x] C-04: RF/XGBoost baseline benchmark gate is added.
  - Owner type: `maintainer`
  - Effort: `M`
  - Target files/areas: model training/eval harness, benchmark report path, `docs/manifest/10_testing.md`, `docs/implementation/checklists/02_milestones.md`
  - Acceptance signal: benchmark artifacts compare fusion vs RF/XGBoost under time+geo splits; regression threshold gate is explicit.
  - Verification method: `unit`, `integration`, `docs check`

- [x] C-05: Milestones are updated to reflect artifact-backed outcomes and current routing reality.
  - Owner type: `maintainer`
  - Effort: `S`
  - Target files/areas: `docs/implementation/checklists/02_milestones.md`
  - Acceptance signal: stale deferred language is removed and measurable artifact-backed outcomes are added.
  - Verification method: `docs check`

- [x] C-06: Surface artifact-backed assumption badges in API/dashboard outputs.
  - Owner type: `maintainer`
  - Effort: `M`
  - Target files/areas: `src/interfaces/api/pipeline.py`, `src/interfaces/dashboard/app.py`, `docs/how_to/interpret_outputs.md`
  - Acceptance signal: runtime responses and dashboard status surfaces expose assumption/calibration badges linked to docs caveats.
  - Verification method: `integration`, `e2e`, `docs check`

- [x] C-07: Close live-browser verification for source-support labels (`G-02`).
  - Owner type: `maintainer`
  - Effort: `S`
  - Target files/areas: `docs/implementation/checklists/05_ui_verification.md`, `docs/implementation/reports/ui_verification_final_report.md`, `docs/implementation/03_worklog.md`
  - Acceptance signal: live dashboard session confirms `supported|blocked|fallback` labels and no runtime errors in source-status panels.
  - Verification method: `e2e`, `docs check`

## Opportunity Outcomes

- [x] O-01: Add artifact-feature mapping contract check.
  - Owner type: `contributor`
  - Effort: `S`
  - Target files/areas: docs check script + CI docs-check step, `docs/implementation/reports/artifact_feature_alignment.md`
  - Acceptance signal: docs-check fails when load-bearing artifact IDs are not mapped to feature/test outcomes.
  - Verification method: `contract`, `docs check`

- [x] O-02: Add retriever ablation and embedding-drift decision packet.
  - Owner type: `maintainer`
  - Effort: `M`
  - Target files/areas: retrieval evaluation harness/reporting, `docs/manifest/20_literature_review.md`, milestone packet docs
  - Acceptance signal: ablation report exists with keep/simplify decision threshold for semantic retrieval.
  - Verification method: `integration`, `e2e`, `docs check`

- [x] O-03: Add land/structure decomposition diagnostics bet.
  - Owner type: `maintainer`
  - Effort: `M`
  - Target files/areas: market/valuation diagnostics docs and implementation packet notes
  - Acceptance signal: decomposition-risk assumptions and mitigation diagnostics are formalized in implementation plan.
  - Verification method: `contract`, `docs check`

- [x] O-04: Surface artifact-backed assumption badges in API/dashboard outputs.
  - Owner type: `contributor`
  - Effort: `M`
  - Target files/areas: `src/interfaces/api/pipeline.py`, `src/interfaces/dashboard/*`, `docs/how_to/interpret_outputs.md`
  - Acceptance signal: UI/API responses expose assumption and calibration-status badges linked to docs.
  - Verification method: `integration`, `e2e`, `docs check`

- [x] O-05: Add live-browser trust-evidence closure packet.
  - Owner type: `maintainer`
  - Effort: `S`
  - Target files/areas: `docs/implementation/checklists/05_ui_verification.md`, `docs/implementation/reports/ui_verification_final_report.md`
  - Acceptance signal: report/checklist include real runtime verification evidence (not fixture-only) for source label rendering.
  - Verification method: `e2e`, `docs check`
