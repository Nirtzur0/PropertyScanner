# Security

## Security Posture (Current)

- Runtime model: single-developer local-first environment.
- Primary external risk surfaces:
  - third-party portal crawling endpoints
  - optional LLM/VLM provider APIs
  - external official data sources
- Primary internal data surfaces:
  - `data/listings.db`
  - `data/vector_index.lancedb`
  - `data/vector_metadata.json`
  - `models/*`

## Baseline Controls

- Input and data-quality filtering before persistence:
  - `src/listings/services/quality_gate.py`
- Crawl compliance/rate control utilities:
  - `src/platform/utils/compliance.py`
- Workflow run logging for traceability:
  - `src/platform/pipeline/repositories/pipeline_runs.py`
  - `src/agentic/memory.py`

## Secrets and Configuration

- Secrets are expected through environment/config overlays; do not hardcode provider keys.
- Required practice:
  - keep provider credentials out of repository files
  - use local environment variables and secret stores for deployment environments
- Follow-up needed:
  - add explicit secrets-handling runbook section in `docs/manifest/09_runbook.md`

## Boundary Validation Requirements

- CLI/API boundary inputs must stay typed and validated at module boundaries.
- Domain contracts (`CanonicalListing`, `DealAnalysis`, evidence schemas) are the canonical output validity boundary:
  - `src/platform/domain/schema.py`

## Network and Crawl Safety Constraints

- External portals may block automation; reliability is not guaranteed.
- Any change to crawl policy must preserve explicit compliance controls and failure transparency.

## Known Gaps

- Robots policy handling currently includes permissive fallbacks and should be tightened before production-scale operation.
- No automated security scanning workflow is configured in CI yet.

## Security Actions in Current Milestone

- P0-SEC-01: keep crawl compliance controls explicit and documented.
- P1-SEC-02: add CI security checks (dependency audit + secret-scan baseline).
- P1-SEC-03: formalize a secrets handling section in release docs.
