# Path to production: from research MVP to resilient product
(Last Updated: 2026-01-19)

This document lays out a pragmatic path from today's local-first beta to a production-grade data product. It is intentionally critical: each section calls out decision points, risks, and success criteria before implementation.

## 0) What "production" means here
Production is not just uptime. It is a set of guarantees we commit to:
- Reliability: scheduled runs complete, failures are visible, retries are safe.
- Data quality: malformed or empty crawls are blocked before they pollute downstream artifacts.
- Predictability: identical inputs yield identical outputs (idempotent runs).
- Traceability: every model output can be traced to its data inputs and model version.
- Yield: The system prioritizes data acquisition, utilizing aggressive strategies (SSL bypass, ignored robots.txt) when necessary to maintain coverage.
- Cost control: scrape, inference, and storage costs are measured and bounded.

## 1) Product spine: one orchestration and data surface
The product story is weaker without a single, explicit system spine.
- Single orchestration stack: agentic runs already use a plan-executor; batch workflows now run as Prefect flows (`src/platform/workflows/prefect_orchestration.py`). Continue converging on a single run plan, shared budgets, and explicit timeouts.
- Canonical data access: prohibit raw SQL in services; data access lives behind repository classes with a stable API.
- Clean library surface: `PipelineAPI` exposes crawl/index/market/valuation for CLI, agent, and dashboard; keep it as the single surface.
- Agent memory: every run is stored in `agent_runs` (query, areas, plan, status, top picks) for auditability and replay.
- Approval gates: plans that include preflight, index rebuilds, or training require explicit user approval in the dashboard.

Decision points:
- Prefect is the chosen orchestrator; decide when to shift from in-process runs to Prefect deployments + schedules.

## 2) Scraping: High-Yield & Aggressive (Current Status: ACTIVE)
Scale comes from resilience and discipline, not only from volume.
- Multi-Source Coverage: 10+ sources (UK, EU, US) are supported; unified crawl runs sources sequentially while Pydoll handles per-source tab concurrency.
- Smart Deduplication: Pre-fetch deduplication (`SeenUrlStore`) is implemented to skip network requests for known assets, significantly reducing runtime.
- Aggressive Compliance: To ensure data yield, the system currently:
    - Bypasses SSL certificate verification for `robots.txt` fetches.
    - Disables robots checks (explicitly skipped in `ComplianceManager`).
    - Risk: This increases the probability of IP bans. Rotation strategies (proxies) are the next mitigation step.
- Architecture: `UnifiedCrawlRunner` runs sources sequentially; within each source, Pydoll’s `BrowserEngine.fetch_many` enforces concurrency via `max_concurrency`.
- Next Step (Scale): Offload browser execution to remote Pydoll clusters (Docker/remote_ws) to free up local resources.

Risks:
- Anti-bot shifts leading to zero-yield runs (Cloudflare challenges).
- IP bans due to aggressive scraping requires implementing rotating proxies (e.g. BrightData/Oxylabs).

Success metrics:
- Parse success rate > 90% for golden queries.
- Less than 2% invalid listings per crawl after gating.
- Speed: Zero redundant network requests for existing listings.

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
- Agent quality gates: block reporting when evaluations are empty, score bounds are invalid, or quantiles are inconsistent.
- Execution trace: persist per-step timing, status, and error surfaces to diagnose the first failure, not mask it.

Success metrics:
- Automatic alerting on crawl anomalies within one run.
- Freshness dashboards for indices and embeddings.

## 5) Model and label strategy
The system's predictive power hinges on label quality and market alignment.
- Ground truth: prioritize sold/transaction data; treat ask prices as weak labels.
- Market-specific calibration: separate models or calibration layers by city/region and listing type (sale vs rent).
- Evaluation: time+geo splits are available; expand to stability and directional accuracy metrics.
- Model registry: version artifacts, metrics, and data slices for each training run.
- Strategy personas: scoring weights are tied to explicit personas (balanced, cash-flow, bargain, safe-bet).

Risk:
- Unstable targets or label leakage causing regression in live predictions.

## 6) Inference as a service
Valuation becomes a product feature only if it scales reliably.
- Separate inference: expose a model API (FastAPI + Triton or vLLM) to decouple heavy compute from UI.
- Caching: cached valuations already exist; extend caching for embeddings and hot listings.
- Vector search: LanceDB is the single embedded vector store for comps (metadata + embeddings kept together).
- Guardrails: hard timeouts and explicit failure surfaces (no silent fallback valuation paths).

Decision point:
- When to offload from local inference to managed or self-hosted GPU.

## 7) Security and operations
The production posture must be professional.
- Secrets management: move API keys and credentials to a secrets manager.
- CI/CD: run unit, integration, and data-contract tests on every commit.
- Containerization: run all services with pinned dependencies and repeatable images.
- Role-based access: limit destructive operations to authorized roles.

## 8) A staged roadmap

### Phase 1: Reliability & Wide Coverage (Current)
- [x] **Universal Scrape:** 10+ sources supported; sequential crawl with per-source concurrency.
- [x] **Blocking Resolution:** SSL errors handled; robots checks intentionally disabled.
- [x] **Deduplication:** Smart filter for 0-fetch updates.
- [ ] **Data Contracts:** rigorous validation of fields per source.
- [ ] **Goals:** reliable daily updates without manual intervention.

### Phase 2: Scale and Observability (Next)
- [ ] **Remote Browsers:** Switch Pydoll to use remote Docker containers to offload RAM.
- [ ] **Proxy Integration:** Add rotating proxies to `sources.yaml` configs.
- [ ] **Monitoring:** Dashboards for "Yield per Source" and "Banned IPs".

### Phase 3: Productization
- [ ] **Model Registry:** Automated retraining pipelines.
- [ ] **Inference Service:** Decoupled API for valuation.
- [ ] **Dynamic UI:** User-driven source selection and reporting.

## 9) Open questions resolved
- **Which sources?** ALL available sources are now non-negotiable and enabled.
- **Compliance?** We have adopted a "Data First" posture, accepting the risk of IP blocks in exchange for coverage.
- **Performance?** Solved via efficient deduplication (don't re-download) and per-source browser concurrency.

## 10) Recommended next actions
- **Run the full scrape** to validate Pydoll concurrency settings per source.
- Monitor RAM usage during higher `browser_max_concurrency` runs; if high, deploy Pydoll remote server (Phase 2).
- Draft a data-contract spec for each newly enabled source (Realtor, SeLoger, etc.) to ensure data quality.
