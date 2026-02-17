"""Unit tests for finder main CLI module."""

import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "finder-py"))

# Check if osgeo is available (GDAL bindings - not on PyPI)
HAS_GDAL = importlib.util.find_spec("osgeo") is not None


class TestFinderMain(unittest.TestCase):
    """Test suite for finder main module."""

    @unittest.skipIf(not HAS_GDAL, "osgeo (GDAL) not installed - install via: brew install gdal")
    def test_main_module_imports(self):
        """Test that main module can be imported."""
        try:
            import main as finder_main

            self.assertTrue(hasattr(finder_main, "main"))
        except ImportError as e:
            self.fail(f"Failed to import finder main: {e}")

    @unittest.skipIf(not HAS_GDAL, "osgeo (GDAL) not installed - install via: brew install gdal")
    def test_main_has_required_functions(self):
        """Test that main module has expected functions."""
        import main as finder_main

        # Check for key functions
        self.assertTrue(hasattr(finder_main, "main"))
        self.assertTrue(callable(finder_main.main))

    def test_finder_modules_available(self):
        """Test that finder submodules are available."""
        try:
            from finder import shape, smooth

            self.assertTrue(hasattr(smooth, "smooth_profile"))
            self.assertTrue(hasattr(smooth, "smooth_points"))
            self.assertTrue(hasattr(shape, "extract_extreme_points"))
        except ImportError as e:
            self.fail(f"Failed to import finder modules: {e}")

    def test_main_file_exists(self):
        """Test that main.py file exists."""
        main_file = Path(__file__).parent.parent / "finder-py" / "main.py"
        self.assertTrue(main_file.exists(), "main.py not found")


if __name__ == "__main__":
    unittest.main()
