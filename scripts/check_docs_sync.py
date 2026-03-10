#!/usr/bin/env python3
"""Enforce docs-sync updates when runtime/test/CI surfaces change."""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Iterable, List, Sequence, Tuple

WATCH_PREFIXES: Tuple[str, ...] = (
    "src/",
    "tests/",
    ".github/workflows/",
    "config/",
)
WATCH_EXACT = {
    "pyproject.toml",
    "requirements.txt",
    "pytest.ini",
}
REQUIRED_DOCS = {
    "docs/implementation/00_status.md",
    "docs/implementation/checklists/02_milestones.md",
}
MANIFEST_DOC_OPTIONS = {
    "docs/manifest/07_observability.md",
    "docs/manifest/09_runbook.md",
    "docs/manifest/10_testing.md",
    "docs/manifest/11_ci.md",
}


def _is_zero_sha(value: str) -> bool:
    value = value.strip()
    return bool(value) and set(value) <= {"0"}


def _run_git(args: Sequence[str]) -> Tuple[int, List[str]]:
    proc = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return proc.returncode, []
    files = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return 0, files


def _resolve_changed_files(base: str, head: str, explicit: Iterable[str]) -> Tuple[List[str], str]:
    provided = [item for item in explicit if item]
    if provided:
        return sorted(set(provided)), "explicit-args"

    candidates: List[Tuple[str, Sequence[str]]] = []
    if base and head and not _is_zero_sha(base):
        candidates.append(("git-diff-triple-dot", ["diff", "--name-only", f"{base}...{head}"]))
        candidates.append(("git-diff-double-dot", ["diff", "--name-only", f"{base}..{head}"]))
    if head:
        candidates.append(("git-show-head-sha", ["show", "--pretty=", "--name-only", head]))
    candidates.append(("git-show-head", ["show", "--pretty=", "--name-only", "HEAD"]))

    for label, args in candidates:
        rc, files = _run_git(args)
        if rc == 0:
            return sorted(set(files)), label

    return [], "none"


def _is_watched_change(path: str) -> bool:
    if path in WATCH_EXACT:
        return True
    return any(path.startswith(prefix) for prefix in WATCH_PREFIXES)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="", help="Base SHA for diff range.")
    parser.add_argument("--head", default="", help="Head SHA for diff range.")
    parser.add_argument(
        "--changed-file",
        action="append",
        default=[],
        help="Explicit changed file path (can be repeated).",
    )
    args = parser.parse_args()

    changed_files, source = _resolve_changed_files(args.base, args.head, args.changed_file)
    if not changed_files:
        print("[docs-sync] No changed files detected; skipping guard.")
        return 0

    print(f"[docs-sync] Changed files source: {source}")
    for item in changed_files:
        print(f"[docs-sync] - {item}")

    watched_changes = sorted(path for path in changed_files if _is_watched_change(path))
    if not watched_changes:
        print("[docs-sync] No runtime/test/CI/config changes detected; guard passes.")
        return 0

    missing_required = sorted(path for path in REQUIRED_DOCS if path not in changed_files)
    has_manifest_update = any(path in changed_files for path in MANIFEST_DOC_OPTIONS)

    if not missing_required and has_manifest_update:
        print("[docs-sync] Guard passed: required docs and manifest updates present.")
        return 0

    print("[docs-sync] Guard failed.", file=sys.stderr)
    print("[docs-sync] Runtime/test/CI/config files changed:", file=sys.stderr)
    for path in watched_changes:
        print(f"  - {path}", file=sys.stderr)

    if missing_required:
        print("[docs-sync] Missing required implementation docs:", file=sys.stderr)
        for path in missing_required:
            print(f"  - {path}", file=sys.stderr)

    if not has_manifest_update:
        print(
            "[docs-sync] Missing manifest update for behavior/command mapping. "
            "Update at least one of:",
            file=sys.stderr,
        )
        for path in sorted(MANIFEST_DOC_OPTIONS):
            print(f"  - {path}", file=sys.stderr)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
