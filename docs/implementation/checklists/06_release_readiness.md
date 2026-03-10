# Release Readiness Checklist

- [ ] RR-01: Version bump policy is applied and release version is selected.
  - AC: release version is consistent with `docs/reference/versioning_policy.md` and `pyproject.toml`.
  - Verify: `rg -n "^version\s*=\s*\"" pyproject.toml && rg -n "Semantic Versioning|Pre-1.0" docs/reference/versioning_policy.md`
  - Files: `pyproject.toml`
  - Docs: `docs/reference/versioning_policy.md`
  - Alternatives: N/A

- [ ] RR-02: Changelog is updated for the release.
  - AC: `CHANGELOG.md` includes release date/version and notable changes.
  - Verify: `rg -n "\[Unreleased\]|\[0\.1\.0\]|Added|Changed|Fixed|Deprecated" CHANGELOG.md`
  - Files: `CHANGELOG.md`
  - Docs: `CHANGELOG.md`
  - Alternatives: release notes only in VCS UI (rejected)

- [ ] RR-03: Upgrade notes are prepared.
  - AC: upgrade notes template is completed for the target release.
  - Verify: `test -f docs/how_to/upgrade_notes_template.md`
  - Files: `docs/how_to/upgrade_notes_template.md`
  - Docs: `docs/how_to/upgrade_notes_template.md`
  - Alternatives: ad-hoc release comments (rejected)

- [ ] RR-04: CI required checks are green on release candidate commit.
  - AC: `docs-sync-guardrail` and `offline-quality-gates` jobs pass.
  - Verify: `python3 scripts/check_command_map.py && python3 -m pytest --run-integration --run-e2e -m "not live"`
  - Files: `.github/workflows/ci.yml`
  - Docs: `docs/manifest/11_ci.md`, `docs/reference/release_workflow.md`
  - Alternatives: local-only confidence (rejected)

- [ ] RR-05: Command map and CI mapping are consistent.
  - AC: all `CMD-*` references in CI docs exist in runbook.
  - Verify: `python3 scripts/check_command_map.py`
  - Files: `docs/manifest/09_runbook.md`, `docs/manifest/11_ci.md`, `scripts/check_command_map.py`
  - Docs: `docs/reference/release_workflow.md`
  - Alternatives: duplicated command tables (rejected)

- [ ] RR-06: Release workflow mapping is up to date.
  - AC: release workflow page reflects current CI behavior and known TODOs.
  - Verify: `rg -n "ci.yml|docs-sync-guardrail|offline-quality-gates|tag|TODO" docs/reference/release_workflow.md`
  - Files: `docs/reference/release_workflow.md`
  - Docs: `docs/reference/release_workflow.md`
  - Alternatives: undocumented release process (rejected)
