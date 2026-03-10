#!/usr/bin/env python3
"""Fail when load-bearing artifacts are no longer mapped to feature/test outcomes."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List

STATUS_TOKENS = ("Supported", "Partial", "Missing", "Misaligned")


def _load_artifact_ids(path: Path) -> List[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("artifact_index_missing_artifacts")

    ids: List[str] = []
    seen = set()
    duplicates = set()
    for idx, item in enumerate(artifacts):
        if not isinstance(item, dict):
            raise ValueError(f"artifact_entry_invalid:{idx}")
        artifact_id = str(item.get("id") or "").strip()
        if not artifact_id:
            raise ValueError(f"artifact_id_missing:{idx}")
        ids.append(artifact_id)
        if artifact_id in seen:
            duplicates.add(artifact_id)
        seen.add(artifact_id)
    if duplicates:
        joined = ",".join(sorted(duplicates))
        raise ValueError(f"artifact_id_duplicate:{joined}")
    return ids


def _extract_status_rows(report_text: str) -> Dict[str, str]:
    rows: Dict[str, str] = {}
    for line in report_text.splitlines():
        if not line.startswith("| "):
            continue
        if "| --- " in line or line.strip().startswith("| ---"):
            continue
        match = re.match(r"\|\s*`([^`]+)`\s*\|", line)
        if not match:
            continue
        if not any(f"| {status} |" in line for status in STATUS_TOKENS):
            continue
        rows[match.group(1)] = line
    return rows


def _check_contract(
    *,
    artifact_ids: List[str],
    alignment_report_text: str,
    alignment_checklist_text: str,
    milestones_text: str,
    improvement_bets_text: str,
) -> List[str]:
    errors: List[str] = []
    checklist_lower = alignment_checklist_text.lower()
    milestones_lower = milestones_text.lower()
    improvement_lower = improvement_bets_text.lower()

    missing_mentions = [aid for aid in artifact_ids if f"`{aid}`" not in alignment_report_text]
    if missing_mentions:
        errors.append(
            "missing_artifact_mentions_in_alignment_report:"
            + ",".join(missing_mentions)
        )

    status_rows = _extract_status_rows(alignment_report_text)
    missing_status_rows = [aid for aid in artifact_ids if aid not in status_rows]
    if missing_status_rows:
        errors.append(
            "missing_status_mapping_rows_in_alignment_report:"
            + ",".join(missing_status_rows)
        )

    checklist_needle = "artifact-feature mapping contract check"
    if "O-01" not in alignment_checklist_text or checklist_needle not in checklist_lower:
        errors.append("alignment_checklist_missing_O-01_contract_entry")

    if "IB-05" not in improvement_bets_text or "artifact-feature mapping contract" not in improvement_lower:
        errors.append("improvement_bets_missing_IB-05_contract_entry")

    if "IB-03" not in milestones_text or "artifact-contract" not in milestones_lower:
        errors.append("milestones_missing_IB-03_artifact_contract_reference")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts-index", default="docs/artifacts/index.json")
    parser.add_argument(
        "--alignment-report",
        default="docs/implementation/reports/artifact_feature_alignment.md",
    )
    parser.add_argument(
        "--alignment-checklist",
        default="docs/implementation/checklists/08_artifact_feature_alignment.md",
    )
    parser.add_argument(
        "--milestones",
        default="docs/implementation/checklists/02_milestones.md",
    )
    parser.add_argument(
        "--improvement-bets",
        default="docs/implementation/checklists/03_improvement_bets.md",
    )
    args = parser.parse_args()

    try:
        artifact_ids = _load_artifact_ids(Path(args.artifacts_index))
    except Exception as exc:
        print(f"[artifact-contract] Failed to load artifacts index: {exc}", file=sys.stderr)
        return 1

    try:
        alignment_report_text = Path(args.alignment_report).read_text(encoding="utf-8")
        alignment_checklist_text = Path(args.alignment_checklist).read_text(encoding="utf-8")
        milestones_text = Path(args.milestones).read_text(encoding="utf-8")
        improvement_bets_text = Path(args.improvement_bets).read_text(encoding="utf-8")
    except Exception as exc:
        print(f"[artifact-contract] Failed to read required docs: {exc}", file=sys.stderr)
        return 1

    errors = _check_contract(
        artifact_ids=artifact_ids,
        alignment_report_text=alignment_report_text,
        alignment_checklist_text=alignment_checklist_text,
        milestones_text=milestones_text,
        improvement_bets_text=improvement_bets_text,
    )
    if errors:
        print("[artifact-contract] Contract failed.", file=sys.stderr)
        for item in errors:
            print(f"[artifact-contract] - {item}", file=sys.stderr)
        return 1

    print("Artifact-feature contract check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
