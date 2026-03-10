#!/usr/bin/env python3
"""Validate paper/implementation_map.md against paper/main.tex and code paths."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PAPER_DIR = ROOT / "paper"
MAP_PATH = PAPER_DIR / "implementation_map.md"
TEX_PATH = PAPER_DIR / "main.tex"

LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
ROW_RE = re.compile(r"^\|\s*`?(?P<paper>[^|]+?)`?\s*\|\s*`?(?P<code>[^|]+?)`?\s*\|\s*`?(?P<find>[^|]+?)`?\s*\|\s*`?(?P<tests>[^|]+?)`?\s*\|\s*(?P<notes>[^|]*)\|\s*$")


def _load_labels() -> set[str]:
    text = TEX_PATH.read_text(encoding="utf-8")
    return {m.group(1).strip() for m in LABEL_RE.finditer(text)}


def _iter_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in MAP_PATH.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        if "---" in line:
            continue
        if "Paper" in line and "Code" in line:
            continue
        m = ROW_RE.match(line)
        if not m:
            continue
        row = {k: v.strip() for k, v in m.groupdict().items()}
        rows.append(row)
    return rows


def _rg_exists(pattern: str, path: Path) -> bool:
    try:
        proc = subprocess.run(
            ["rg", "-n", "-F", pattern, str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        proc = subprocess.run(
            ["grep", "-n", "-F", pattern, str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
    return proc.returncode == 0


def main() -> int:
    if not MAP_PATH.exists():
        print("missing implementation_map.md", file=sys.stderr)
        return 2
    if not TEX_PATH.exists():
        print("missing main.tex", file=sys.stderr)
        return 2

    labels = _load_labels()
    rows = _iter_rows()
    if not rows:
        print("no rows parsed", file=sys.stderr)
        return 2

    ok = True
    for row in rows:
        paper = row["paper"].strip("`")
        if paper.startswith("eq:") or paper.startswith("sec:"):
            alt_label = paper.split(":", 1)[1]
            if paper not in labels and alt_label not in labels:
                print(f"missing_label:{alt_label}")
                ok = False
        code = row["code"].strip("`")
        if code and code != "N/A":
            code_path = (ROOT / code).resolve()
            if not code_path.exists():
                print(f"missing_code_path:{code}")
                ok = False
        find = row["find"].strip("`")
        if find and find != "N/A" and code and code != "N/A":
            code_path = (ROOT / code).resolve()
            if code_path.exists() and not _rg_exists(find, code_path):
                print(f"missing_pattern:{find} in {code}")
                ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
