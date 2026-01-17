from datetime import datetime
import sqlite3

from src.market.repositories.eri_metrics import ERIMetricsRepository
from src.market.services.eri_signals import ERISignalsService


def _create_market_indices(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE market_indices (
            id TEXT PRIMARY KEY,
            region_id TEXT,
            month_date DATE,
            price_index_sqm FLOAT,
            rent_index_sqm FLOAT,
            inventory_count INT,
            new_listings_count INT,
            sold_count INT,
            absorption_rate FLOAT,
            median_dom INT,
            price_cut_share FLOAT,
            volatility_3m FLOAT,
            updated_at DATETIME
        )
        """
    )
    conn.execute("CREATE INDEX ix_market_indices_region_date ON market_indices (region_id, month_date)")


def _seed_market_indices(conn: sqlite3.Connection, region_id: str) -> None:
    rows = []
    base_price = 3000.0
    for idx, month in enumerate(["2023-01-01", "2023-02-01", "2023-03-01", "2023-04-01", "2023-05-01"]):
        rows.append(
            (
                f"{region_id}-{month}",
                region_id,
                month,
                base_price + idx * 50,
                base_price * 0.5,
                100 + idx * 2,
                80 + idx * 3,
                None,
                None,
                None,
                None,
                None,
                month,
            )
        )
    conn.executemany(
        """
        INSERT OR REPLACE INTO market_indices (
            id, region_id, month_date, price_index_sqm, rent_index_sqm, inventory_count,
            new_listings_count, sold_count, absorption_rate, median_dom, price_cut_share,
            volatility_3m, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def test_registry_signals_eri(tmp_path):
    db_path = tmp_path / "registry.db"
    db_url = f"sqlite:///{db_path}"

    repo = ERIMetricsRepository(db_url=db_url)
    repo.ensure_schema()
    records = [
        {
            "id": "madrid-2023-01-01",
            "region_id": "madrid",
            "period_date": "2023-01-01",
            "txn_count": 100,
            "mortgage_count": 60,
            "price_sqm": 3000.0,
        },
        {
            "id": "madrid-2023-04-01",
            "region_id": "madrid",
            "period_date": "2023-04-01",
            "txn_count": 110,
            "mortgage_count": 65,
            "price_sqm": 3050.0,
        },
        {
            "id": "madrid-2023-07-01",
            "region_id": "madrid",
            "period_date": "2023-07-01",
            "txn_count": 120,
            "mortgage_count": 70,
            "price_sqm": 3100.0,
        },
        {
            "id": "madrid-2023-10-01",
            "region_id": "madrid",
            "period_date": "2023-10-01",
            "txn_count": 130,
            "mortgage_count": 75,
            "price_sqm": 3200.0,
        },
        {
            "id": "madrid-2024-01-01",
            "region_id": "madrid",
            "period_date": "2024-01-01",
            "txn_count": 140,
            "mortgage_count": 80,
            "price_sqm": 3300.0,
        },
    ]
    repo.upsert_records(records)

    service = ERISignalsService(db_url=db_url)
    signals = service.get_signals(
        "madrid",
        datetime(2024, 6, 1),
        allow_proxy=False,
        country_code="ES",
    )

    assert signals
    assert signals.get("registry_provider") == "eri_es"
    assert "registral_price_sqm_change" in signals
    assert "txn_volume_z" in signals


def test_registry_signals_proxy_for_gb_and_it(tmp_path):
    db_path = tmp_path / "registry_proxy.db"
    conn = sqlite3.connect(db_path)
    _create_market_indices(conn)
    _seed_market_indices(conn, "london")
    _seed_market_indices(conn, "rome")
    conn.commit()
    conn.close()

    db_url = f"sqlite:///{db_path}"
    service = ERISignalsService(db_url=db_url)

    gb_signals = service.get_signals(
        "london",
        datetime(2024, 6, 1),
        allow_proxy=True,
        country_code="GB",
    )
    it_signals = service.get_signals(
        "rome",
        datetime(2024, 6, 1),
        allow_proxy=True,
        country_code="IT",
    )

    assert gb_signals
    assert gb_signals.get("registry_provider") == "uk_land_registry"
    assert "registral_price_sqm_change" in gb_signals

    assert it_signals
    assert it_signals.get("registry_provider") == "it_omi_registry"
    assert "registral_price_sqm_change" in it_signals
