# Release Workflow Mapping

This page maps local release actions to CI workflow behavior.

## Current CI State

- Workflow: `.github/workflows/ci.yml`
- Jobs:
  - `docs-sync-guardrail`
  - `offline-quality-gates`

CI currently validates quality gates but does not publish tags/releases automatically.

## Local -> CI Mapping

| Local release action | Required artifact/change | CI mapping |
| --- | --- | --- |
| Update changelog | `CHANGELOG.md` | validated indirectly by docs-sync guardrail when runtime/test/CI changed |
| Confirm versioning policy | `docs/reference/versioning_policy.md` | checked through docs-sync policy and review checklist |
| Run release readiness checklist | `docs/implementation/checklists/06_release_readiness.md` | checklist governs local sign-off before tag |
| Validate command-map integrity | `python3 scripts/check_command_map.py` | `docs-sync-guardrail` runs equivalent check |
| Validate offline reliability | `python3 -m pytest --run-integration --run-e2e -m "not live"` | `offline-quality-gates` job |

## Tag/Publish Status

- Automated tag/release publishing is **not configured yet**.
- TODO (P1): add a tag-triggered workflow that packages release metadata and publishes notes.

## Minimum Manual Release Steps

1. Complete all items in `docs/implementation/checklists/06_release_readiness.md`.
2. Ensure CI is green on target commit.
3. Create and push tag.
4. Publish release notes using `CHANGELOG.md` and upgrade notes template.
