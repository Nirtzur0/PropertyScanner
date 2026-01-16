from datetime import datetime

from src.core.config import DEFAULT_DB_PATH
from src.repositories.base import resolve_db_url
from src.repositories.listings import ListingsRepository

DB_PATH = str(DEFAULT_DB_PATH)


def clean_data(db_path: str = DB_PATH) -> None:
    repo = ListingsRepository(db_url=resolve_db_url(db_path=db_path))

    fixed = repo.fix_missing_fetched_at(default_ts=datetime.utcnow())
    print(f"Fixed {fixed} missing timestamps.")

    cleared = repo.clear_invalid_coordinates()
    print(f"Cleared {cleared} invalid zero-coordinates.")


def main() -> int:
    clean_data()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
