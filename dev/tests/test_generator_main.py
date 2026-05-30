"""Unit tests for generator main CLI module."""

import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "generator-py"))

# Check if osgeo is available (GDAL bindings - not on PyPI)
HAS_GDAL = importlib.util.find_spec("osgeo") is not None


class TestGeneratorMain(unittest.TestCase):
    """Test suite for generator main module."""

    @unittest.skipIf(not HAS_GDAL, "osgeo (GDAL) not installed - install via: brew install gdal")
    def test_main_module_imports(self):
        """Test that main module can be imported."""
        try:
            import main as generator_main

            self.assertTrue(hasattr(generator_main, "main"))
        except ImportError as e:
            self.fail(f"Failed to import generator main: {e}")

    @unittest.skipIf(not HAS_GDAL, "osgeo (GDAL) not installed - install via: brew install gdal")
    def test_main_has_required_functions(self):
        """Test that main module has expected functions."""
        import main as generator_main

        # Check for key functions
        self.assertTrue(hasattr(generator_main, "main"))
        self.assertTrue(callable(generator_main.main))

    @unittest.skipIf(not HAS_GDAL, "osgeo (GDAL) not installed - install via: brew install gdal")
    def test_pgen_modules_available(self):
        """Test that pgen submodules are available."""
        try:
            from pgen import config, dem, helper, profile, transect

            self.assertTrue(hasattr(config, "parse"))
            self.assertTrue(hasattr(dem, "get_DEM"))
            self.assertTrue(hasattr(helper, "init"))
            self.assertTrue(hasattr(profile, "generate_profiles"))
            self.assertTrue(hasattr(transect, "generate_transects"))
        except ImportError as e:
            self.fail(f"Failed to import pgen modules: {e}")

    def test_main_file_exists(self):
        """Test that main.py file exists."""
        main_file = Path(__file__).parent.parent / "generator-py" / "main.py"
        self.assertTrue(main_file.exists(), "main.py not found")


if __name__ == "__main__":
    unittest.main()
