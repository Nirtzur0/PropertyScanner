# Glossary

- **Artifact**: a persisted output from workflows (DB rows, vector index, model files, metadata).
- **Backfill**: workflow that computes/persists missing or stale valuation outputs.
- **Canonical Listing**: normalized listing object used across services (`CanonicalListing`).
- **Comp**: comparable property used for valuation evidence.
- **Confidence**: model uncertainty representation, not a guarantee.
- **Crawl source**: external portal/provider configured in `config/sources.yaml`.
- **Docs-sync guardrail**: CI check that enforces doc updates when runtime/test/CI/config changes.
- **Evidence Pack**: structured valuation support payload (`EvidencePack`).
- **Hydra composition**: layered config assembly from `config/app.yaml` defaults.
- **Preflight**: canonical freshness orchestration flow for deciding which pipeline steps to run.
- **Runbook Command ID**: stable `CMD-*` identifier in `docs/manifest/09_runbook.md` used by CI/docs.
- **SLI/SLO**: service level indicator/objective definitions in observability docs.
- **VLM**: vision-language model enrichment path for image-derived listing context.
