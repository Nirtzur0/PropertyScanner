# Path To Production

This page describes a pragmatic path from a local-first beta to a production-grade data product.

Canonical deployment/release controls:
- `docs/manifest/08_deployment.md`
- `docs/reference/release_workflow.md`
- `docs/implementation/checklists/06_release_readiness.md`

## What Production Means Here

Production is defined by explicit guarantees:
- Reliability: scheduled runs complete, failures are visible, retries are safe.
- Data quality: malformed/empty crawls are blocked before polluting downstream artifacts.
- Predictability: idempotent runs for the same inputs.
- Traceability: outputs can be traced to data slices and model versions.
- Coverage continuity: source-health issues are visible and mitigated.
- Cost control: scrape, inference, and storage costs are measured and bounded.

## Product Spine

- Single orchestration spine: Prefect-backed workflows with explicit step budgets/timeouts.
- Canonical data access via repositories + `StorageService`.
- Shared entrypoint layer through `PipelineAPI` for CLI/agent/dashboard.
- Agent memory persisted in `agent_runs` for replay/audit.
- Approval gates for expensive state-mutating operations.

## Scraping At Scale

Scale requires resilient acquisition and explicit guardrails:
- multi-source coverage with bounded per-source concurrency,
- smart deduplication to avoid redundant fetches,
- anti-bot mitigation strategy with observable fallback behavior,
- optional remote-browser execution as local resource limits are reached.

Key risks:
- anti-bot shifts causing zero-yield runs,
- aggressive fetching policies increasing block risk,
- source-specific parser drift.

Target metrics:
- parse success > 90% on golden checks,
- invalid listing ratio < 2% post-gate,
- no redundant fetches for unchanged assets.

## Data Lifecycle

- idempotent workflows,
- explicit snapshot/event lifecycle choices,
- tombstones for removals,
- lineage metadata for source + parser/normalizer versions.

Decision threshold:
- move from local SQLite default to a networked DB when concurrency/indexing requirements exceed local-first constraints.

## Quality Gates And Observability

- data contracts for required fields/ranges/integrity,
- health telemetry for yield, errors, latency, and freshness,
- drift detection for source HTML and market distributions,
- quality gates that block user-facing output when core checks fail,
- trace-first debugging with per-step timing and errors.

## Model And Label Strategy

- prioritize sold/transaction labels over ask labels,
- keep market-segment calibration explicit,
- evaluate with leak-safe splits and stability metrics,
- registry of model artifacts, metrics, and data slices.

## Inference Service Strategy

- decouple heavy inference from UI when needed,
- expand caching for valuations/embeddings/hot listings,
- keep strict timeouts and explicit failures (no silent fallback paths),
- define migration trigger from local inference to managed/self-hosted compute.

## Security And Operations

- managed secrets for keys and credentials,
- CI quality gates on every merge,
- repeatable containerized runtime,
- role-based protection around destructive operations.

## Staged Roadmap

### Phase 1: Reliability And Coverage

- stabilize source quality and crawler reliability,
- enforce data contracts and freshness gates,
- keep daily update flows operator-friendly.

### Phase 2: Scale And Observability

- remote browser execution,
- proxy/fallback strategy hardening,
- dashboarded source health and anomaly metrics.

### Phase 3: Productization

- stronger model registry discipline,
- dedicated inference surface where needed,
- user-facing controls and release hardening.

## Recommended Next Actions

1. Keep source support/fallback status visible in runtime outputs and dashboard surfaces.
2. Add source-specific data-contract checks for newly enabled portals.
3. Formalize operational SLOs per workflow and enforce through CI/report gates.
