# Property Scanner Docs

Property Scanner is a local-first property intelligence system for crawling listings, enriching market context, and producing valuation outputs through a shared CLI/API/dashboard workflow. These docs are for new users, power users, and contributors who need runnable commands and clear output interpretation.

Quick Links: [Getting started](./getting_started/quickstart.md) | [Tutorials](./tutorials/README.md) | [How-to](./how_to/run_end_to_end.md) | [Reference](./reference/cli.md) | [Troubleshooting](./troubleshooting.md)

## Navigation

- Getting started
  - [Installation](./getting_started/installation.md)
  - [Quickstart](./getting_started/quickstart.md)
- Tutorials
  - [End-to-end Tutorial](./tutorials/README.md)
- How-to
  - [Configuration](./how_to/configuration.md)
  - [Run End-to-End](./how_to/run_end_to_end.md)
  - [Interpret Outputs](./how_to/interpret_outputs.md)
  - [Upgrade Notes Template](./how_to/upgrade_notes_template.md)
- Reference
  - [CLI Reference](./reference/cli.md)
  - [Configuration Reference](./reference/configuration.md)
  - [Data Formats](./reference/data_formats.md)
  - [Versioning Policy](./reference/versioning_policy.md)
  - [Release Workflow](./reference/release_workflow.md)
- Explanation
  - [Architecture Overview](./explanation/architecture.md)
  - [System Overview](./explanation/system_overview.md)
  - [Data And Training Pipeline](./explanation/data_pipeline.md)
  - [Unified Scraping Architecture](./explanation/scraping_architecture.md)
  - [Services Map](./explanation/services_map.md)
  - [Agent System And Workflow](./explanation/agent_system.md)
  - [Model Architecture](./explanation/model_architecture.md)
  - [Path To Production](./explanation/production_path.md)
  - [Design Decisions](./explanation/design_decisions.md)
- Project operations
  - [Troubleshooting](./troubleshooting.md)
  - [Glossary](./glossary.md)
  - [Changelog](../CHANGELOG.md)

## Engineering Docs

These are implementation/control docs and should be linked, not duplicated.

- Manifest (what/why)
  - [Core Objective](./manifest/00_overview.md)
  - [Architecture](./manifest/01_architecture.md)
  - [API Contracts](./manifest/04_api_contracts.md)
  - [Data Model](./manifest/05_data_model.md)
  - [Security](./manifest/06_security.md)
  - [Observability](./manifest/07_observability.md)
  - [Runbook / Command Map](./manifest/09_runbook.md)
  - [Testing](./manifest/10_testing.md)
  - [CI](./manifest/11_ci.md)
  - [Conventions](./manifest/12_conventions.md)
- Implementation (how/when)
  - [Status](./implementation/00_status.md)
  - [Worklog](./implementation/03_worklog.md)
  - [Milestones](./implementation/checklists/02_milestones.md)
  - [Release Readiness Checklist](./implementation/checklists/06_release_readiness.md)

## Where To Look Next

- New users: start with [Installation](./getting_started/installation.md), then [Quickstart](./getting_started/quickstart.md), then [Interpret Outputs](./how_to/interpret_outputs.md).
- Power users: use [Run End-to-End](./how_to/run_end_to_end.md), [CLI Reference](./reference/cli.md), and [Configuration Reference](./reference/configuration.md).
- Contributors: review [Conventions](./manifest/12_conventions.md), [Milestones](./implementation/checklists/02_milestones.md), [CI](./manifest/11_ci.md), and [Release Readiness](./implementation/checklists/06_release_readiness.md).

## Not Now

Deferred in this docs bet:
- Full contributor policy page (`CONTRIBUTING.md`) with PR templates and governance details.
- Release tag/publish automation beyond current CI baseline (tracked in [Release Workflow](./reference/release_workflow.md)).
- Expanded source-by-source operational playbooks beyond current crawler status page.

## Remaining Improvements

- Add a dedicated API reference page if external API usage grows beyond current CLI-first workflow.
