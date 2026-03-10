# Product Requirements Document (PRD)

## Problem statement

Property Scanner has strong pipeline capabilities, but project intent, acceptance criteria, and repo-level objective are not yet codified in a single testable planning surface. This creates planning drift risk across crawling, market data, valuation, and dashboard workflows.

This PRD defines a measurable objective and acceptance criteria to guide implementation and stabilization in a docs-first way.

## Users and jobs-to-be-done

- Solo investor:
  - Discover candidate properties quickly.
  - Compare estimated value vs asking price with interpretable evidence.
- Analyst/researcher:
  - Re-run workflows with reproducible artifacts and inspect assumptions.
  - Validate that model/data updates improve outcomes rather than regress.
- Maintainer/contributor:
  - Add/modify pipeline components safely.
  - Verify changes with deterministic tests and documented commands.

## In-scope workflows

- Local setup and quickstart to dashboard.
- Preflight orchestration for freshness-based pipeline runs.
- Crawl/normalize/enrich listing ingestion.
- Market/transactions/index/model/backfill/calibration workflows.
- CLI/API/dashboard access over shared underlying services.
- Offline test gating and verification commands.
- Documentation synchronization for objective, requirements, and acceptance checks.

## Out-of-scope / non-goals

- Hosted SaaS/multi-tenant deployment.
- Mandatory live crawler reliability across anti-bot-protected portals.
- Automated transaction execution or financial/legal guarantees.
- Broad UI redesign beyond current dashboard behavior.

## Success metrics

- Setup-to-dashboard first run <= 30 minutes following documented commands.
- Offline suites pass consistently:
  - Unit default suite green.
  - Integration suite green when enabled.
  - E2E suite green when enabled.
- End-to-end local happy path (preflight -> dashboard inspection) completes without manual DB repair steps.
- Core artifacts (`data/listings.db`, vector index, model outputs) are produced and discoverable via docs.
- Acceptance checklist (`docs/implementation/checklists/01_plan.md`) remains actionable and verifiable.

## Requirements (functional + non-functional)

### Functional requirements

- FR-01: The system must expose a clear objective, target users, and journeys in `docs/manifest/00_overview.md`.
- FR-02: The CLI must support documented commands for preflight, crawl, market-data, index, train, backfill, and dashboard paths.
- FR-03: Dashboard, CLI, and API must remain coherent entrypoints to the same pipeline behavior.
- FR-04: The pipeline must persist run-critical artifacts (DB/index/model outputs) in documented default paths.
- FR-05: Acceptance criteria must map requirements to verification commands and expected file surfaces.

### Non-functional requirements

- NFR-01: Default development/test workflow must remain deterministic and offline-first.
- NFR-02: Docs must remain truthful to implemented behavior (no undocumented breaking changes).
- NFR-03: Runtime reliability must favor safe failure over silent partial success.
- NFR-04: Repo should stay single-machine operable with bounded setup complexity.
- NFR-05: Assumptions and known gaps must be explicit rather than implied.

## Risks and assumptions

### Risks

- R-01: Source anti-bot changes can break crawl reliability unpredictably.
- R-02: LLM/VLM dependencies can introduce non-determinism and optional-path breakage.
- R-03: Missing CI wiring may allow regressions to land unnoticed.
- R-04: Docs drift can cause false confidence in pipeline health.

### Assumptions

- A-01: Core local workflows (CLI + dashboard + API) remain the primary operating mode.
- A-02: SQLite continues as primary system of record in current horizon.
- A-03: Live/network tests remain opt-in and not required for default validation.
- A-04: Existing docs/commands are generally accurate and can be incrementally normalized.

## Acceptance criteria mapping

- AC-01 -> FR-01, NFR-02: Objective and non-goals defined in overview doc.
- AC-02 -> FR-02, FR-03: Command map covers critical user journeys and is runnable.
- AC-03 -> FR-04, NFR-03: Artifact lifecycle and invariants are explicit and preserved.
- AC-04 -> FR-05, NFR-05: Checklist criteria are testable with concrete verification methods.
- AC-05 -> NFR-01: Offline test suites remain green with documented commands.
- AC-06 -> NFR-02: Docs index and manifest references are consistent with produced files.
- AC-07 -> NFR-04: Local setup remains bounded and reproducible.
- AC-08 -> NFR-05: Open assumptions and gaps are explicitly listed for follow-up.

## Open questions / TODOs

- Should CI be introduced now (GitHub Actions) or deferred to a dedicated release hardening packet?
- Which minimal observability baseline is required for "release-ready" in this repo?
- Do we want stricter artifact schema validation (e.g., contracts for valuation outputs)?
- Should live crawler validation be formalized as scheduled diagnostics outside default tests?
