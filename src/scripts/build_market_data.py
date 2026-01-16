import argparse
import sqlite3
from typing import List, Optional

import structlog

from src.core.migrations import run_migrations
from src.core.config import DEFAULT_DB_PATH
from src.services.hedonic_index import HedonicIndexService
from src.services.macro_data import MacroDataService
from src.services.market_indices import MarketIndexService

logger = structlog.get_logger(__name__)


def _list_cities(db_path: str) -> List[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT DISTINCT city FROM listings WHERE city IS NOT NULL AND city != ''"
        ).fetchall()
        cities: List[str] = []
        for (city,) in rows:
            if not city:
                continue
            cities.append(str(city).strip().lower())
        return sorted(set(c for c in cities if c))
    finally:
        conn.close()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build macro data + market/hedonic indices for projections.")
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH), help="Path to SQLite DB")
    parser.add_argument("--skip-migrations", action="store_true", help="Skip schema migrations")
    parser.add_argument("--skip-macro", action="store_true", help="Skip macro_indicators refresh")
    parser.add_argument("--skip-market-indices", action="store_true", help="Skip market_indices recompute")
    parser.add_argument("--skip-hedonic", action="store_true", help="Skip hedonic_indices recompute")
    parser.add_argument("--city", type=str, default=None, help="Only compute hedonic index for this city (lowercased)")
    parser.add_argument("--train-tft", action="store_true", help="Train TFT forecaster (requires hedonic indices)")
    args = parser.parse_args(argv)

    if not args.skip_migrations:
        run_migrations(db_path=args.db)

    if not args.skip_macro:
        try:
            MacroDataService(db_path=args.db).fetch_all()
        except Exception as e:
            logger.warning("macro_refresh_failed", error=str(e))

    if not args.skip_market_indices:
        try:
            MarketIndexService(db_path=args.db).recompute_indices(region_type="city")
        except Exception as e:
            logger.warning("market_indices_failed", error=str(e))

    if not args.skip_hedonic:
        try:
            hedonic = HedonicIndexService(db_path=args.db)
            if args.city:
                cities = [args.city.strip().lower()]
            else:
                cities = _list_cities(args.db)

            if not cities:
                hedonic.save_to_db(region_name=None)
            else:
                for city in cities:
                    hedonic.save_to_db(region_name=city)
        except Exception as e:
            logger.warning("hedonic_indices_failed", error=str(e))

    if args.train_tft:
        try:
            from src.training.forecasting_tft import TFTForecastingService

            TFTForecastingService(db_path=args.db).train(epochs=50)
        except Exception as e:
            logger.warning("tft_training_failed", error=str(e))

    logger.info("market_data_ready", db=args.db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
