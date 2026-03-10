# Changelog

All notable changes to this project are documented in this file.

This format follows Keep a Changelog principles and uses Semantic Versioning policy from `docs/reference/versioning_policy.md`.

## [Unreleased]

### Added
- Diataxis documentation set for onboarding, how-to guidance, reference pages, and troubleshooting.
- Release discipline artifacts:
  - `docs/reference/versioning_policy.md`
  - `docs/reference/release_workflow.md`
  - `docs/implementation/checklists/06_release_readiness.md`
  - `docs/how_to/upgrade_notes_template.md`
- CI release/docs mapping references in `docs/manifest/11_ci.md`.

### Changed
- `docs/INDEX.md` now serves as the canonical docs navigation page with Quick Links and release guidance.

## [0.1.0] - 2026-02-08

### Added
- Initial local-first property scanner implementation (crawl, enrichment, market/index/train/backfill, dashboard/CLI/API).
- Architecture, contracts, data model, testing, observability, runbook, and CI baseline manifests under `docs/manifest/`.
- Implementation tracking and milestone checklists under `docs/implementation/`.
