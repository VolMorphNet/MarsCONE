"""Unit tests for finder smoothing functions."""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "finder-py"))

from finder.smooth import smooth_profile  # noqa: E402


class TestSmoothingFunctions(unittest.TestCase):
    """Test suite for smoothing functions."""

    def setUp(self):
        """Set up test data."""
        self.test_profile = pd.DataFrame(
            {
                "elevation": [100.0, 105.0, 110.0, 105.0, 100.0, 102.0, 108.0],
            }
        )
        self.test_points = pd.Series([1.0, 2.0, 3.0, 10.0, 4.0, 5.0])

    def test_profile_data_type(self):
        """Test that profile data can be accessed."""
        elevation = self.test_profile["elevation"]
        self.assertEqual(len(elevation), 7)

    def test_points_data_type(self):
        """Test that points data is valid series."""
        self.assertIsInstance(self.test_points, pd.Series)

    def test_data_has_values(self):
        """Test that test data contains values."""
        self.assertGreater(len(self.test_profile), 0)
        self.assertGreater(len(self.test_points), 0)

    def test_smooth_profile(self):
        """Test profile smoothing function."""
        # smooth_profile expects: profile, begin_no, end_no, window, degree
        smoothed = smooth_profile(self.test_profile, 0, 6, window=5, degree=2)
        self.assertIsInstance(smoothed, np.ndarray)  # Returns numpy array
        self.assertGreater(len(smoothed), 0)  # Has some data
        self.assertEqual(len(smoothed), 6)  # Returns end_no - begin_no elements


if __name__ == "__main__":
    unittest.main()
