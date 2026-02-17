"""Unit tests for Jupyter notebooks."""

import json
import unittest
from pathlib import Path


class TestNotebooks(unittest.TestCase):
    """Test suite for Jupyter notebook files."""

    def test_cross_section_notebook_exists(self):
        """Test that cross-section.ipynb exists."""
        notebook_path = Path(__file__).parent.parent / "cross-section.ipynb"
        self.assertTrue(notebook_path.exists(), "cross-section.ipynb not found")

    def test_cross_section_notebook_valid_json(self):
        """Test that notebook is valid JSON."""
        notebook_path = Path(__file__).parent.parent / "cross-section.ipynb"
        if not notebook_path.exists():
            self.skipTest("Notebook not found")

        try:
            with open(notebook_path, "r", encoding="utf-8") as f:
                nb_data = json.load(f)
            self.assertIsInstance(nb_data, dict)
            self.assertIn("cells", nb_data)
        except json.JSONDecodeError as e:
            self.fail(f"Notebook is not valid JSON: {e}")

    def test_notebook_has_cells(self):
        """Test that notebook contains cells."""
        notebook_path = Path(__file__).parent.parent / "cross-section.ipynb"
        if not notebook_path.exists():
            self.skipTest("Notebook not found")

        with open(notebook_path, "r", encoding="utf-8") as f:
            nb_data = json.load(f)

        self.assertIn("cells", nb_data)
        self.assertGreater(len(nb_data["cells"]), 0, "Notebook has no cells")

    def test_notebook_metadata(self):
        """Test that notebook has required metadata."""
        notebook_path = Path(__file__).parent.parent / "cross-section.ipynb"
        if not notebook_path.exists():
            self.skipTest("Notebook not found")

        with open(notebook_path, "r", encoding="utf-8") as f:
            nb_data = json.load(f)

        self.assertIn("metadata", nb_data)
        self.assertIn("nbformat", nb_data)


if __name__ == "__main__":
    unittest.main()
