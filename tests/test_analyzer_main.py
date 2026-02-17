"""Unit tests for analyzer main CLI module."""

import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "analyzer-py"))

# Check if osgeo is available (GDAL bindings - not on PyPI)
HAS_GDAL = importlib.util.find_spec("osgeo") is not None


class TestAnalyzerMain(unittest.TestCase):
    """Test suite for analyzer main module."""

    @unittest.skipIf(not HAS_GDAL, "osgeo (GDAL) not installed - install via: brew install gdal")
    def test_main_module_imports(self):
        """Test that main module can be imported."""
        try:
            import main as analyzer_main

            self.assertTrue(hasattr(analyzer_main, "main"))
        except ImportError as e:
            self.fail(f"Failed to import analyzer main: {e}")

    @unittest.skipIf(not HAS_GDAL, "osgeo (GDAL) not installed - install via: brew install gdal")
    def test_main_has_required_functions(self):
        """Test that main module has expected functions."""
        import main as analyzer_main

        # Check for key functions
        self.assertTrue(hasattr(analyzer_main, "main"))
        self.assertTrue(callable(analyzer_main.main))

    def test_analyzer_module_available(self):
        """Test that analyzer submodule is available."""
        try:
            from analyzer import measure

            self.assertTrue(hasattr(measure, "get_distance"))
            self.assertTrue(hasattr(measure, "get_slope"))
            self.assertTrue(hasattr(measure, "get_volume"))
            self.assertTrue(hasattr(measure, "get_points_by_elevation"))
        except ImportError as e:
            self.fail(f"Failed to import analyzer.measure: {e}")

    def test_main_file_exists(self):
        """Test that main.py file exists."""
        main_file = Path(__file__).parent.parent / "analyzer-py" / "main.py"
        self.assertTrue(main_file.exists(), "main.py not found")


if __name__ == "__main__":
    unittest.main()
