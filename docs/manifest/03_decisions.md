# Decisions

This file records durable engineering decisions.

## 2026-03-11: V3 Prune Removes Command Center From The Product IA

- Decision: simplify the React product to three primary destinations, remove Command Center as a product surface, keep `/command-center` only as a compatibility redirect to `/pipeline`, and reduce `Decisions` to watchlists plus memos.
- Context:
  - the V2 redesign improved route parity, but the live product still spent too much attention on secondary surfaces and low-confidence advisory framing.
  - the follow-up audit found that `Command Center` imposed conceptual weight without enough differentiated value, and that `saved searches` and `alerts` did not deserve equal footing with watchlists and memos inside `Decisions`.
  - the new backend additions (`GET /api/v1/pipeline/trust-summary`, `POST /api/v1/ui-events`) support a slimmer trust-first pipeline and future validation without keeping the extra destination.
- Mechanism:
  - primary nav is now:
    - `Workbench`
    - `Decisions`
    - `Pipeline`
  - `/watchlists` remains the canonical decision-memory route and `/memos` still redirects to its memo tab.
  - `/command-center` now records a `command_center_redirected` UI event and redirects to `/pipeline`.
  - saved-search creation stays near the Workbench lens rather than as a `Decisions` tab.
  - pipeline trust is now served by the aggregate `GET /api/v1/pipeline/trust-summary` contract and lower-level operational detail moves behind disclosure.
- Alternatives considered:
  - keep Command Center as a read-mostly page.
  - rejected because the workflow had not earned a full product destination and weakened first-use clarity.
  - keep saved searches and alerts as `Decisions` tabs.
  - rejected because they are supporting mechanics, not primary analyst outcomes.

Rationale: the product should feel calmer and more obviously useful. Three destinations are enough for the current analyst workflow, and trust should be folded into Pipeline rather than implied through a weak assistant surface.

## 2026-03-11: React Workbench Is Canonical and Decision Memory Is Merged

- Decision: treat the FastAPI-served React workbench as the canonical product surface, and merge watchlists, saved searches, memos, and alerts into one `Decisions` destination.
- Context:
  - the repo had already moved onboarding toward the React workbench, but the live route structure still preserved fragmented product memory (`Watchlists` and `Memos` as separate primary destinations).
  - the redesign audit found that the split nav obscured the actual workflow boundary between exploration, investigation, decision memory, operations, and guarded advisory context.
  - the old React listing and comp-review routes were too skeletal to behave like real dossier/workbench surfaces, which made the primary journey look less coherent than the underlying backend actually was.
- Mechanism:
  - primary nav is now:
    - `Workbench`
    - `Decisions`
    - `Pipeline`
    - `Command Center`
  - `/watchlists` is the canonical merged decision-memory route and `/memos` redirects to its memo tab.
  - listing detail now consumes a dossier-grade workbench context contract.
  - comp review now consumes a dedicated workspace aggregation contract instead of a raw persistence list.
  - pipeline and command-center routes remain separate because they serve trust and advisory functions, not listing exploration or decision memory.
- Alternatives considered:
  - keep watchlists and memos as separate primary-nav items.
  - rejected because it duplicated decision-memory surfaces and weakened information scent.
  - keep Streamlit as a parallel first-class dashboard surface.
  - rejected because the canonical implementation path, design system, and verification packet are now centered on the React product.

Rationale: the product should read like one coherent analyst system. Exploration, dossier review, decision memory, operational trust, and guarded advisory context are distinct jobs, but watchlists and memos are not distinct top-level products.

## 2026-03-10: Weak-Regime Interval Fallback Uses Explicit Bootstrap Policy

- Decision: keep segmented conformal calibration as the primary uncertainty path, but switch to explicit bootstrap fallback intervals for weak-regime segments.
- Context:
  - `M9/C-10` required the repo to stop treating fallback interval behavior as an undocumented gap.
  - the valuation service already had a bootstrap widening path, but trigger semantics were implicit and depended only on sample count.
- Mechanism:
  - added a shared interval-policy decision in `src/valuation/services/conformal_calibrator.py`.
  - calibrated intervals are used only when the segment is seen, `n_samples >= 20`, and empirical segment coverage remains above the default floor (`target_coverage - 0.05`, currently `0.80`).
  - otherwise the service uses wider bootstrap intervals and persists the reason in valuation evidence (`unseen_segment`, `insufficient_samples`, `coverage_below_floor`).
  - updated pipeline assumption badges so `lit-jackknifeplus-2021` is a runtime `caution` policy, not a `gap`.
- Alternatives considered:
  - keep bootstrap behavior implicit behind `is_calibrated(...)`.
  - rejected because operators could not distinguish low-data fallback from genuinely calibrated intervals.

Rationale: the product should never overstate interval validity in weak regimes; explicit fallback is safer than silent pseudo-calibration.

## 2026-03-10: ChatMock Becomes the Default OpenAI-Compatible Backend

- Decision: make ChatMock the default backend for shared text completions, description analysis, and vision requests, while keeping Ollama as an explicit compatibility mode.
- Context:
  - the repo previously split model behavior across LiteLLM fallbacks and direct Ollama-specific request code.
  - that made backend changes slower and left the description-analysis and vision paths outside the shared config surface.
- Mechanism:
  - extended config with provider-level routing fields (`provider`, `api_base`, `api_key_env`, `text_models`, `vision_model`, `supports_vision`).
  - refactored `src/platform/utils/llm.py` into the canonical OpenAI-compatible completion path with ordered fallback, auth/env lookup, and explicit `api_base` routing.
  - moved `src/listings/services/description_analyst.py` onto the shared completion path.
  - migrated `src/listings/services/vlm.py` to OpenAI-style multimodal requests by default and made unsupported-vision failures explicit instead of silently reverting to Ollama.
  - retained explicit `provider="ollama"` compatibility mode for local fallback workflows.
- Alternatives considered:
  - keep the shared text path on LiteLLM but leave description/VLM on Ollama-specific clients.
  - rejected because backend changes would still require touching multiple unrelated service implementations and vision failures would remain implicit.

Rationale: one config-driven OpenAI-compatible route keeps model backends swappable and makes unsupported vision behavior observable instead of hidden.

## 2026-02-09: M8 Retriever Ablation Packet Uses Explicit Keep/Simplify Thresholds

- Decision: implement a dedicated retriever ablation harness and route semantic-retrieval complexity decisions using explicit thresholds.
- Context:
  - `M8/C-08` required reproducible comparison of `geo-only`, `geo+structure`, and `geo+structure+semantic` comp-selection modes.
  - prior docs identified retrieval complexity risk (`O-02`) but had no executable decision packet.
- Mechanism:
  - added `src/ml/training/retriever_ablation.py` and CLI passthrough command `retriever-ablation`.
  - command emits `docs/implementation/reports/retriever_ablation_report.{json,md}` with:
    - per-mode coverage/MAE/MAPE/MedAE,
    - semantic keep/simplify decision thresholds,
    - embedding-drift proxy checks from retriever metadata lock.
  - current packet outcome recommends `simplify` for semantic retrieval at configured thresholds.
- Alternatives considered:
  - keep semantic retrieval by default without periodic ablation.
  - rejected because complexity drift would remain unbounded and non-falsifiable.

Rationale: retrieval complexity needs a repeatable decision surface, not one-off intuition.

## 2026-02-09: Pipeline Status Includes Artifact-Backed Assumption Badges

- Decision: extend runtime pipeline status payloads with artifact-backed assumption badges and render them in dashboard status views.
- Context:
  - active packet `M7/C-06` required trust-visible assumption cues in user-facing API/dashboard outputs.
  - source labels (`supported|blocked|fallback`) existed, but literature caveats and known gaps were still docs-only.
- Mechanism:
  - added `PipelineAPI.assumption_badges(...)` and embedded its output into `PipelineAPI.pipeline_status(...)`.
  - badge contract fields: `id`, `label`, `status`, `artifact_ids`, `summary`, `guide_path`.
  - badges currently cover:
    - source coverage caveat (`lit-case-shiller-1988`),
    - conformal coverage caveat (`lit-conformal-tutorial-2021`),
    - jackknife+ fallback caution (`lit-jackknifeplus-2021`),
    - land/structure decomposition diagnostics gap (`lit-deng-gyourko-wu-2012`).
  - updated dashboard status surfaces to render assumption badge lines in both compact and detailed status views.
  - added regression checks in unit (`test_pipeline_api__source_support.py`) and UI E2E (`test_dashboard_ui_verification_loop.py`).
- Alternatives considered:
  - keep assumption caveats in docs only.
  - rejected because runtime trust interpretation remained implicit and easy to miss during operator workflows.

Rationale: assumption caveats should be explicit where operators read runtime status, not only in implementation reports.

## 2026-02-09: Runtime Source-Support Labels Are Exposed via Pipeline Status

- Decision: expose explicit `supported|blocked|fallback` source labels in runtime API/dashboard status payloads.
- Context:
  - active packet `M6/C-02` required trust-visible source support semantics in user-facing runtime surfaces.
  - pipeline status previously surfaced freshness fields only (`needs_refresh`, `reasons`) with no source support context.
- Mechanism:
  - added `PipelineAPI.source_support_summary()` and `PipelineAPI.pipeline_status()` in `src/interfaces/api/pipeline.py`.
  - classification inputs:
    - configured sources in `config/sources.yaml`,
    - operational/blocking evidence in `docs/crawler_status.md`.
  - updated dashboard loader/UI to render source counts and per-label examples in `🧭 Pipeline Status`.
  - added regression coverage for classification + UI rendering.
- Alternatives considered:
  - keep source support semantics in docs only.
  - rejected because runtime trust state would remain implicit and hard to validate during operations.

Rationale: operators need explicit runtime source trust labels to interpret pipeline health and avoid over-trusting blocked/unverified sources.

## 2026-02-09: Legacy Top-Level Docs Migrated Into Diataxis Tree

- Decision: retire legacy top-level docs (`docs/00..08`) and keep migrated content only in the Diataxis + engineering-docs structure.
- Context:
  - repo had both legacy numbered docs and newer Diataxis docs, creating parallel documentation surfaces.
  - user requirement was explicit: transfer old docs into the new prompt-library format and remove old docs.
- Mechanism:
  - migrated legacy content into `docs/explanation/*` pages linked from `docs/INDEX.md`.
  - updated README and internal references to point at canonical new paths.
  - removed `docs/00_docs_index.md` through `docs/08_path_to_production.md`.
- Alternatives considered:
  - keep legacy docs as supplemental pages.
  - rejected because dual structures create drift and navigation ambiguity.

Rationale: one canonical docs format improves discoverability and keeps maintenance bounded.

## 2026-02-08: Artifact-Feature Mapping Contract Is CI-Enforced

- Decision: enforce artifact-feature mapping integrity with a dedicated docs/CI contract check.
- Context:
  - `IB-05` and `O-01` required artifact IDs to remain tied to feature/test mappings as an executable gate.
  - manual alignment review alone could drift as artifacts or docs changed.
- Mechanism:
  - added `scripts/check_artifact_feature_contract.py`.
  - checker validates:
    - artifact IDs from `docs/artifacts/index.json` are present in alignment report mappings.
    - alignment checklist includes the `O-01` contract entry.
    - improvement and milestone checklists retain `IB-05` / `IB-03` artifact-contract governance references.
  - added CI integration in `.github/workflows/ci.yml` and command-map docs references.
- Alternatives considered:
  - keep artifact-feature alignment as a manual review-only checklist.
  - rejected because trust-critical mapping drift would remain unchecked.

Rationale: load-bearing external claims need machine-checkable mapping contracts, not only narrative alignment notes.

## 2026-02-08: Artifact-Feature Alignment Surfaces Remain a Milestone Gate

- Decision: treat artifact-feature alignment checklist/report files as persistent milestone-gate artifacts, not one-time prompt outputs.
- Context:
  - milestone `P1-F` required alignment surfaces to remain checkable and referenced by active milestone packets.
  - after `P1-E`, alignment mappings needed explicit sync to avoid drift between completed work and literature-backed claims.
- Mechanism:
  - kept `docs/implementation/checklists/08_artifact_feature_alignment.md` and `docs/implementation/reports/artifact_feature_alignment.md` in active milestone verification paths.
  - updated `docs/implementation/checklists/02_milestones.md`, status, and worklog references to preserve ongoing checkability.
- Alternatives considered:
  - leave alignment docs as static one-off outputs.
  - rejected because milestone evidence would drift from actual implementation state.

Rationale: alignment artifacts must stay live and checkable so trust-critical claims remain auditable over time.

## 2026-02-08: Fusion-vs-Tree Benchmark Gate is Required Before Fusion Performance Claims

- Decision: require a benchmark gate that compares fusion valuation behavior against `RandomForest` and `XGBoost` baselines under time+geo splits.
- Context:
  - milestone `P1-E` required explicit baseline benchmarking as a trust guard for model-complexity claims.
  - artifact alignment linked `lit-breiman-2001` and `lit-xgboost-2016` to a missing operational benchmark gate.
- Mechanism:
  - added benchmark harness at `src/ml/training/benchmark.py` (data loading, split generation, baseline/fusion evaluation, gate thresholds, report writers).
  - wired CLI command `benchmark` in `src/interfaces/cli.py`.
  - added targeted unit coverage for split/gate behavior and CLI forwarding.
  - emitted benchmark artifacts at `docs/implementation/reports/fusion_tree_benchmark.{json,md}`.
- Alternatives considered:
  - rely on fusion-only metrics without enforced tabular baselines.
  - rejected because baseline-free comparisons cannot detect complexity regressions reliably.

Rationale: fusion claims must be benchmarked against strong tabular baselines on leak-safe splits before being treated as trusted improvements.

## 2026-02-08: Spatial Residual Diagnostics Added to Calibration Workflow

- Decision: add runtime-emitted spatial residual diagnostics (drift/outlier warnings) as part of calibration refresh outputs.
- Context:
  - milestone `P1-D` required spatial diagnostics to be emitted and wired to triage.
  - artifact alignment tied `lit-anselin-1995` claims to missing operational diagnostics.
- Mechanism:
  - added `build_spatial_residual_diagnostics` in `src/valuation/workflows/calibration.py`.
  - added optional workflow output `--spatial-diagnostics-output` plus thresholds for drift/outlier evaluation.
  - added Moran/LISA proxy fields (`lisa_like_hotspot`, method/notes metadata) and runbook/observability triage mapping.
  - fixed wrapper passthrough forwarding in `src/interfaces/cli.py` so calibrator flags are forwarded in order.
- Alternatives considered:
  - keep spatial diagnostics as docs-only intent.
  - rejected because diagnostics would remain non-operational and unverifiable in runtime outputs.

Rationale: segment-level spatial drift/outlier outputs make location-sensitive model risk observable and triageable.

## 2026-02-08: Segmented Conformal Coverage Reporting is a Required Calibration Output

- Decision: calibration refresh runs should be able to emit a segmented coverage report keyed by `region_id`, `listing_type`, `price_band`, and `horizon_months`.
- Context:
  - milestone `P0-F` required explicit conditional-coverage visibility beyond aggregate calibration diagnostics.
  - artifact alignment identified segmented coverage as a trust-critical gap.
- Mechanism:
  - added `segmented_coverage_report` to `StratifiedCalibratorRegistry`.
  - added workflow support in `src/valuation/workflows/calibration.py` to write a JSON coverage report with threshold metadata.
  - added targeted unit tests plus runbook/observability references for triage.
- Alternatives considered:
  - keep diagnostics implicit in in-memory calibrator state only.
  - rejected because operational coverage drift would remain hard to detect and gate per segment.

Rationale: segment-aware coverage outputs make uncertainty quality measurable and actionable during calibration runs.

## 2026-02-08: Persisted Confidence Uses Calibration-Derived Composite Semantics

- Decision: replace static persisted confidence in valuation persistence with a traceable composite score.
- Context:
  - milestone `P0-E` required confidence semantics to be derived from model diagnostics instead of placeholders.
  - artifact alignment highlighted confidence semantics as a trust-critical gap.
- Mechanism:
  - removed static confidence assignment from `src/valuation/services/valuation_persister.py`.
  - derived confidence from interval uncertainty, calibration status, projection confidence, comp support depth, and risk penalties.
  - persisted component breakdown in `valuations.evidence.confidence_components`.
  - added targeted unit coverage for confidence persistence behavior.
- Alternatives considered:
  - keep fixed confidence and explain caveats in docs only.
  - rejected because confidence would remain non-falsifiable and disconnected from model quality signals.

Rationale: persisted confidence must reflect measurable evidence quality so downstream triage and UI interpretation remain trustworthy.

## 2026-02-08: Canonical Dependency Install Path is Lockfile-Backed

- Decision: use `requirements.lock` as the single canonical dependency install surface; treat `requirements.txt` as the editable constraint input.
- Context:
  - milestone `P1-C` identified drift risk from ambiguous/dual install paths.
  - release and CI checks require reproducible dependency resolution across environments.
- Mechanism:
  - generated `requirements.lock` with `pip-tools`.
  - updated install and stack docs to standardize on `python3 -m pip install -r requirements.lock`.
  - documented lock regeneration command for maintainers.
- Alternatives considered:
  - retain dual pip/Poetry install paths as equivalent defaults.
  - rejected because parallel install paths increase drift and troubleshooting overhead.

Rationale: a committed lockfile gives a deterministic baseline for local runs, CI gates, and release checks.

## 2026-02-08: Execute Prompt-13 Research Paper Verification

- Decision: create a paper-backed verification harness that binds load-bearing equations to code and tests.
- Context:
  - `prompt-12` established the literature base, but claims still needed reproducible, code-linked verification.
  - research outputs must remain auditable as code evolves.
- Mechanism:
  - added `paper/main.tex`, `paper/implementation_map.md`, `paper/verification_log.md`, and `paper/README.md`.
  - added `scripts/verify_paper_contract.py` and `scripts/paper_generate_sanity_artifact.py` plus unit tests in `tests/unit/paper/`.
  - generated `paper/artifacts/sanity_case.json` as a deterministic regression anchor.
- Alternatives considered:
  - keep research validation in narrative docs only.
  - rejected because it cannot detect paper/code drift or enforce invariants.

Rationale: a paper-to-code contract plus tests makes research claims falsifiable and maintainable.

## 2026-02-08: Execute Prompt-02 as a Bounded Packet (Standard Mode)

- Decision: run `prompt-02-app-development-playbook` in **Standard** intensity and constrain this turn to Packet 1 (milestones + observability/CI mapping docs).
- Context:
  - `prompt-02` full surface is large and would exceed bounded-bet discipline in one run.
  - prompt-00 routing and `checkbox.md` handoff prioritize P0 outcomes before release/research tracks.
- Mechanism:
  - created missing Packet 1 docs (`02_milestones.md`, observability/runbook/ci pointers, project plan, assumptions register, epic doc).
  - deferred release-doc packet (`prompt-11`) and research packets (`prompt-12`, `prompt-13`) as explicit not-now.
- Alternatives considered:
  - execute the full prompt-02 deliverable set in one pass.
  - rejected due high churn risk and reduced verification quality.

Rationale: bounded packets keep execution auditable and aligned with objective risk closure.

## 2026-02-08: Canonical Command Map Moved to Runbook

- Decision: set `docs/manifest/09_runbook.md` as canonical command map source and point CI/testing docs to command IDs there.
- Context:
  - command-map content was previously embedded in testing docs, which increased duplication risk.
  - docs system charter defines runbook as canonical command map location.
- Mechanism:
  - updated `docs/.prompt_system.yml` `command_map_file` to `docs/manifest/09_runbook.md`.
  - updated `docs/manifest/10_testing.md` and `docs/manifest/11_ci.md` to pointer-based mapping.
- Alternatives considered:
  - keep command map duplicated in testing and CI docs.
  - rejected because duplicated tables drift over time.

Rationale: single-source command map reduces maintenance and routing ambiguity.

## 2026-02-08: Stack Option Selection for P0 Reliability Work

- Decision: choose Option A (simplest robust existing stack) for current packet; defer Option B (scaling-oriented runtime changes).
- Context:
  - objective constraints prioritize local-first reliability and reproducibility.
  - current risks are governance/observability/CI gaps, not immediate scaling bottlenecks.
- Mechanism:
  - documented options and selected approach in `docs/manifest/02_tech_stack.md`.
  - deferred DB/runtime migration considerations to later release-hardening packets.
- Alternatives considered:
  - switch default DB runtime to Postgres in current packet.
  - rejected due unnecessary migration risk before P0 gates are in place.

Rationale: close reliability governance gaps before infrastructure migration.

## 2026-02-08: Add CI Baseline with Docs-Sync Guardrail

- Decision: introduce GitHub Actions CI baseline (`.github/workflows/ci.yml`) with two required jobs: docs-sync guardrail and offline quality gates.
- Context:
  - milestone packet M2 requires executable CI, not only CI planning docs.
  - prompt-system integrity requires docs updates to stay coupled to runtime/test/CI changes.
- Mechanism:
  - added `docs-sync-guardrail` job invoking `scripts/check_docs_sync.py`.
  - added command-map integrity check invoking `scripts/check_command_map.py`.
  - added `offline-quality-gates` job for CLI surface + marker visibility + unit/integration/e2e offline suites.
  - aligned CI docs and runbook command IDs in `docs/manifest/09_runbook.md` and `docs/manifest/11_ci.md`.
- Alternatives considered:
  - keep CI absent and rely on local status evidence only.
  - rejected because P0 reliability acceptance requires enforceable gates.

Rationale: make reliability expectations machine-enforced before further scope expansion.

## 2026-02-08: Execute Prompt-11 Release Documentation Packet

- Decision: add Diataxis-aligned onboarding/reference/release docs and formal release-readiness checklist in one bounded docs packet.
- Context:
  - post-CI audit identified release discipline docs as highest remaining trust gap.
  - command-map and CI baseline already existed, enabling release workflow mapping.
- Mechanism:
  - added `CHANGELOG.md`, versioning policy, release workflow mapping, upgrade notes template, release readiness checklist.
  - added user-facing docs pages under `docs/getting_started`, `docs/how_to`, `docs/reference`, `docs/explanation`, plus troubleshooting and glossary.
  - updated `docs/INDEX.md` as canonical navigation with quick links and deferred-notes section.
- Alternatives considered:
  - keep release policy implicit and defer all user docs to a later cycle.
  - rejected because it leaves high-impact adoption and release risks unresolved.

Rationale: release readiness and docs discoverability are now explicit and verifiable from repo artifacts.

## 2026-02-08: Execute Prompt-12 Literature Validation Packet

- Decision: run the literature-validation packet with artifact-grounded citations before moving to paper verification (`prompt-13`).
- Context:
  - release-discipline artifacts are now present, so the next unresolved packet is research validation.
  - router still surfaces `prompt-07` due uncommitted CI files, so execution needs explicit anti-loop packet discipline.
- Mechanism:
  - added `docs/manifest/20_literature_review.md` with scoped questions, claim table, contradictions, and project decisions.
  - added `docs/implementation/reports/20_literature_review_log.md` with search log, inclusion/exclusion rationale, and per-source notes.
  - added `docs/implementation/checklists/20_literature_review.md`.
  - initialized `docs/artifacts/index.json` and captured 14 DOI/arXiv metadata artifacts.
- Alternatives considered:
  - skip artifact capture and keep references inline only.
  - rejected because prompt/charter traceability requires artifact IDs for load-bearing external sources.
  - jump directly to `prompt-13`.
  - rejected because `prompt-13` should inherit a stable claim-evidence base from this packet.

Rationale: a claim-traceable literature base reduces paper/verification drift and keeps research decisions auditable.

## 2026-02-06: Pytest Marker Taxonomy + Gating

- Decision: Standardize test selection via markers and explicit opt-in flags.
- Markers:
  - `integration`: offline integration tests (SQLite/filesystem), no live network.
  - `e2e`: end-to-end tests (offline, minimal mocks).
  - `live`: real network/browser tests, always opt-in.
  - `network`: hits the network.
  - `slow`: long-running tests.
- Gating:
  - Default `pytest` run skips `integration`, `e2e`, and `live` unless explicitly enabled.
  - Enable via CLI flags: `--run-integration`, `--run-e2e`, `--run-live` or env vars `RUN_INTEGRATION=1`, `RUN_E2E=1`, `RUN_LIVE=1`.

Rationale: keep the default suite deterministic and fast; make boundary tests explicit and easy to run.

## 2026-02-06: Mitigate Third-Party Pytest Plugin Interference

- Decision: Prefer a repo-controlled test environment and keep tests robust against extra pytest plugins being present.
- Mechanism:
  - Primary: run tests via the project venv (`venv/bin/python -m pytest`), as documented in `docs/manifest/10_testing.md`.
  - Best-effort hardening:
    - `pytest.ini` includes `addopts` entries intended to disable the LangSmith pytest plugin.
    - `sitecustomize.py` exists as an optional hook to set `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, but note: in this Python 3.12 environment `sitecustomize.py` is not auto-imported at interpreter startup (so this hook may not take effect).
  - If plugin autoload becomes a real problem in some environment, prefer explicitly setting `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` in that environment and then enabling only the needed plugins.

Rationale: ensure repository tests run in a stable, repo-controlled environment.

## 2026-02-06: Make `src` Import-Safe via Lazy Exports

- Decision: avoid importing heavy/optional runtime dependencies (notably Prefect) at `import src` time.
- Mechanism:
  - `src/__init__.py` exports `PipelineAPI` lazily via `__getattr__`.

Rationale: tests and submodules should be importable without pulling in orchestration dependencies.

## 2026-02-08: Canonical Architecture Source and Coherence Gate

- Decision: set `docs/manifest/01_architecture.md` as the canonical architecture control document, with `docs/manifest/04_api_contracts.md` and `docs/manifest/05_data_model.md` as required companion artifacts.
- Context:
  - repo had architecture narrative docs but no manifest-level C4/coherence gate files required by the prompt system.
  - prompt router repeatedly selected architecture packet due missing artifacts.
- Mechanism:
  - added architecture baseline with C4 context/containers/components, runtime scenarios, deployment/trust boundaries, and risk inventory.
  - added contract and data-model manifests linked to real repo paths.
  - added coherence checklist/report with explicit `GO_WITH_RISKS` verdict.
- Alternatives considered:
  - keep architecture only in `docs/explanation/system_overview.md` and skip manifest files.
  - rejected because it does not satisfy prompt-system coherence checks and weakens routing/gating consistency.

Rationale: architecture decisions need a single canonical, checkable surface that matches prompt-pack gates.
