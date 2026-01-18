# Path to production: from research MVP to resilient product

This document lays out a pragmatic path from today's local-first beta to a production-grade data product. It is intentionally critical: each section calls out decision points, risks, and success criteria before implementation.

## 0) What "production" means here
Production is not just uptime. It is a set of guarantees we commit to:
- Reliability: scheduled runs complete, failures are visible, retries are safe.
- Data quality: malformed or empty crawls are blocked before they pollute downstream artifacts.
- Predictability: identical inputs yield identical outputs (idempotent runs).
- Traceability: every model output can be traced to its data inputs and model version.
- Compliance: source usage is respectful of terms, robots, and regional policy.
- Cost control: scrape, inference, and storage costs are measured and bounded.

## 1) Product spine: one orchestration and data surface
The product story is weaker without a single, explicit system spine.
- Single orchestration stack: agentic runs already use a plan-executor; batch workflows still run through preflight. Unify these under one run plan and shared budgets.
- Canonical data access: prohibit raw SQL in services; data access lives behind repository classes with a stable API.
- Clean library surface: `PipelineAPI` already exposes crawl/index/market/valuation for CLI, agent, and dashboard; keep it as the single surface.

Decision points:
- Orchestrator selection (Airflow vs Prefect vs Dagster) based on local-first dev, scheduling complexity, and operational overhead.
- When to split or keep orchestration inside the app (embedded scheduler vs external scheduler).

## 2) Scraping that holds up
Scale comes from resilience and discipline, not only from volume.
- Distributed extraction: containerized agents with queue-based scheduling and backpressure.
- Source contract tests: golden queries and assertions for embedded JSON presence, parse rates, and required fields.
- Canary change detection: structural change alerts before a full run; optional visual regression for JS-heavy pages.
- Adaptive fetch strategy: gradual escalation from HTTP to headless rendering when needed, with rate limits and conservative retries.
- Compliance guardrails: honor robots and terms; avoid bypass or circumvention logic.

Risks:
- Anti-bot shifts leading to zero-yield runs.
- Scraping costs growing faster than value (proxy, headless compute).

Success metrics:
- Parse success rate > 90% for golden queries.
- Less than 2% invalid listings per crawl after gating.

## 3) Data lifecycle: idempotency, history, and truth
Training and analytics are only as good as the data lifecycle model.
- Idempotent runs: every run and backfill is safe to repeat without data duplication.
- Snapshot vs event data: choose a truth model (daily snapshots vs event history vs both) and enforce it across storage and analytics.
- Tombstones for removals: disappearing listings are data, not silent drops.
- Lineage and provenance: store source URL, crawl timestamp, parser version, and normalizer version for every record.

Decision points:
- Whether to move from local SQLite to a production-grade database (PostgreSQL) when concurrency and indexing become limiting.
- When to introduce a data warehouse or lake for long-term history.

## 4) Quality gates and observability
Production trust is earned by early detection.
- Data contracts: validation checks for required fields, price ranges, and location integrity.
- Health telemetry: metrics on yield, parse error rates, VLM latency, inference queue times, and index freshness.
- Drift detection: monitor changes in distributions (price, area, listing count) and source HTML structure.

Success metrics:
- Automatic alerting on crawl anomalies within one run.
- Freshness dashboards for indices and embeddings.

## 5) Model and label strategy
The system's predictive power hinges on label quality and market alignment.
- Ground truth: prioritize sold/transaction data; treat ask prices as weak labels.
- Market-specific calibration: separate models or calibration layers by city/region and listing type (sale vs rent).
- Evaluation: time+geo splits are available; expand to stability and directional accuracy metrics.
- Model registry: version artifacts, metrics, and data slices for each training run.

Risk:
- Unstable targets or label leakage causing regression in live predictions.

## 6) Inference as a service
Valuation becomes a product feature only if it scales reliably.
- Separate inference: expose a model API (FastAPI + Triton or vLLM) to decouple heavy compute from UI.
- Caching: cached valuations already exist; extend caching for embeddings and hot listings.
- Guardrails: hard timeouts and fallback paths to baseline comp valuation.

Decision point:
- When to offload from local inference to managed or self-hosted GPU.

## 7) Security and operations
The production posture must be professional.
- Secrets management: move API keys and credentials to a secrets manager.
- CI/CD: run unit, integration, and data-contract tests on every commit.
- Containerization: run all services with pinned dependencies and repeatable images.
- Role-based access: limit destructive operations to authorized roles.

## 8) A staged roadmap
A staged plan prevents premature scaling.

Phase 1: Reliability Baseline
- Goals: idempotent runs, data contracts, unified data access, single orchestration plan.
- Exit criteria: no silent data failures for two weeks; reproducible valuations.

Phase 2: Scale and Observability
- Goals: distributed crawling, contract tests, monitoring dashboards, canary detection.
- Exit criteria: stable yield under variable source changes; alerting within minutes.

Phase 3: Productization
- Goals: model registry, inference service, API-first architecture, automated retraining.
- Exit criteria: stable model performance, low latency valuation, predictable costs.

## 9) Open questions to resolve
- Which sources are non-negotiable for accuracy, and which are optional?
- What freshness guarantees does the dashboard need (daily, hourly, on-demand)?
- What minimum dataset size yields reliable area intelligence signals?
- Which compliance constraints apply for UK/IT sources, and who owns that risk?

## 10) Recommended next actions (planning only)
- Define the truth model (snapshot vs event) and document it.
- Choose the orchestration platform and define minimal run DAGs.
- Draft a data-contract spec for each source with golden fixtures.
- Establish evaluation baselines for valuation and rent estimation.
