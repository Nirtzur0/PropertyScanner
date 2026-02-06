"""Test runner hardening.

This repo's tests run under environments where third-party pytest plugins may be
installed globally and can break collection (e.g., version skew between pytest,
Python, and plugin deps).

We disable pytest plugin auto-loading by default when pytest is being invoked.
Projects that want plugins can still enable them explicitly via env vars.
"""

from __future__ import annotations

import os
import sys


def _looks_like_pytest_invocation(argv0: str) -> bool:
    base = os.path.basename(argv0 or "")
    if base.startswith("pytest"):
        return True
    # "python -m pytest" style
    if base.startswith("python") and any(arg == "pytest" for arg in sys.argv[1:3]):
        return True
    return False


if _looks_like_pytest_invocation(sys.argv[0] if sys.argv else ""):
    os.environ.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
