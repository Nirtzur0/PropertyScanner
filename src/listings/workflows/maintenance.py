from datetime import datetime
from typing import Optional

from src.platform.settings import AppConfig
from src.platform.db.base import resolve_db_url
from src.listings.repositories.listings import ListingsRepository
from src.platform.utils.config import load_app_config_safe
from src.platform.utils.time import utcnow

def clean_data(db_path: Optional[str] = None, *, app_config: Optional[AppConfig] = None) -> None:
    app_config = app_config or load_app_config_safe()
    if db_path is None:
        db_path = str(app_config.pipeline.db_path)
    repo = ListingsRepository(db_url=resolve_db_url(db_path=db_path))

    fixed = repo.fix_missing_fetched_at(default_ts=utcnow())
    print(f"Fixed {fixed} missing timestamps.")

    cleared = repo.clear_invalid_coordinates()
    print(f"Cleared {cleared} invalid zero-coordinates.")


def main() -> int:
    clean_data()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
