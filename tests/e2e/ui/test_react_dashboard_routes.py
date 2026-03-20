from __future__ import annotations

from pathlib import Path
import socket
import threading
import time
import urllib.request

import pytest
import uvicorn
from playwright.sync_api import expect, sync_playwright

from src.adapters.http import app as app_module
from tests.unit.adapters.http.test_fastapi_local_api import _container


_ROOT = Path(__file__).resolve().parents[3]
_FRONTEND_DIST = _ROOT / "frontend" / "dist"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(url: str, timeout_seconds: int = 30) -> None:
    start = time.time()
    last_error: Exception | None = None
    while time.time() - start < timeout_seconds:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # pragma: no cover - best effort startup polling
            last_error = exc
        time.sleep(0.5)
    raise AssertionError(f"react_dashboard_server_not_ready: {last_error}")


@pytest.mark.e2e
def test_react_dashboard_routes__render_redesigned_surfaces(tmp_path, monkeypatch) -> None:
    if not (_FRONTEND_DIST / "index.html").exists():
        pytest.skip("frontend_dist_missing: run `npm run build` in frontend/ first")

    container = _container(tmp_path)
    container.workspace.create_watchlist(
        name="Core Madrid",
        description="Priority review bucket",
        listing_ids=["target"],
        filters={"city": "Madrid"},
    )
    container.workspace.create_saved_search(
        name="Madrid apartments",
        query="Madrid apartments",
        filters={"city": "Madrid"},
        sort={"field": "price", "direction": "asc"},
    )
    container.workspace.create_memo(
        title="Target memo",
        listing_id="target",
        sections=[{"heading": "Summary", "body": "Prioritize after comp review."}],
    )
    container.workspace.create_comp_review(
        listing_id="target",
        selected_comp_ids=["comp-1", "comp-2"],
        rejected_comp_ids=["comp-3"],
        overrides={"condition_adjustment_pct": 0.02},
        notes="Manual review requested.",
    )
    container.valuation.evaluate_listing_id("target", persist=True)

    monkeypatch.setattr(app_module, "get_container", lambda: container)
    monkeypatch.setattr(app_module, "_FRONTEND_DIST", _FRONTEND_DIST)

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app_module.app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_for_server(f"http://127.0.0.1:{port}/workbench")

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1100})

            page.goto(f"http://127.0.0.1:{port}/watchlists?tab=memos", wait_until="domcontentloaded", timeout=120_000)
            expect(page.get_by_text("Decision hub", exact=False)).to_be_visible(timeout=30_000)
            expect(page.get_by_text("Target memo", exact=False)).to_be_visible(timeout=30_000)
            expect(page.get_by_role("button", name="Watchlists")).to_be_visible(timeout=30_000)
            expect(page.locator("button", has_text="Saved searches")).to_be_visible(timeout=30_000)
            expect(page.get_by_role("button", name="Memos")).to_be_visible(timeout=30_000)

            page.goto(
                f"http://127.0.0.1:{port}/watchlists?tab=saved-searches",
                wait_until="domcontentloaded",
                timeout=120_000,
            )
            expect(page.get_by_text("Reusable lens library", exact=False)).to_be_visible(timeout=30_000)
            expect(page.locator("strong", has_text="Madrid apartments")).to_be_visible(timeout=30_000)

            page.goto(f"http://127.0.0.1:{port}/listings/target", wait_until="domcontentloaded", timeout=120_000)
            expect(page.get_by_text("Listing dossier", exact=False)).to_be_visible(timeout=30_000)
            expect(page.get_by_text("Health, freshness, and provenance", exact=False)).to_be_visible(timeout=30_000)
            expect(page.get_by_text("Only the signals that change the call", exact=False)).to_be_visible(timeout=30_000)

            page.goto(f"http://127.0.0.1:{port}/comp-reviews/target", wait_until="domcontentloaded", timeout=120_000)
            expect(page.get_by_text("Comp workbench", exact=False)).to_be_visible(timeout=30_000)
            expect(page.get_by_role("heading", name="Pin, reject, or leave under consideration")).to_be_visible(timeout=30_000)
            expect(page.get_by_role("heading", name="Analyst overrides")).to_be_visible(timeout=30_000)
            expect(page.get_by_role("button", name="Save review")).to_be_enabled(timeout=30_000)

            page.goto(f"http://127.0.0.1:{port}/comp-reviews/missing-area", wait_until="domcontentloaded", timeout=120_000)
            expect(page.get_by_text("Target Surface Area Required", exact=False)).to_be_visible(timeout=30_000)
            expect(page.get_by_role("button", name="Save review")).to_be_disabled(timeout=30_000)

            page.goto(f"http://127.0.0.1:{port}/pipeline", wait_until="domcontentloaded", timeout=120_000)
            expect(page.get_by_text("Pipeline trust surface", exact=False)).to_be_visible(timeout=30_000)
            expect(page.get_by_text("Top blockers", exact=False)).to_be_visible(timeout=30_000)
            expect(page.get_by_text("Show operational details", exact=False)).to_be_visible(timeout=30_000)

            page.goto(f"http://127.0.0.1:{port}/command-center", wait_until="domcontentloaded", timeout=120_000)
            expect(page).to_have_url(f"http://127.0.0.1:{port}/pipeline", timeout=30_000)
            expect(page.get_by_text("Pipeline trust surface", exact=False)).to_be_visible(timeout=30_000)

            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=15)
