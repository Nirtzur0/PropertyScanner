from pathlib import Path
from typing import Optional, Union

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine

from src.platform.config import DEFAULT_DB_URL
from src.platform.storage import StorageService


def resolve_db_url(db_url: Optional[str] = None, db_path: Optional[Union[str, Path]] = None) -> str:
    if db_url:
        return str(db_url)
    if db_path:
        db_path_str = str(db_path)
        if "://" in db_path_str:
            return db_path_str
        return f"sqlite:///{db_path_str}"
    return str(DEFAULT_DB_URL)


class RepositoryBase:
    def __init__(
        self,
        *,
        db_url: Optional[str] = None,
        db_path: Optional[Union[str, Path]] = None,
        storage: Optional[StorageService] = None,
        engine: Optional[Engine] = None,
    ) -> None:
        if engine is not None:
            self.engine = engine
            self.storage = storage
        else:
            resolved = resolve_db_url(db_url=db_url, db_path=db_path)
            self.storage = storage or StorageService(db_url=resolved)
            self.engine = self.storage.engine

    def has_table(self, table_name: str) -> bool:
        inspector = inspect(self.engine)
        return table_name in inspector.get_table_names()

    def has_column(self, table_name: str, column_name: str) -> bool:
        inspector = inspect(self.engine)
        try:
            cols = inspector.get_columns(table_name)
        except Exception:
            return False
        return any(col.get("name") == column_name for col in cols)
