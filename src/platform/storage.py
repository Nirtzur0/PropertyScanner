from pathlib import Path
from typing import Optional

import structlog
from sqlalchemy import create_engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

from src.platform.config import DEFAULT_DB_URL
from src.platform.domain.models import Base
from src.platform.migrations import run_migrations

logger = structlog.get_logger()


class StorageService:
    def __init__(self, db_url: str = DEFAULT_DB_URL, *, bootstrap_schema: bool = True):
        self.db_url = db_url
        connect_args = {}
        try:
            url = make_url(db_url)
            if url.drivername.startswith("sqlite"):
                connect_args["timeout"] = 30
                if url.database and url.database != ":memory:":
                    Path(url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        self.engine = create_engine(db_url, connect_args=connect_args)
        if bootstrap_schema:
            self.ensure_current_schema()

        self.SessionLocal = sessionmaker(bind=self.engine)

    def ensure_current_schema(self) -> None:
        Base.metadata.create_all(self.engine)

        # Ensure auxiliary tables/columns exist (indices, macro tables, etc).
        # SQLAlchemy `create_all` won't evolve existing SQLite schemas.
        try:
            url = make_url(self.db_url)
            if url.drivername.startswith("sqlite") and url.database and url.database != ":memory:":
                run_migrations(db_path=url.database)
        except Exception as e:
            logger.warning("migrations_failed", error=str(e))

    def get_session(self) -> Session:
        return self.SessionLocal()
