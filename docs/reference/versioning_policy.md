# Versioning Policy

## Scheme

Project versions follow Semantic Versioning (`MAJOR.MINOR.PATCH`).

Current declared version in `pyproject.toml`: `0.1.0`.

## Compatibility Rules

- `PATCH`: bug fixes and non-breaking docs/config clarifications.
- `MINOR`: backward-compatible feature additions and new optional workflows.
- `MAJOR`: breaking CLI/config/data-contract changes.

## Pre-1.0 Rules

While major version is `0`, minor releases may include breaking changes when necessary.

When a breaking change is introduced in pre-1.0:
- document it in `CHANGELOG.md`
- add explicit migration steps using `docs/how_to/upgrade_notes_template.md`
- update release readiness checklist before tagging

## Deprecation Policy

- New deprecations must be documented in `CHANGELOG.md` under `Deprecated`.
- Remove deprecated behavior only after at least one published release cycle with migration notes.

## Migration Policy

Any breaking change touching CLI/config/data formats must include:
- before/after behavior description
- exact migration steps
- rollback path
- validation commands

## Version Bump Ownership

Maintainer-owned by default, executed during release packet completion in `docs/implementation/checklists/06_release_readiness.md`.
