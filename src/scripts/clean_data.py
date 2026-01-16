import sqlite3
from datetime import datetime

from src.core.config import DEFAULT_DB_PATH

DB_PATH = str(DEFAULT_DB_PATH)

def clean_data():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Fix fetched_at
    # If fetched_at is NULL, set it to updated_at, or now if both NULL
    cursor.execute("""
        UPDATE listings 
        SET fetched_at = COALESCE(updated_at, ?) 
        WHERE fetched_at IS NULL
    """, (datetime.utcnow(),))
    print(f"Fixed {cursor.rowcount} missing timestamps.")
    
    # 2. Fix invalid Zero coordinates (which cause s00000 geohash)
    # Also ignore s00000 string itself
    cursor.execute("""
        UPDATE listings 
        SET lat = NULL, lon = NULL, geohash = NULL 
        WHERE geohash = 's00000' OR (lat = 0.0 AND lon = 0.0)
    """)
    print(f"Cleared {cursor.rowcount} invalid zero-coordinates.")
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    clean_data()
