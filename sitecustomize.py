"""Test runner hardening.

This repo's tests run under environments where third-party pytest plugins may be
installed globally and can break collection (e.g., version skew between pytest,
Python, and plugin deps).

We disable pytest plugin auto-loading by default when pytest is being invoked.
Projects that want plugins can still enable them explicitly via env vars.
"""

from __future__ import annotations

import os

# Pytest plugin auto-loading is the common source of "it works on my machine"
# failures when dev machines have globally-installed pytest plugins (LangSmith,
# etc.) that don't match our dependency pins. Setting this env var is harmless
# for non-pytest processes: pytest is the only consumer.
os.environ.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
