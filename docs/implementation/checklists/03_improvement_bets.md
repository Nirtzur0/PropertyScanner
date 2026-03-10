# Improvement Bets Checklist

## Packet Summary

- Prompt: `prompt-14-improvement-direction-bet-loop`
- Date: 2026-02-08
- Source report: `docs/implementation/reports/improvement_directions.md`
- Appetite: `medium`

## Selected Improvement Bets

- [x] IB-01: Confidence persistence is calibration-derived and testable.
  - Owner type: `maintainer`
  - Effort: `M`
  - Target files/areas: `src/valuation/services/valuation_persister.py`, `tests/unit/valuation/test_valuation_persister__confidence_semantics.py`, `docs/how_to/interpret_outputs.md`
  - Acceptance signal: no placeholder confidence assignment; persisted fields map to calibration diagnostics.
  - Suggested prompt chain: `prompt-02 -> prompt-09 -> prompt-03`

- [x] IB-02: Segmented conformal coverage reporting is operational and thresholded.
  - Owner type: `maintainer`
  - Effort: `M`
  - Target files/areas: `src/valuation/services/conformal_calibrator.py`, valuation reporting outputs, `docs/manifest/07_observability.md`, `docs/manifest/09_runbook.md`
  - Acceptance signal: per-run coverage outputs exist for `region_id`, listing type, and price band with explicit pass/fail thresholds.
  - Suggested prompt chain: `prompt-02 -> prompt-10 -> prompt-03`

- [x] IB-03: Fusion-vs-RF/XGBoost benchmark gate is added.
  - Owner type: `maintainer`
  - Effort: `M`
  - Target files/areas: model eval/benchmark harness, `docs/manifest/10_testing.md`, `docs/implementation/checklists/02_milestones.md`
  - Acceptance signal: benchmark report compares fusion against RF/XGBoost under time+geo splits with explicit acceptance bounds.
  - Suggested prompt chain: `prompt-02 -> prompt-09 -> prompt-03`

- [x] IB-04: Top-level preflight help and lockfile policy converge to one operator-friendly workflow.
  - Owner type: `maintainer`
  - Effort: `S`
  - Target files/areas: `src/interfaces/cli.py`, `README.md`, `docs/manifest/02_tech_stack.md`, `docs/manifest/09_runbook.md`
  - Acceptance signal: preflight help exposes actionable options and docs define one canonical lockfile-backed install path.
  - Suggested prompt chain: `prompt-02 -> prompt-11 -> prompt-03`

- [x] IB-05: Artifact-feature mapping contract is enforced by docs/CI checks.
  - Owner type: `contributor`
  - Effort: `S`
  - Target files/areas: docs-check script(s), CI docs guardrail, `docs/implementation/reports/artifact_feature_alignment.md`
  - Acceptance signal: docs/CI check fails when load-bearing artifact IDs are no longer mapped to feature/test outcomes.
  - Suggested prompt chain: `prompt-15 -> prompt-02 -> prompt-11`

- [x] IB-06: Source support/fallback status is visible in runtime user surfaces.
  - Owner type: `maintainer`
  - Effort: `M`
  - Target files/areas: pipeline status payloads, dashboard status rendering, `config/sources.yaml`, `docs/crawler_status.md`
  - Acceptance signal: outputs explicitly annotate supported/blocked/fallback source states.
  - Suggested prompt chain: `prompt-02 -> prompt-06 -> prompt-03` (completed on 2026-02-09 via prompt-02 + prompt-06 rerun)

## Not Now

- [x] N-01: Spatial residual diagnostics (`LISA`/Moran-style) packet executed after segmented coverage stabilization.
  - Owner type: `maintainer`
  - Effort: `M`
  - Target files/areas: valuation diagnostics surfaces and observability docs
  - Acceptance signal: diagnostics emitted and wired to triage playbook.
  - Suggested prompt chain: `prompt-04 -> prompt-02 -> prompt-03`
