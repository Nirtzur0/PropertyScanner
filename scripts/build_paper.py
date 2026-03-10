#!/usr/bin/env python3
"""Build the paper PDF with pdflatex + bibtex if available."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PAPER_DIR = ROOT / "paper"
MAIN = PAPER_DIR / "main.tex"


def _require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"missing_tool:{name}")


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=str(PAPER_DIR), check=True)


def main() -> int:
    if not MAIN.exists():
        print("missing main.tex", file=sys.stderr)
        return 2

    try:
        _require_tool("pdflatex")
        _require_tool("bibtex")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        print("Install LaTeX tooling (pdflatex + bibtex) to build the PDF.")
        return 3

    _run(["pdflatex", "-interaction=nonstopmode", "main.tex"])
    _run(["bibtex", "main"])
    _run(["pdflatex", "-interaction=nonstopmode", "main.tex"])
    _run(["pdflatex", "-interaction=nonstopmode", "main.tex"])
    print("Built paper/main.pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
