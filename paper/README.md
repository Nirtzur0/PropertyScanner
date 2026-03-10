# Paper: PropertyScanner Valuation

This directory contains the reproducible paper and verification harness.

## Build the paper (LaTeX)

Command (repo-sourced):
- `python3 scripts/build_paper.py`

Source: `scripts/build_paper.py`

Prereqs:
- `pdflatex` and `bibtex` available on PATH.

If LaTeX tooling is missing, the script will exit with a clear error. The
verification tests and artifacts can still be run without building the PDF.

## Run verification tests

Commands (repo-sourced via CI pytest usage):
- `python3 -m pytest -m "not integration and not e2e and not live" tests/unit/paper`
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -m "not integration and not e2e and not live" tests/unit/paper` (fallback when local third-party pytest entrypoint plugins interfere)

Source: `.github/workflows/ci.yml` (pytest usage patterns).

## Generate the sanity artifact

Command (repo-sourced):
- `python3 scripts/paper_generate_sanity_artifact.py`

Source: `scripts/paper_generate_sanity_artifact.py`

Artifacts:
- `paper/artifacts/sanity_case.json`

## Expected outputs
- `paper/main.pdf` (if LaTeX tools are available)
- `paper/artifacts/sanity_case.json`

## Determinism notes
- Tests use fixed data and deterministic calculations.
- No external network is required.
