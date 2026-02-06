from src.listings.utils.seen_url_store import SeenUrlStore


def test_insert_new__duplicates_and_empty_strings__returns_new_unique_urls(tmp_path):
    # Arrange
    db_path = tmp_path / "seen.sqlite3"
    store = SeenUrlStore(path=str(db_path))
    try:
        assert store.count("sale") == 0

        # Act
        inserted = store.insert_new("sale", ["a", "b", "a", ""])

        # Assert
        assert inserted == ["a", "b"]
        assert store.count("sale") == 2

        inserted_again = store.insert_new("sale", ["a", "c"])
        assert inserted_again == ["c"]
        assert store.count("sale") == 3

        assert store.count("rent") == 0
        store.insert_new("rent", ["a"])
        assert store.count("rent") == 1
    finally:
        store.close()


def test_reset_mode__existing_rows__clears_mode_partition(tmp_path):
    # Arrange
    db_path = tmp_path / "seen.sqlite3"
    store = SeenUrlStore(path=str(db_path))
    try:
        store.insert_new("sale", ["a", "b"])
        assert store.count("sale") == 2

        # Act
        store.reset_mode("sale")

        # Assert
        assert store.count("sale") == 0
    finally:
        store.close()
