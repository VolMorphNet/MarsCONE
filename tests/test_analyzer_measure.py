"""Unit tests for analyzer measurement functions."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "analyzer-py"))

from analyzer.measure import (get_distance,  # noqa: E402
                              get_points_by_elevation, get_slope)


class TestMeasurementFunctions(unittest.TestCase):
    """Test suite for measurement functions."""

    def setUp(self):
        """Set up test profile data."""
        self.profile_data = pd.DataFrame(
            {
                "elevation": [100.0, 105.0, 110.0, 105.0, 100.0],
                "x_geo": [0.0, 1.0, 2.0, 3.0, 4.0],
                "y_geo": [0.0, 0.0, 0.0, 0.0, 0.0],
            }
        )

    def test_profile_data_structure(self):
        """Test that profile data has required columns."""
        required_cols = ["elevation", "x_geo", "y_geo"]
        self.assertTrue(all(col in self.profile_data.columns for col in required_cols))

    def test_elevation_range(self):
        """Test that elevation values are in valid range."""
        elevations = self.profile_data["elevation"].values
        self.assertTrue(np.all(elevations >= 0))
        self.assertTrue(np.all(elevations <= 9000))  # Reasonable upper bound for DEM

    def test_coordinate_order(self):
        """Test that x and y coordinates are properly paired."""
        self.assertEqual(
            len(self.profile_data["x_geo"]), len(self.profile_data["y_geo"])
        )

    def test_get_distance(self):
        """Test distance calculation along profile."""
        # Test distance between point 0 and point 2
        distance = get_distance(self.profile_data, 0, 2)
        self.assertIsInstance(distance, float)
        self.assertGreater(distance, 0)

    def test_get_slope(self):
        """Test slope calculation."""
        # Calculate slope from point 0 to point 2
        slope = get_slope(self.profile_data, 0, 2)
        self.assertIsInstance(slope, float)

    def test_get_points_by_elevation(self):
        """Test filtering points by elevation."""
        elevations = [102.0, 108.0]
        result = get_points_by_elevation(elevations, self.profile_data, 0, 4)
        self.assertIsInstance(result, dict)  # Returns dict with elevation keys
        self.assertEqual(len(result), 2)  # Two elevation values


if __name__ == "__main__":
    unittest.main()
