
import sqlite3
import pygeohash as pgh
import structlog

logger = structlog.get_logger()

def backfill_geohash(db_path="data/listings.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get listings without geohash
    cursor.execute("SELECT id, lat, lon FROM listings WHERE geohash IS NULL AND lat IS NOT NULL")
    rows = cursor.fetchall()
    
    updates = []
    for (lid, lat, lon) in rows:
        if lat and lon:
            gh = pgh.encode(lat, lon, precision=6)
            updates.append((gh, lid))
            
    if updates:
        cursor.executemany("UPDATE listings SET geohash = ? WHERE id = ?", updates)
        conn.commit()
    
    conn.close()
    logger.info("backfill_complete", count=len(updates))

if __name__ == "__main__":
    backfill_geohash()
