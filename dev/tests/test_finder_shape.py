"""Unit tests for finder shape extraction functions."""

import sys
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).parent.parent / "finder-py"))

try:
    from finder import shape

    SHAPE_AVAILABLE = True
except ImportError:
    SHAPE_AVAILABLE = False


class TestFinderShape(unittest.TestCase):
    """Test suite for shape extraction functions."""

    def setUp(self):
        """Set up test data with extreme points."""
        # Create test GeoDataFrame with points
        points_data = {
            "geometry": [
                Point(0, 0),
                Point(1, 5),  # Top point (max y)
                Point(2, 0),
                Point(3, -3),  # Bottom point (min y)
                Point(4, 0),
            ],
            "elevation": [100.0, 110.0, 105.0, 95.0, 100.0],
            "cone_id": ["cone_1"] * 5,
            "transect_id": ["transect_1"] * 5,
        }
        self.test_points = gpd.GeoDataFrame(points_data, crs="EPSG:4326")

    def test_shape_module_exists(self):
        """Test that shape module can be imported."""
        self.assertTrue(SHAPE_AVAILABLE, "shape module not found")

    def test_shape_has_functions(self):
        """Test that shape module has expected functions."""
        if not SHAPE_AVAILABLE:
            self.skipTest("shape module not available")

        self.assertTrue(hasattr(shape, "extract_extreme_points"))

    def test_geodataframe_structure(self):
        """Test that test GeoDataFrame has correct structure."""
        self.assertIsInstance(self.test_points, gpd.GeoDataFrame)
        self.assertIn("geometry", self.test_points.columns)
        self.assertIn("elevation", self.test_points.columns)
        self.assertEqual(len(self.test_points), 5)


if __name__ == "__main__":
    unittest.main()
