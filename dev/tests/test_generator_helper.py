"""Unit tests for generator helper functions."""

import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "generator-py"))

# Check if osgeo is available (GDAL bindings - not on PyPI)
HAS_GDAL = importlib.util.find_spec("osgeo") is not None

# Import only what's safe to test without file system dependencies
try:
    from pgen import helper

    HELPER_AVAILABLE = True
except ImportError:
    HELPER_AVAILABLE = False


class TestGeneratorHelper(unittest.TestCase):
    """Test suite for generator helper functions."""

    @unittest.skipIf(not HAS_GDAL, "osgeo (GDAL) not installed - install via: brew install gdal")
    def test_helper_module_exists(self):
        """Test that helper module can be imported."""
        self.assertTrue(HELPER_AVAILABLE, "helper module not found")

    def test_helper_has_functions(self):
        """Test that helper module has expected functions."""
        if not HELPER_AVAILABLE:
            self.skipTest("helper module not available")

        self.assertTrue(hasattr(helper, "init"))
        self.assertTrue(hasattr(helper, "detect_mode"))
        self.assertTrue(hasattr(helper, "check_paths"))
        self.assertTrue(hasattr(helper, "read_input_features"))

    def test_helper_functions_callable(self):
        """Test that helper functions are callable."""
        if not HELPER_AVAILABLE:
            self.skipTest("helper module not available")

        self.assertTrue(callable(helper.init))
        self.assertTrue(callable(helper.detect_mode))
        self.assertTrue(callable(helper.check_paths))


if __name__ == "__main__":
    unittest.main()
