from __future__ import annotations

import pandas as pd

from src.listings.agents.crawlers.spain.official_sources import OfficialSourcesAgent


class _Response:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


def test_fetch_eri_stats__uses_bounded_http_fetch_and_processes_csv(monkeypatch, tmp_path) -> None:
    agent = OfficialSourcesAgent(db_path=str(tmp_path / "official.db"))
    calls: list[tuple[str, int]] = []
    processed: list[tuple[int, int, pd.DataFrame]] = []

    def _fake_request_get(session, url: str, timeout: int):
        calls.append((url, timeout))
        return _Response("territorio;n_transacciones;precio_m2;hipotecas\nMadrid;10;2500;4\n")

    def _fake_process(df: pd.DataFrame, year: int, quarter: int) -> None:
        processed.append((year, quarter, df.copy()))

    monkeypatch.setattr(
        "src.listings.agents.crawlers.spain.official_sources.request_get",
        _fake_request_get,
    )
    monkeypatch.setattr(agent, "_process_eri_csv", _fake_process)

    agent.fetch_eri_stats(year=2026)

    assert calls[0][0].endswith("/ER.1.2026.csv")
    assert calls[0][1] == agent.ERI_REQUEST_TIMEOUT_SECONDS
    assert processed[0][0:2] == (2026, 1)
    assert list(processed[0][2].columns) == ["territorio", "n_transacciones", "precio_m2", "hipotecas"]


def test_fetch_eri_stats__continues_after_fetch_error(monkeypatch, tmp_path) -> None:
    agent = OfficialSourcesAgent(db_path=str(tmp_path / "official.db"))
    seen_urls: list[str] = []
    processed_quarters: list[int] = []

    def _fake_request_get(session, url: str, timeout: int):
        seen_urls.append(url)
        if url.endswith("/ER.1.2026.csv"):
            raise TimeoutError("timed_out")
        return _Response("territorio;n_transacciones;precio_m2;hipotecas\nMadrid;10;2500;4\n")

    monkeypatch.setattr(
        "src.listings.agents.crawlers.spain.official_sources.request_get",
        _fake_request_get,
    )
    monkeypatch.setattr(
        agent,
        "_process_eri_csv",
        lambda df, year, quarter: processed_quarters.append(quarter),
    )

    agent.fetch_eri_stats(year=2026)

    assert any(url.endswith("/ER.1.2026.csv") for url in seen_urls)
    assert any(url.endswith("/ER.2.2026.csv") for url in seen_urls)
    assert 2 in processed_quarters
