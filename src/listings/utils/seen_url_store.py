import os
import sqlite3
import time
from typing import Iterable, List
from src.platform.config import SEEN_URLS_DB


class SeenUrlStore:
    """
    Disk-backed de-duplication for crawled URLs.

    Using SQLite keeps memory usage flat even with very large crawls, and
    provides stable resume behavior across runs.
    """

    def __init__(self, path: str = str(SEEN_URLS_DB)):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_urls (
                mode TEXT NOT NULL,
                url TEXT NOT NULL,
                added_at REAL NOT NULL,
                PRIMARY KEY (mode, url)
            )
            """
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def count(self, mode: str) -> int:
        cur = self.conn.execute("SELECT COUNT(1) FROM seen_urls WHERE mode = ?", (mode,))
        row = cur.fetchone()
        return int(row[0] if row else 0)

    def reset_mode(self, mode: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM seen_urls WHERE mode = ?", (mode,))

    def seed(self, mode: str, urls: Iterable[str]) -> int:
        """
        Insert a potentially-large iterable of URLs without building a return list.
        Returns the number of URLs newly inserted.
        """
        inserted = 0
        now = time.time()
        with self.conn:
            for url in urls:
                if not url:
                    continue
                cur = self.conn.execute(
                    "INSERT OR IGNORE INTO seen_urls (mode, url, added_at) VALUES (?, ?, ?)",
                    (mode, url, now),
                )
                if cur.rowcount == 1:
                    inserted += 1
        return inserted

    def insert_new(self, mode: str, urls: Iterable[str]) -> List[str]:
        """
        Insert a batch of URLs and return only those that were not seen before.
        """
        new_urls: List[str] = []
        now = time.time()
        with self.conn:
            for url in urls:
                if not url:
                    continue
                cur = self.conn.execute(
                    "INSERT OR IGNORE INTO seen_urls (mode, url, added_at) VALUES (?, ?, ?)",
                    (mode, url, now),
                )
                if cur.rowcount == 1:
                    new_urls.append(url)
        return new_urls
