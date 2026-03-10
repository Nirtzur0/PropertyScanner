#!/usr/bin/env python3
"""Verify CI docs only reference command IDs that exist in the runbook."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def main() -> int:
    runbook_path = Path("docs/manifest/09_runbook.md")
    ci_path = Path("docs/manifest/11_ci.md")

    runbook_text = runbook_path.read_text(encoding="utf-8")
    ci_text = ci_path.read_text(encoding="utf-8")

    runbook_ids = set(re.findall(r"CMD-[A-Z0-9-]+", runbook_text))
    ci_ids = set(re.findall(r"CMD-[A-Z0-9-]+", ci_text))

    missing = sorted(ci_ids - runbook_ids)
    if missing:
        print("Missing command IDs in runbook:", ", ".join(missing))
        return 1

    print("Command map integrity check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
