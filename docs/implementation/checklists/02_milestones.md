# Milestones Checklist

## Checkpoint Notes

- [x] 2026-03-11 Dashboard V3 prune packet: the React analyst surface now ships with three primary destinations, a command-center redirect, slimmer Decisions tabs, a trust-summary pipeline contract, and UI instrumentation.
  - AC: `Workbench`, `Decisions`, and `Pipeline` are the only primary destinations; `/command-center` redirects to `/pipeline`; Decisions only exposes watchlists + memos; pipeline consumes `GET /api/v1/pipeline/trust-summary`; tracked UI events persist through `POST /api/v1/ui-events`.
  - Verify: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/platform/test_migrations__runtime_tables.py tests/unit/application/test_reporting_service.py tests/unit/adapters/http/test_fastapi_local_api.py -q && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest --run-e2e tests/e2e/ui/test_react_dashboard_routes.py -q && (cd frontend && npm run build)`
  - Files: `frontend/src/App.tsx`, `frontend/src/pages.tsx`, `frontend/src/api.ts`, `frontend/src/track.ts`, `src/adapters/http/app.py`, `src/application/reporting.py`, `src/application/pipeline.py`, `src/platform/domain/models.py`
  - Docs: `docs/implementation/reports/figma_live_alignment_matrix.md`, `docs/manifest/03_decisions.md`, `docs/manifest/04_api_contracts.md`, `docs/manifest/07_observability.md`, `docs/implementation/00_status.md`, `docs/implementation/03_worklog.md`
  - Alternatives: keep V2 breadth and the separate Command Center destination (rejected: too much conceptual weight for too little analyst value)

- [x] 2026-03-11 Dashboard UX redesign packet: the canonical React analyst surface now follows the V2 IA, with `Decisions` replacing split watchlist/memo navigation and real dossier/comp-review/pipeline/command-center routes implemented.
  - AC: workbench truth strip, dossier parity, comp-review workspace, decision-hub merge, pipeline trust surface, and guarded command-center UI all exist with route/data-contract coverage.
  - Verify: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/adapters/http/test_fastapi_local_api.py -q && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest --run-e2e tests/e2e/ui/test_react_dashboard_routes.py -q && (cd frontend && npm run build)`
  - Files: `frontend/src/*`, `src/application/workbench.py`, `src/adapters/http/app.py`, `tests/e2e/ui/test_react_dashboard_routes.py`
  - Docs: `docs/implementation/reports/dashboard_ux_audit_redesign.md`, `docs/implementation/reports/figma_live_alignment_matrix.md`, `docs/implementation/00_status.md`, `docs/implementation/03_worklog.md`
  - Alternatives: keep the old route skeletons and API-only decision surfaces (rejected: misleading hierarchy and fragmented workflows)

- [x] 2026-03-10 ChatMock default backend: shared text, description-analysis, and VLM routes now default to ChatMock/OpenAI-compatible endpoints with explicit Ollama compatibility mode.
  - AC: repo-default model configuration is ChatMock/OpenAI-compatible, unsupported vision requests fail explicitly, and targeted text+vision regression coverage passes.
  - Verify: `python3 -m src.interfaces.cli preflight --help && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/platform/test_llm__chatmock_routing.py tests/unit/listings/services/test_description_analyst__chatmock.py tests/unit/listings/services/test_vlm__chatmock.py --run-integration tests/integration/listings/test_feature_fusion__chatmock_paths.py -q`
  - Files: `src/platform/settings.py`, `src/platform/utils/llm.py`, `src/listings/services/description_analyst.py`, `src/listings/services/llm_normalizer.py`, `src/listings/services/vlm.py`
  - Docs: `README.md`, `docs/reference/configuration.md`, `docs/how_to/configuration.md`, `docs/manifest/02_tech_stack.md`, `docs/manifest/03_decisions.md`, `docs/manifest/07_observability.md`, `docs/manifest/10_testing.md`, `docs/implementation/00_status.md`, `docs/implementation/03_worklog.md`
  - Alternatives: keep description/VLM on direct Ollama-specific clients (rejected: backend changes remained fragmented and vision failures stayed implicit)

- [x] 2026-03-10 UI hotfix: dashboard render no longer drops to the empty state when persisted valuations are older than the 7-day freshness window.
  - AC: real dashboard runtime renders deal cards/memo/insights from existing persisted valuations while pipeline freshness still reports `Refresh due`.
  - Verify: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/interfaces/test_dashboard_loaders__stale_cached_valuations.py -q && /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q && RUN_LIVE=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/live/ui/test_dashboard_live_browser__source_support.py -q`
  - Files: `src/interfaces/dashboard/services/loaders.py`, `src/valuation/services/valuation_persister.py`, `tests/unit/interfaces/test_dashboard_loaders__stale_cached_valuations.py`
  - Docs: `docs/implementation/00_status.md`, `docs/implementation/03_worklog.md`, `docs/implementation/reports/ui_verification_final_report.md`
  - Alternatives: force a preflight refresh before every dashboard load (rejected: broader behavior change than needed for this hotfix)

## Active Packet

- [x] M10: React dashboard UX redesign, V3 prune, and instrumentation are implemented and verified.
  - Progress:
    - [x] UX redesign: workbench truth strip, review queue, and active dossier rail now lead the primary route.
    - [x] V3 prune: primary navigation is now limited to `Workbench`, `Decisions`, and `Pipeline`.
    - [x] Decision Hub simplification: `/watchlists` is the canonical decision-memory destination and `/memos` redirects to its memo tab.
    - [x] Dossier parity: listing detail is now an evidence/provenance-heavy dossier with merged trust framing.
    - [x] Pipeline trust surface: the page now leads with `GET /api/v1/pipeline/trust-summary` and hides lower-level ops detail behind disclosure.
    - [x] Instrumentation: UI events persist through `POST /api/v1/ui-events`.
  - Owner: maintainer
  - Effort: M
  - AC: all major React routes are implemented against real contracts; no major screen ships without explicit state coverage; primary nav is limited to three destinations; pipeline trust and UI instrumentation have explicit backend support; planning/alignment docs reflect the new IA.
  - Verify: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/platform/test_migrations__runtime_tables.py tests/unit/application/test_reporting_service.py tests/unit/adapters/http/test_fastapi_local_api.py -q && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest --run-e2e tests/e2e/ui/test_react_dashboard_routes.py -q && (cd frontend && npm run build)`
  - Files: `frontend/src/App.tsx`, `frontend/src/pages.tsx`, `frontend/src/api.ts`, `frontend/src/types.ts`, `frontend/src/track.ts`, `frontend/src/styles.css`, `src/application/reporting.py`, `src/application/pipeline.py`, `src/adapters/http/app.py`, `src/platform/domain/models.py`
  - Docs: `docs/implementation/reports/dashboard_ux_audit_redesign.md`, `docs/implementation/reports/figma_live_alignment_matrix.md`, `docs/manifest/00_overview.md`, `docs/manifest/03_decisions.md`, `docs/manifest/04_api_contracts.md`, `docs/manifest/07_observability.md`
  - Alternatives: defer simplification until after more backend work (rejected: the product hierarchy itself was still distorting user understanding)

- [ ] M9: Fallback interval policy and post-ablation monitoring triggers are execution-ready.
  - Progress:
    - [x] Prompt-02 mini packet defines `C-10` fallback interval policy with explicit trigger thresholds.
    - [ ] Prompt-03 follow-up validates `M9` routing evidence and records any remaining deferred follow-ons (`C-11`, `C-12`).
  - Owner: maintainer
  - Effort: S
  - AC: fallback interval policy for weak-regime segments is explicit in runtime/runbook docs; follow-on rerun/reevaluation triggers are either codified or explicitly deferred.
  - Verify: `rg -n "C-10|fallback interval|jackknife|weak-regime|CMD-RETRIEVER-ABLATION|cadence|sample-floor" docs/manifest/09_runbook.md docs/manifest/20_literature_review.md docs/implementation/checklists/02_milestones.md docs/implementation/checklists/07_alignment_review.md docs/implementation/reports/alignment_review.md -S`
  - Files: fallback policy + monitoring surfaces under `src/valuation/services/*` and `docs/manifest/*`
  - Docs: `docs/manifest/09_runbook.md`, `docs/manifest/20_literature_review.md`, `docs/implementation/checklists/07_alignment_review.md`, `docs/implementation/reports/alignment_review.md`, `docs/implementation/00_status.md`, `docs/implementation/03_worklog.md`
  - Alternatives: defer fallback policy until release packet (rejected: unresolved uncertainty semantics risk)

- [x] M8: Retrieval ablation and decomposition diagnostics decisions are evidence-backed and execution-ready.
  - Progress:
    - [x] Prompt-02 packet delivered ablation harness/runtime report and decision thresholds for `C-08` + `C-09`.
    - [x] Prompt-03 follow-up reran alignment gate and closed `M8` routing evidence (`C-10` carried forward into `M9`).
  - Owner: maintainer
  - Effort: M
  - AC: retriever ablation outputs and decomposition diagnostics decisions are documented with keep/simplify thresholds and mapped to artifact-backed outcomes.
  - Verify: `rg -n "C-08|C-09|O-02|O-03|ablation|decomposition|land|structure" docs/implementation/checklists/08_artifact_feature_alignment.md docs/implementation/reports/artifact_feature_alignment.md docs/implementation/checklists/02_milestones.md docs/implementation/checklists/07_alignment_review.md docs/implementation/reports/alignment_review.md -S`
  - Files: retrieval ablation surfaces under `src/ml/training/retriever_ablation.py` + `src/interfaces/cli.py` with packet docs under `docs/implementation/*`
  - Docs: `docs/implementation/checklists/08_artifact_feature_alignment.md`, `docs/implementation/reports/artifact_feature_alignment.md`, `docs/implementation/checklists/07_alignment_review.md`, `docs/implementation/reports/alignment_review.md`, `docs/implementation/00_status.md`, `docs/implementation/03_worklog.md`
  - Alternatives: defer retrieval/decomposition decisions (rejected: sustained complexity and trust ambiguity)

- [x] M1: P0 reliability baseline planning is explicit and execution-ready.
  - Owner: maintainer
  - Effort: S
  - AC: P0 outcomes A/B/C from `checkbox.md` are mapped to bounded packets with owners, effort, and acceptance signals.
  - Verify: `rg -n "Outcome A|Outcome B|Outcome C|P0" checkbox.md docs/implementation/checklists/02_milestones.md`
  - Files: `docs/implementation/checklists/02_milestones.md`
  - Docs: `docs/implementation/00_status.md`, `docs/implementation/reports/project_plan.md`
  - Alternatives: N/A

## P0 (Must Fix)

- [x] P0-A: Milestone queue exists with ordered packet IDs and done criteria.
  - Owner: maintainer
  - Effort: S
  - AC: checklist includes M1/M2/M3 packet definitions with explicit acceptance signals.
  - Verify: `rg -n "M1|M2|M3|Acceptance signal" docs/implementation/checklists/02_milestones.md`
  - Files: `docs/implementation/checklists/02_milestones.md`
  - Docs: `docs/implementation/00_status.md`
  - Alternatives: use only free-text status notes (rejected: not checkable)

- [x] P0-B: Observability gate exists and maps objective metrics to measurable signals.
  - Owner: maintainer
  - Effort: M
  - AC: `docs/manifest/07_observability.md` contains logging schema, golden signals, SLI/SLO, and triage commands.
  - Verify: `rg -n "Logging Schema|golden signals|SLI|SLO|Debug Playbook" docs/manifest/07_observability.md`
  - Files: `docs/manifest/07_observability.md`
  - Docs: `docs/manifest/11_ci.md`, `docs/manifest/09_runbook.md`
  - Alternatives: defer observability to release packet (rejected: P0 risk)

- [x] P0-C: CI baseline command mapping is defined and references canonical runbook IDs.
  - Owner: maintainer
  - Effort: M
  - AC: `docs/manifest/11_ci.md` points to `CMD-*` entries in `docs/manifest/09_runbook.md` without duplicating command tables.
  - Verify: `rg -n "CMD-" docs/manifest/11_ci.md docs/manifest/09_runbook.md`
  - Files: `docs/manifest/11_ci.md`, `docs/manifest/09_runbook.md`
  - Docs: `docs/implementation/00_status.md`
  - Alternatives: duplicate full command list in CI doc (rejected: drift risk)

- [x] P0-D: Source support boundaries are explicitly constrained in docs/runtime planning.
  - Owner: maintainer
  - Effort: M
  - AC: milestone/plan notes include source reliability constraint and anti-bot limitation references.
  - Verify: `rg -n "source|anti-bot|crawler" docs/implementation/reports/project_plan.md docs/manifest/00_overview.md docs/crawler_status.md`
  - Files: `docs/implementation/reports/project_plan.md`
  - Docs: `docs/manifest/00_overview.md`, `docs/crawler_status.md`
  - Alternatives: defer source-boundary clarity (rejected: trust risk)

- [x] P0-E: Persisted confidence semantics are calibration-derived and traceable.
  - Owner: maintainer
  - Effort: M
  - AC: valuation persistence no longer uses static placeholder confidence; confidence fields map to calibration/model diagnostics.
  - Verify: `rg -n "confidence_components|calibration_status|projection_component|volatility_penalty" src/valuation/services/valuation_persister.py && python3 -m pytest tests/unit/valuation/test_valuation_persister__confidence_semantics.py -q && rg -n "confidence_components|calibration" docs/how_to/interpret_outputs.md`
  - Files: `src/valuation/services/valuation_persister.py`, `tests/unit/valuation/test_valuation_persister__confidence_semantics.py`
  - Docs: `docs/how_to/interpret_outputs.md`, `docs/implementation/checklists/08_artifact_feature_alignment.md`
  - Alternatives: retain heuristic confidence (rejected: artifact misalignment risk)

- [x] P0-F: Segmented interval coverage is reported and gated per run.
  - Owner: maintainer
  - Effort: M
  - AC: conformal coverage outputs include `region_id`, listing type, and price-band segmentation with explicit thresholds.
  - Verify: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/valuation/test_conformal_calibrator__segmented_coverage_report.py -q && rg -n "segmented_coverage_report|region_id|listing_type|price_band|coverage_floor" src/valuation/services/conformal_calibrator.py src/valuation/workflows/calibration.py docs/manifest/07_observability.md docs/manifest/09_runbook.md`
  - Files: conformal/reporting surfaces in `src/valuation/services/*` and workflow outputs
  - Docs: `docs/manifest/07_observability.md`, `docs/manifest/09_runbook.md`, `docs/implementation/reports/artifact_feature_alignment.md`
  - Alternatives: global-only coverage reporting (rejected: contradicts artifact caveats)

## P1 (Should Fix)

- [x] P1-A: Release discipline artifacts are added and linked from CI docs.
  - Owner: maintainer
  - Effort: M
  - AC: `CHANGELOG.md`, versioning policy, and release readiness checklist exist and are linked from `docs/manifest/11_ci.md`.
  - Verify: `test -f CHANGELOG.md && test -f docs/reference/versioning_policy.md && test -f docs/implementation/checklists/06_release_readiness.md`
  - Files: `CHANGELOG.md`, `docs/reference/versioning_policy.md`, `docs/implementation/checklists/06_release_readiness.md`
  - Docs: `docs/manifest/11_ci.md`, `docs/INDEX.md`
  - Alternatives: keep release process implicit (rejected)

- [x] P1-B: CLI preflight UX exposes actionable options at top-level help.
  - Owner: maintainer
  - Effort: S
  - AC: `python3 -m src.interfaces.cli preflight --help` shows concrete options instead of passthrough placeholder.
  - Verify: `python3 -m src.interfaces.cli preflight --help`
  - Files: `src/interfaces/cli.py`
  - Docs: `README.md`, `docs/manifest/09_runbook.md`
  - Alternatives: retain passthrough behavior (rejected; actionable top-level flags implemented)

- [x] P1-C: Dependency management converges on lockfile-backed install path.
  - Owner: maintainer
  - Effort: S
  - AC: single recommended install flow + lockfile policy documented.
  - Verify: `rg -n "lockfile|install path|Poetry|requirements" docs/manifest/02_tech_stack.md README.md`
  - Files: `pyproject.toml`, `requirements.txt`
  - Docs: `docs/manifest/02_tech_stack.md`, `README.md`
  - Alternatives: dual-path forever (rejected due drift; lockfile-backed path adopted)

- [x] P1-D: Spatial residual diagnostics are emitted and wired to triage.
  - Owner: maintainer
  - Effort: M
  - AC: spatial drift/outlier diagnostics are available in runtime outputs and mapped to runbook triage commands.
  - Verify: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/valuation/test_calibration_workflow__spatial_diagnostics.py -q && rg -n "spatial|Moran|LISA|drift|outlier" src docs/manifest/07_observability.md docs/manifest/09_runbook.md`
  - Files: valuation diagnostics surfaces under `src/valuation/*`
  - Docs: `docs/manifest/07_observability.md`, `docs/manifest/09_runbook.md`
  - Alternatives: keep spatial diagnostics as docs-only intent (rejected)

- [x] P1-E: Fusion model claims are benchmarked against RF/XGBoost baselines.
  - Owner: maintainer
  - Effort: M
  - AC: benchmark report compares fusion vs RF/XGBoost under time+geo splits with explicit acceptance thresholds.
  - Verify: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest tests/unit/ml/test_benchmark_workflow__time_geo_baselines.py tests/unit/interfaces/test_cli__passthrough_flag_forwarding.py -q && python3 -m src.interfaces.cli benchmark --listing-type sale --geo-key city --max-fusion-eval 80 --output-json docs/implementation/reports/fusion_tree_benchmark.json --output-md docs/implementation/reports/fusion_tree_benchmark.md && rg -n "RandomForest|XGBoost|time\\+geo|benchmark|fusion_tree_benchmark" docs/manifest/20_literature_review.md docs/implementation/reports/artifact_feature_alignment.md docs/manifest/10_testing.md docs/manifest/09_runbook.md`
  - Files: `src/ml/training/benchmark.py`, `src/interfaces/cli.py`, `tests/unit/ml/test_benchmark_workflow__time_geo_baselines.py`
  - Docs: `docs/manifest/10_testing.md`, `docs/manifest/09_runbook.md`, `docs/implementation/reports/artifact_feature_alignment.md`
  - Alternatives: rely only on current fusion metrics (rejected: missing baseline guard)

- [x] P1-F: Artifact-feature alignment gate is kept as a checkable milestone surface.
  - Owner: contributor
  - Effort: S
  - AC: artifact-feature alignment checklist/report stay updated and are referenced by milestone packets.
  - Verify: `test -f docs/implementation/checklists/08_artifact_feature_alignment.md && test -f docs/implementation/reports/artifact_feature_alignment.md && rg -n "C-04|P1-E|P1-F|artifact_feature_alignment" docs/implementation/checklists/02_milestones.md docs/implementation/checklists/08_artifact_feature_alignment.md docs/implementation/reports/artifact_feature_alignment.md docs/implementation/00_status.md docs/implementation/03_worklog.md`
  - Files: `docs/implementation/checklists/08_artifact_feature_alignment.md`, `docs/implementation/reports/artifact_feature_alignment.md`, `docs/implementation/checklists/02_milestones.md`
  - Docs: `docs/implementation/00_status.md`, `docs/implementation/03_worklog.md`, `docs/manifest/03_decisions.md`
  - Alternatives: run one-off alignment gate only (rejected)

- [x] P1-G: Artifact-backed assumption badges are visible in runtime API/dashboard surfaces.
  - Owner: maintainer
  - Effort: M
  - AC: runtime status payloads and dashboard views include explicit assumption/calibration badges linked to docs caveats.
  - Verify: `rg -n "assumption|calibration|badge" src/interfaces/api/pipeline.py src/interfaces/dashboard/app.py docs/how_to/interpret_outputs.md -S && /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q`
  - Files: `src/interfaces/api/pipeline.py`, `src/interfaces/dashboard/app.py`
  - Docs: `docs/how_to/interpret_outputs.md`, `docs/implementation/checklists/08_artifact_feature_alignment.md`, `docs/implementation/reports/artifact_feature_alignment.md`
  - Alternatives: keep assumptions as docs-only caveats (rejected)

- [x] P1-H: Live-browser evidence confirms source-support labels under real dashboard runtime.
  - Owner: maintainer
  - Effort: S
  - AC: prompt-06 artifacts include live-session evidence for `supported|blocked|fallback` labels with no runtime exceptions.
  - Verify: `python3 -m src.interfaces.cli dashboard --help && rg -n "G-02|supported\\|blocked\\|fallback|live browser|live-session|real Streamlit" docs/implementation/checklists/05_ui_verification.md docs/implementation/reports/ui_verification_final_report.md -S`
  - Files: `docs/implementation/checklists/05_ui_verification.md`, `docs/implementation/reports/ui_verification_final_report.md`
  - Docs: `docs/implementation/00_status.md`, `docs/implementation/03_worklog.md`
  - Alternatives: rely only on fixture-backed AppTest evidence (rejected)

## P2 (Nice to Have)

- [x] P2-A: Docs navigation has one canonical top-level index for user/internal docs.
  - Owner: contributor
  - Effort: S
  - AC: `docs/INDEX.md` clearly states canonical navigation and links all active docs sections.
  - Verify: `rg -n "Quick Links|Navigation|Engineering Docs|Where To Look Next" docs/INDEX.md`
  - Files: `docs/INDEX.md`
  - Docs: `docs/INDEX.md`
  - Alternatives: leave split index ownership (rejected)

- [x] P2-B: Valuation output interpretation guide is added for user-facing confidence/evidence semantics.
  - Owner: contributor
  - Effort: M
  - AC: dedicated how-to/reference page exists and is linked from docs index.
  - Verify: `rg -n "interpret" docs/how_to docs/reference docs/INDEX.md`
  - Files: `docs/how_to/interpret_outputs.md` (planned)
  - Docs: `docs/INDEX.md`
  - Alternatives: keep interpretation implicit in architecture docs (rejected)

## Improvement Bet Outcomes (Prompt-14)

- [x] IB-01: Improvement packet 1 outcomes are routed and ready for implementation kickoff.
  - Owner: maintainer
  - Effort: S
  - AC: `03_improvement_bets.md` exists and Packet-1 directions are mapped to milestone-ready results (`IB-01`, `IB-02`, `IB-04`).
  - Verify: `test -f docs/implementation/checklists/03_improvement_bets.md && rg -n "IB-01|IB-02|IB-04" docs/implementation/checklists/03_improvement_bets.md docs/implementation/reports/improvement_directions.md`
  - Files: `docs/implementation/checklists/03_improvement_bets.md`, `docs/implementation/reports/improvement_directions.md`
  - Docs: `docs/implementation/00_status.md`, `docs/implementation/03_worklog.md`
  - Alternatives: keep ad-hoc improvement notes only (rejected)

- [x] IB-02: Confidence and coverage trust outcomes are integrated as hard milestone gates.
  - Owner: maintainer
  - Effort: M
  - AC: `P0-E` and `P0-F` keep explicit verification paths and remain linked from improvement bets until both are closed.
  - Verify: `rg -n "P0-E|P0-F|IB-01|IB-02" docs/implementation/checklists/02_milestones.md docs/implementation/checklists/03_improvement_bets.md`
  - Files: `docs/implementation/checklists/02_milestones.md`
  - Docs: `docs/implementation/checklists/03_improvement_bets.md`, `docs/implementation/reports/improvement_directions.md`
  - Alternatives: defer confidence/coverage to later packet (rejected)

- [x] IB-03: Benchmark and artifact-contract outcomes are converted into checkable gates.
  - Owner: maintainer
  - Effort: M
  - AC: baseline benchmark (`IB-03`) and artifact contract (`IB-05`) include CI/docs verification signals before release packet expansion.
  - Verify: `python3 scripts/check_artifact_feature_contract.py && rg -n "IB-03|IB-05|benchmark|artifact-feature|CMD-ARTIFACT-FEATURE-CONTRACT-CHECK" docs/implementation/checklists/03_improvement_bets.md docs/implementation/reports/improvement_directions.md docs/implementation/reports/artifact_feature_alignment.md docs/manifest/09_runbook.md docs/manifest/11_ci.md`
  - Files: `docs/implementation/checklists/03_improvement_bets.md`, `scripts/check_artifact_feature_contract.py`, docs/CI check surfaces
  - Docs: `docs/manifest/10_testing.md`, `docs/manifest/11_ci.md`, `docs/manifest/09_runbook.md`
  - Alternatives: rely on manual review only (rejected)

## Packets and Sequence

- [x] Packet M1 (`small`, now): complete P0-A/P0-B/P0-C planning and docs mapping.
  - Acceptance signal: this checklist plus runbook/observability/ci pointer docs exist and pass grep verification.
- [x] Packet M2 (`medium`, now): implement CI workflow baseline and docs-sync guardrail execution.
  - Acceptance signal: `.github/workflows/ci.yml` exists and runs offline gate commands.
- [x] Packet M3 (`medium`, now): implement P1 release discipline artifacts.
  - Acceptance signal: release docs exist and are linked from CI/reference surfaces.
- [x] Packet M4 (`small`, now): run artifact-feature alignment gate and route outcomes into measurable milestones.
  - Acceptance signal: prompt-15 deliverables exist and P0-E/P0-F/P1-D/P1-E/P1-F are tracked.
- [x] Packet M5 (`small`, now): run improvement-direction discovery and produce implementation-ready bet checklist.
  - Acceptance signal: prompt-14 deliverables exist (`improvement_directions.md`, `03_improvement_bets.md`) and improvement outcomes are milestone-mapped.

- [x] Packet M6 (`medium`, next): execute UI verification loop and surface runtime source-support status.
  - Progress:
    - [x] Prompt-06 UI verification artifacts delivered (`docs/implementation/checklists/05_ui_verification.md`, `docs/implementation/reports/ui_verification_final_report.md`, `tests/e2e/ui/test_dashboard_ui_verification_loop.py`).
    - [x] Runtime source-support/fallback labels are surfaced in API/dashboard runtime status payloads.
  - Acceptance signal: UI verification artifacts exist (prompt-06 deliverables) and API/dashboard outputs expose supported/blocked/fallback source labels.
  - Verify: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/interfaces/test_pipeline_api__source_support.py -q && /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q && rg -n "supported|blocked|fallback|source_support|source support" src/interfaces/api/pipeline.py src/interfaces/dashboard/app.py -S`
  - Files: `src/interfaces/api/pipeline.py`, `src/interfaces/dashboard/services/loaders.py`, `src/interfaces/dashboard/app.py`, `tests/unit/interfaces/test_pipeline_api__source_support.py`, `tests/e2e/ui/test_dashboard_ui_verification_loop.py`
  - Docs: `docs/crawler_status.md`, `docs/manifest/04_api_contracts.md`, `docs/manifest/07_observability.md`, `docs/implementation/checklists/05_ui_verification.md`, `docs/implementation/reports/ui_verification_final_report.md`, `docs/implementation/00_status.md`, `docs/implementation/03_worklog.md`
  - Alternatives: defer UI verification until after source-status surfacing (rejected; regression risk in current dashboard flows).

- [x] Packet M7 (`medium`, now): execute post-`M6` trust closure (`C-06` + `C-07`).
  - Progress:
    - [x] Prompt-02 follow-up: add artifact-backed assumption badges to API/dashboard runtime surfaces (`O-04`).
    - [x] Prompt-06 follow-up: capture live-browser verification evidence for source labels (`G-02`/`O-05`).
    - [x] Prompt-03 follow-up: rerun alignment gate with updated trust evidence.
  - Acceptance signal: assumption/calibration badges are visible in runtime UI/API responses and prompt-06 artifacts contain real runtime verification evidence.
  - Verify: `/Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest --run-e2e tests/e2e/ui/test_dashboard_ui_verification_loop.py -q && rg -n "assumption|calibration|badge|G-02|live browser|source_support" src/interfaces/api/pipeline.py src/interfaces/dashboard/app.py docs/how_to/interpret_outputs.md docs/implementation/checklists/05_ui_verification.md docs/implementation/reports/ui_verification_final_report.md -S`
  - Files: `src/interfaces/api/pipeline.py`, `src/interfaces/dashboard/app.py`, `docs/implementation/checklists/05_ui_verification.md`, `docs/implementation/reports/ui_verification_final_report.md`
  - Docs: `docs/implementation/checklists/08_artifact_feature_alignment.md`, `docs/implementation/reports/artifact_feature_alignment.md`, `docs/implementation/checklists/07_alignment_review.md`, `docs/implementation/reports/alignment_review.md`, `docs/implementation/00_status.md`, `docs/implementation/03_worklog.md`
  - Alternatives: split `C-06` and `C-07` into separate packets (rejected: coupled trust evidence and better routing coherence)

- [x] Packet M8 (`medium`, completed): execute retrieval ablation and decomposition diagnostics decision packet (`C-08` + `C-09`).
  - Progress:
    - [x] Prompt-02: retriever ablation harness, CLI wiring, tests, and report artifacts landed; `C-08`/`C-09` marked closed in alignment docs.
    - [x] Prompt-03 follow-up: refreshed alignment gate and marked packet closure evidence.
  - Acceptance signal: ablation report and decomposition-diagnostics decision note exist with explicit keep/simplify thresholds and verification commands.
  - Verify: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m pytest tests/unit/ml/test_retriever_ablation_workflow__decisions.py tests/unit/interfaces/test_cli__passthrough_flag_forwarding.py -q && /Users/nirtzur/Documents/projects/property_scanner/venv/bin/python -m src.interfaces.cli retriever-ablation --listing-type sale --max-targets 80 --num-comps 5 --output-json docs/implementation/reports/retriever_ablation_report.json --output-md docs/implementation/reports/retriever_ablation_report.md && rg -n "C-08|C-09|O-02|O-03|retriever_ablation_report|decomposition" docs/implementation/reports/artifact_feature_alignment.md docs/manifest/20_literature_review.md docs/implementation/checklists/08_artifact_feature_alignment.md -S`
  - Files: retrieval evaluation surfaces and implementation reports/checklists
  - Docs: `docs/implementation/reports/artifact_feature_alignment.md`, `docs/implementation/checklists/08_artifact_feature_alignment.md`, `docs/implementation/00_status.md`, `docs/implementation/03_worklog.md`
  - Alternatives: defer retrieval diagnostics indefinitely (rejected: complexity drift risk)

- [ ] Packet M9 (`small`, now): land fallback interval policy and finalize post-`M8` operational triggers (`C-10`, optional `C-11`/`C-12`).
  - Progress:
    - [x] Prompt-02: define fallback interval trigger policy and runbook mapping.
    - [ ] Prompt-03 follow-up: re-check alignment and confirm only deferred leftovers remain.
  - Acceptance signal: fallback interval policy is explicit for weak-regime segments and routing docs clearly indicate whether `C-11`/`C-12` were absorbed or deferred.
  - Verify: `rg -n "C-10|fallback interval|jackknife|weak-regime|cadence|sample-floor" docs/manifest/09_runbook.md docs/manifest/20_literature_review.md docs/implementation/checklists/07_alignment_review.md docs/implementation/reports/alignment_review.md docs/implementation/checklists/02_milestones.md -S`
  - Files: fallback interval + monitoring docs/runtime surfaces under `src/valuation/services/*`, `docs/manifest/*`, and `docs/implementation/*`
  - Docs: `docs/manifest/09_runbook.md`, `docs/manifest/20_literature_review.md`, `docs/implementation/checklists/07_alignment_review.md`, `docs/implementation/reports/alignment_review.md`, `docs/implementation/00_status.md`, `docs/implementation/03_worklog.md`
  - Alternatives: defer fallback policy to release readiness (rejected: unresolved uncertainty policy risk)

## Deferred / Not Now

- [x] Research-track prompts (`prompt-12`, `prompt-13`) executed; further reruns are optional and should not block P0/P1 reliability outcomes.
- [ ] UI polish packets remain deferred until reliability gates are in place.
