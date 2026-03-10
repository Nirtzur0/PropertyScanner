from __future__ import annotations

import contextlib
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import pytest
from playwright.sync_api import expect, sync_playwright
from sqlalchemy import create_engine

from src.platform.domain.models import Base


_ROOT = Path(__file__).resolve().parents[3]
_VENV_PYTHON = _ROOT / "venv" / "bin" / "python"


def _python_executable() -> str:
    if _VENV_PYTHON.exists():
        return str(_VENV_PYTHON)
    return sys.executable


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(url: str, timeout_seconds: int = 90) -> None:
    start = time.time()
    last_error: Exception | None = None
    while time.time() - start < timeout_seconds:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # pragma: no cover - best-effort startup polling
            last_error = exc
        time.sleep(1)
    raise AssertionError(f"dashboard_server_not_ready: {last_error}")


@pytest.mark.live
def test_live_dashboard__shows_source_support_and_assumption_badges() -> None:
    port = _free_port()
    dashboard_url = f"http://127.0.0.1:{port}"

    with tempfile.TemporaryDirectory(prefix="dashboard-live-ui-") as tmp_dir:
        db_path = Path(tmp_dir) / "dashboard_live.db"
        create_engine(f"sqlite:///{db_path}").dispose()
        # Ensure all required tables exist so the dashboard starts cleanly on an empty DB.
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        engine.dispose()

        env = os.environ.copy()
        env["PROPERTY_SCANNER_DB_PATH"] = str(db_path)
        env["PYTHONUNBUFFERED"] = "1"

        cmd = [
            _python_executable(),
            "-m",
            "src.interfaces.cli",
            "dashboard",
            "--skip-preflight",
            "--server.headless",
            "true",
            "--server.address",
            "127.0.0.1",
            "--server.port",
            str(port),
        ]
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            cwd=str(_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        try:
            _wait_for_server(dashboard_url, timeout_seconds=120)

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(dashboard_url, wait_until="domcontentloaded", timeout=120_000)

                # Expand lens panel and open system status in the real dashboard runtime.
                expect(page.get_by_role("button", name="Tune")).to_be_visible(timeout=30_000)
                page.get_by_role("button", name="Tune").click()
                expect(page.get_by_role("button", name="Hide")).to_be_visible(timeout=30_000)
                expect(page.get_by_text("System status", exact=False)).to_be_visible(timeout=30_000)
                page.get_by_text("System status", exact=False).first.click()

                expect(page.get_by_text("Source support:", exact=False)).to_be_visible(timeout=30_000)
                expect(page.get_by_text("Assumption badges:", exact=False)).to_be_visible(timeout=30_000)
                expect(page.get_by_text("lit-case-shiller-1988", exact=False)).to_be_visible(timeout=30_000)

                browser.close()
        finally:
            proc.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=15)
            if proc.poll() is None:
                proc.kill()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    proc.wait(timeout=5)
