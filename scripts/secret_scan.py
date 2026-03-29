#!/usr/bin/env python3
"""Lightweight secret scanner for CI.

Scans source files for patterns that suggest hardcoded secrets.
Exit code 1 if any potential secrets are found.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PATTERNS = [
    (r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]", "hardcoded_api_key"),
    (r"sk-[A-Za-z0-9]{20,}", "openai_key"),
    (r"ghp_[A-Za-z0-9]{36}", "github_pat"),
    (r"(?i)password\s*[:=]\s*['\"][^'\"]{8,}['\"]", "hardcoded_password"),
    (r"AKIA[0-9A-Z]{16}", "aws_access_key"),
]

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", "dist", "build", "third_party",
}

EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".yaml", ".yml", ".toml", ".json", ".env"}


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    findings: list[tuple[int, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return findings
    for line_no, line in enumerate(text.splitlines(), start=1):
        for pattern, label in PATTERNS:
            if re.search(pattern, line):
                findings.append((line_no, label, line.strip()[:120]))
    return findings


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    total_findings: list[tuple[str, int, str, str]] = []

    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix not in EXTENSIONS or not path.is_file():
            continue
        for line_no, label, snippet in scan_file(path):
            total_findings.append((str(path.relative_to(root)), line_no, label, snippet))

    if total_findings:
        print(f"Found {len(total_findings)} potential secret(s):")
        for file_path, line_no, label, snippet in total_findings:
            print(f"  {file_path}:{line_no} [{label}] {snippet}")
        return 1

    print("No secrets detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
