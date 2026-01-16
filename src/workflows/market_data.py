import argparse
from typing import List, Optional

import structlog

from src.core.migrations import run_migrations
from src.core.config import DEFAULT_DB_PATH
from src.repositories.base import resolve_db_url
from src.repositories.listings import ListingsRepository
from src.services.hedonic_index import HedonicIndexService
from src.services.macro_data import MacroDataService
from src.services.market_indices import MarketIndexService

logger = structlog.get_logger(__name__)


def _list_cities(db_path: str) -> List[str]:
    db_url = resolve_db_url(db_path=db_path)
    repo = ListingsRepository(db_url=db_url)
    return repo.list_cities()


def build_market_data(
    *,
    db_path: str = str(DEFAULT_DB_PATH),
    skip_migrations: bool = False,
    skip_macro: bool = False,
    skip_market_indices: bool = False,
    skip_hedonic: bool = False,
    city: Optional[str] = None,
    train_tft: bool = False,
) -> None:
    if not skip_migrations:
        run_migrations(db_path=db_path)

    if not skip_macro:
        try:
            MacroDataService(db_path=db_path).fetch_all()
        except Exception as e:
            logger.warning("macro_refresh_failed", error=str(e))

    if not skip_market_indices:
        try:
            MarketIndexService(db_path=db_path).recompute_indices(region_type="city")
        except Exception as e:
            logger.warning("market_indices_failed", error=str(e))
            
    # 2b. Official Government Data (INE/ERI)
    # Allows fallback anchors for Hedonic and Liquidity signals
    try:
        from src.agents.crawlers.official_sources import OfficialSourcesAgent
        OfficialSourcesAgent(db_path=db_path).run()
    except Exception as e:
        logger.warning("official_sources_ingest_failed", error=str(e))


    if not skip_hedonic:
        try:
            hedonic = HedonicIndexService(db_path=db_path)
            hedonic.save_to_db(region_name=None)
            if city:
                cities = [city.strip().lower()]
            else:
                cities = _list_cities(db_path)

            for target_city in cities:
                hedonic.save_to_db(region_name=target_city)
        except Exception as e:
            logger.warning("hedonic_indices_failed", error=str(e))

    if train_tft:
        try:
            from src.training.forecasting_tft import TFTForecastingService

            TFTForecastingService(db_path=db_path).train(epochs=50)
        except Exception as e:
            logger.warning("tft_training_failed", error=str(e))

    logger.info("market_data_ready", db=db_path)


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

    build_market_data(
        db_path=args.db,
        skip_migrations=args.skip_migrations,
        skip_macro=args.skip_macro,
        skip_market_indices=args.skip_market_indices,
        skip_hedonic=args.skip_hedonic,
        city=args.city,
        train_tft=args.train_tft,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
