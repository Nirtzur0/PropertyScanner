import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "check_artifact_feature_contract.py"


def _write_contract_files(tmp_path: Path, *, missing_status_for: str | None = None) -> dict[str, Path]:
    artifacts_index = tmp_path / "index.json"
    alignment_report = tmp_path / "artifact_feature_alignment.md"
    alignment_checklist = tmp_path / "08_artifact_feature_alignment.md"
    milestones = tmp_path / "02_milestones.md"
    improvement_bets = tmp_path / "03_improvement_bets.md"

    artifacts_index.write_text(
        json.dumps(
            {
                "version": 1,
                "artifacts": [
                    {"id": "lit-a", "kind": "paper"},
                    {"id": "lit-b", "kind": "paper"},
                ],
            }
        ),
        encoding="utf-8",
    )

    matrix_rows = [
        "| `lit-a` | implication | coverage | Supported | `src/a.py` |",
        "| `lit-b` | implication | coverage | Partial | `src/b.py` |",
    ]
    if missing_status_for == "lit-b":
        matrix_rows[-1] = "| `lit-b` | implication | coverage | no-status-here | `src/b.py` |"

    alignment_report.write_text(
        "\n".join(
            [
                "# Artifact-Feature Alignment Report",
                "",
                "## Artifact-to-Feature Matrix",
                "",
                "| Artifact ID | Expected implication | Current feature/test coverage | Status (Supported/Partial/Missing/Misaligned) | Evidence paths |",
                "| --- | --- | --- | --- | --- |",
                *matrix_rows,
                "",
            ]
        ),
        encoding="utf-8",
    )

    alignment_checklist.write_text(
        "\n".join(
            [
                "# Checklist",
                "- [ ] O-01: Add artifact-feature mapping contract check.",
                "  - Acceptance signal: docs-check fails when load-bearing artifact IDs are not mapped to feature/test outcomes.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    milestones.write_text(
        "\n".join(
            [
                "# Milestones",
                "- [ ] IB-03: Benchmark and artifact-contract outcomes are converted into checkable gates.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    improvement_bets.write_text(
        "\n".join(
            [
                "# Improvement Bets",
                "- [ ] IB-05: Artifact-feature mapping contract is enforced by docs/CI checks.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return {
        "artifacts_index": artifacts_index,
        "alignment_report": alignment_report,
        "alignment_checklist": alignment_checklist,
        "milestones": milestones,
        "improvement_bets": improvement_bets,
    }


def _run_script(paths: dict[str, Path]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--artifacts-index",
            str(paths["artifacts_index"]),
            "--alignment-report",
            str(paths["alignment_report"]),
            "--alignment-checklist",
            str(paths["alignment_checklist"]),
            "--milestones",
            str(paths["milestones"]),
            "--improvement-bets",
            str(paths["improvement_bets"]),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_contract_script_passes_for_valid_mapping(tmp_path: Path) -> None:
    paths = _write_contract_files(tmp_path)
    result = _run_script(paths)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Artifact-feature contract check passed." in result.stdout


def test_contract_script_fails_when_status_mapping_missing(tmp_path: Path) -> None:
    paths = _write_contract_files(tmp_path, missing_status_for="lit-b")
    result = _run_script(paths)
    assert result.returncode == 1
    assert "missing_status_mapping_rows_in_alignment_report:lit-b" in result.stderr
