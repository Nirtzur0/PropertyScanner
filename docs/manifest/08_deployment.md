# Deployment

## Deployment Shape (Current)

### Local default (canonical)

- Runtime: local Python process.
- Data stores: local filesystem + SQLite (`data/listings.db`) + LanceDB artifacts.
- Entry commands: see `docs/manifest/09_runbook.md`.

### Containerized (optional)

- Dashboard service is available via `docker compose up --build dashboard`.
- Dashboard exposed on `http://localhost:8505` in compose profile.
- Compose includes optional Postgres profile; default repository behavior remains SQLite-first.

## Environments

- `dev-local`: default and canonical environment for this milestone.
- `dev-container`: optional reproducible container runtime.
- `ci` (planned): offline deterministic test execution + docs guardrails.

## Build/Release Notes

- Release discipline docs are pending (`CHANGELOG.md`, versioning policy, release checklist).
- CI workflow and release mapping are tracked as milestone outcomes in `docs/implementation/checklists/02_milestones.md`.

## Trust and Boundary Notes

- External crawling targets and optional model providers are untrusted boundaries.
- Local DB and artifact directories are trusted operational boundaries for this milestone.

## Deployment Risks

- Drift risk between SQLite default and compose Postgres profile.
- Missing CI/release gates can cause undocumented behavior differences between environments.

## Packet Follow-up

- Add CI environment definition and required checks in next packet.
- Add release workflow mapping once `prompt-11` packet is executed.
