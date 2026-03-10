# Overview

## Core Objective

We are building a local-first property intelligence system for investors/analysts so they can discover opportunities, evaluate listings with reproducible evidence, and make faster buy/hold/skip decisions from one workflow.

### Non-goals

- Provide legal/financial advice or automated investment execution.
- Guarantee live crawling availability across all third-party portals.
- Replace official appraisal/compliance processes.
- Operate as a hosted multi-tenant SaaS in the current milestone.

### Measurable success metrics

- New-user time-to-first-dashboard is <= 30 minutes using documented quickstart.
- Offline default test suites stay green (unit + integration + e2e) on local runs.
- Preflight-to-dashboard happy path completes without manual DB fixes on a fresh workspace.
- Valuation runs persist outputs with provenance (run metadata + artifacts) for auditability.

### Constraints

- Default runtime is local machine execution with SQLite-backed storage.
- Source crawlers are constrained by anti-bot protections and changing portal behavior.
- LLM/VLM paths are optional and must degrade gracefully when disabled/unavailable.
- Cost and complexity should remain bounded by a single-developer-friendly setup.

### Do-not-break invariants

- `data/listings.db` remains the system of record for listings and run metadata.
- Core pipeline commands stay available via `src/interfaces/cli.py`.
- Preflight must remain the canonical entrypoint for freshness-based orchestration.
- Test gating semantics (`integration`, `e2e`, `live` opt-in behavior) must stay explicit.
- Existing docs and command map must stay truthful to actual repo behavior.

### Primary user journeys

1. Setup and first run: clone -> install dependencies -> run dashboard -> inspect outputs.
2. Data refresh: run preflight/crawl path -> ingest updates -> validate run status.
3. Market and index refresh: build market data + vector index -> verify artifacts.
4. Model and valuation workflow: train/backfill/calibrate -> review valuation outputs.
5. Analyst workflow: run agent-assisted query -> inspect candidates and evidence trail.
6. Contributor workflow: run tests -> make scoped change -> verify docs/tests alignment.

## Target Users

- Solo property investor using local tooling for recurring deal analysis.
- Quant/analyst validating valuation hypotheses with explicit data lineage.
- Contributor/maintainer extending sources, workflows, and model behavior safely.

## Key Workflows

- Unified crawl and normalization into canonical listing schema.
- Optional feature fusion (LLM/VLM + sentiment) with fallback-safe behavior.
- Market/official metrics ingest and derived index generation.
- Comp indexing and retrieval for valuation evidence.
- Training + backfill + calibration lifecycle for valuation quality.
- Dashboard/CLI/API access layers over the same pipeline surface.
