
import sqlite3
import structlog

logger = structlog.get_logger()

def upgrade_schema(db_path="data/listings.db"):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("ALTER TABLE listings ADD COLUMN geohash VARCHAR")
        logger.info("schema_upgraded")
    except Exception as e:
        logger.info("schema_upgrade_skipped", reason=str(e))
    conn.close()

if __name__ == "__main__":
    upgrade_schema()
