import structlog
from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker, Session
from src.platform.domain.models import Base
from src.platform.migrations import run_migrations
from src.platform.config import DEFAULT_DB_URL

logger = structlog.get_logger()

class StorageService:
    def __init__(self, db_url: str = DEFAULT_DB_URL):
        connect_args = {}
        try:
            url = make_url(db_url)
            if url.drivername.startswith("sqlite"):
                connect_args["timeout"] = 30
        except Exception:
            pass

        self.engine = create_engine(db_url, connect_args=connect_args)
        Base.metadata.create_all(self.engine)

        # Ensure auxiliary tables/columns exist (indices, macro tables, etc).
        # SQLAlchemy `create_all` won't evolve existing SQLite schemas.
        try:
            url = make_url(db_url)
            if url.drivername.startswith("sqlite") and url.database and url.database != ":memory:":
                run_migrations(db_path=url.database)
        except Exception as e:
            logger.warning("migrations_failed", error=str(e))

        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()
