import os
import tempfile
import unittest

from src.utils.seen_url_store import SeenUrlStore


class TestSeenUrlStore(unittest.TestCase):
    def test_insert_new_and_count(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
            db_path = os.path.join(tmpdir, "seen.sqlite3")
            store = SeenUrlStore(path=db_path)
            try:
                self.assertEqual(store.count("sale"), 0)

                inserted = store.insert_new("sale", ["a", "b", "a", ""])
                self.assertEqual(inserted, ["a", "b"])
                self.assertEqual(store.count("sale"), 2)

                inserted_again = store.insert_new("sale", ["a", "c"])
                self.assertEqual(inserted_again, ["c"])
                self.assertEqual(store.count("sale"), 3)

                self.assertEqual(store.count("rent"), 0)
                store.insert_new("rent", ["a"])
                self.assertEqual(store.count("rent"), 1)
            finally:
                store.close()

    def test_reset_mode(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
            db_path = os.path.join(tmpdir, "seen.sqlite3")
            store = SeenUrlStore(path=db_path)
            try:
                store.insert_new("sale", ["a", "b"])
                self.assertEqual(store.count("sale"), 2)
                store.reset_mode("sale")
                self.assertEqual(store.count("sale"), 0)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()

