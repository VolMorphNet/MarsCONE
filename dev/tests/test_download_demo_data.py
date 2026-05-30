"""Unit tests for download_demo_data module."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from download_demo_data import DEFAULT_DATA_DIR, DEFAULT_URL  # noqa: E402


class TestDownloadDemoData(unittest.TestCase):
    """Test suite for download_demo_data functions."""

    def test_default_url_format(self):
        """Test that default URL is properly formatted."""
        self.assertIsInstance(DEFAULT_URL, str)
        self.assertTrue(DEFAULT_URL.startswith("https://"))
        self.assertIn("zenodo", DEFAULT_URL)

    def test_default_data_dir(self):
        """Test that default data directory is set."""
        self.assertIsInstance(DEFAULT_DATA_DIR, str)
        self.assertEqual(DEFAULT_DATA_DIR, "data")

    def test_path_construction(self):
        """Test that Path objects can be created from defaults."""
        data_path = Path(DEFAULT_DATA_DIR)
        self.assertIsInstance(data_path, Path)
        self.assertEqual(data_path.name, "data")


if __name__ == "__main__":
    unittest.main()
