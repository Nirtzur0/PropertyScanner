from __future__ import annotations

import os
import subprocess
import sys


def test_http_app_import__avoids_futurewarning_heavy_ml_startup() -> None:
    env = dict(os.environ)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONWARNINGS"] = "error::FutureWarning"

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import src.adapters.http.app; print('ok')",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
