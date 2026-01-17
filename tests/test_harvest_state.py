import json
import os
import tempfile
import unittest

from src.listings.utils.harvest_state import HarvestAreaState, load_harvest_state, save_harvest_state


class TestHarvestState(unittest.TestCase):
    def test_load_creates_default_state(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
            path = os.path.join(tmpdir, "state.json")
            state = load_harvest_state(
                path=path,
                mode="sale",
                target_count=123,
                start_urls=["https://example.com/a/", "https://example.com/b/"],
            )

            self.assertEqual(state.mode, "sale")
            self.assertEqual(state.target_count, 123)
            self.assertEqual([a.start_url for a in state.areas], ["https://example.com/a", "https://example.com/b"])
            self.assertEqual(state.current_area_index, 0)

    def test_load_preserves_completed_index(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
            path = os.path.join(tmpdir, "state.json")

            saved = load_harvest_state(
                path=path,
                mode="sale",
                target_count=10,
                start_urls=["https://example.com/a/", "https://example.com/b/"],
            )
            saved.current_area_index = 2
            save_harvest_state(path, saved)

            reloaded = load_harvest_state(
                path=path,
                mode="sale",
                target_count=10,
                start_urls=["https://example.com/a/", "https://example.com/b/"],
            )
            self.assertEqual(reloaded.current_area_index, 2)

    def test_load_resets_index_when_completed_and_config_changes(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
            path = os.path.join(tmpdir, "state.json")

            saved = load_harvest_state(
                path=path,
                mode="sale",
                target_count=10,
                start_urls=["https://example.com/a/", "https://example.com/b/"],
            )
            saved.current_area_index = 2
            save_harvest_state(path, saved)

            reloaded = load_harvest_state(
                path=path,
                mode="sale",
                target_count=10,
                start_urls=["https://example.com/c/"],
            )
            self.assertEqual(reloaded.current_area_index, 0)

    def test_load_reconciles_start_urls_order(self):
        with tempfile.TemporaryDirectory(dir=os.getcwd()) as tmpdir:
            path = os.path.join(tmpdir, "state.json")

            saved = load_harvest_state(
                path=path,
                mode="sale",
                target_count=10,
                start_urls=["https://example.com/a/", "https://example.com/b/"],
            )
            saved.areas[1].pages_visited = 42
            saved.current_area_index = 1
            save_harvest_state(path, saved)

            reloaded = load_harvest_state(
                path=path,
                mode="sale",
                target_count=999,
                start_urls=["https://example.com/b/", "https://example.com/c/"],
            )

            self.assertEqual([a.start_url for a in reloaded.areas], ["https://example.com/b", "https://example.com/c"])
            self.assertEqual(reloaded.areas[0].pages_visited, 42)
            self.assertEqual(reloaded.target_count, 999)

    def test_signature_changes_with_links(self):
        area = HarvestAreaState(start_url="https://example.com/a/")
        sig1 = area.compute_signature(["https://example.com/x", "https://example.com/y"])
        sig2 = area.compute_signature(["https://example.com/x", "https://example.com/z"])
        self.assertNotEqual(sig1, sig2)


if __name__ == "__main__":
    unittest.main()
