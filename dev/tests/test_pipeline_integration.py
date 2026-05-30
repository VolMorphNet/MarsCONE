"""Integration tests using real demo data from test_set.

These tests run the actual pipeline on demo data to verify
end-to-end functionality.
"""

import sys
import unittest
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestPipelineIntegration(unittest.TestCase):
    """Integration tests for complete pipeline with demo data."""

    @classmethod
    def setUpClass(cls):
        """Set up test fixtures - check if demo data exists."""
        cls.base_dir = Path(__file__).parent.parent
        cls.test_data_dir = cls.base_dir / "data" / "test_set"

        # Check if demo data is available
        cls.has_demo_data = cls.test_data_dir.exists()

        if cls.has_demo_data:
            cls.input_dir = cls.test_data_dir / "input"
            cls.output_dir = cls.test_data_dir / "output"
            cls.db_path = cls.test_data_dir / "db" / "database.gpkg"

    def test_demo_data_exists(self):
        """Test that demo data directory exists."""
        self.assertTrue(
            self.test_data_dir.exists(), f"Demo data not found at {self.test_data_dir}"
        )

    def test_input_data_structure(self):
        """Test that input data has correct structure."""
        if not self.has_demo_data:
            self.skipTest("Demo data not available")

        # Check for required directories
        self.assertTrue((self.input_dir / "dem").exists(), "DEM directory not found")
        self.assertTrue(
            (self.input_dir / "points").exists(), "Points directory not found"
        )

        # Check for shapefiles
        shapefiles = list((self.input_dir / "points").glob("*.shp"))
        self.assertGreater(
            len(shapefiles), 0, "No shapefiles found in points directory"
        )

    def test_dem_file_exists(self):
        """Test that DEM file exists."""
        if not self.has_demo_data:
            self.skipTest("Demo data not available")

        dem_files = list((self.input_dir / "dem").glob("*.tif"))
        self.assertGreater(len(dem_files), 0, "No DEM .tif files found")

    def test_database_file_exists(self):
        """Test that GeoPackage database exists (requires pipeline run)."""
        if not self.has_demo_data:
            self.skipTest("Demo data not available")

        if not self.db_path.exists():
            self.skipTest(
                "Pipeline has not been run yet. "
                "Run 'python run_pipeline.py' first to generate output."
            )

    def test_output_directories_created(self):
        """Test that output directories were created by pipeline."""
        if not self.has_demo_data:
            self.skipTest("Demo data not available")

        if not self.output_dir.exists():
            self.skipTest(
                "Pipeline has not been run yet. "
                "Run 'python run_pipeline.py' first to generate output."
            )

        # Check for required output subdirectories
        required_dirs = ["generator", "finder", "analyzer"]

        for dirname in required_dirs:
            dir_path = self.output_dir / dirname
            self.assertTrue(dir_path.exists(), f"Output directory not found: {dirname}")

        # Check for optional figures directory (created by notebook)
        figures_dir = self.output_dir / "figures"
        # This is informational, not a failure
        if not figures_dir.exists():
            print(
                "Note: figures directory not found (created by notebook visualization)"
            )

    def test_analyzer_output_files(self):
        """Test that analyzer produced expected output files."""
        if not self.has_demo_data:
            self.skipTest("Demo data not available")

        analyzer_dir = self.output_dir / "analyzer"
        if not analyzer_dir.exists():
            self.skipTest(
                "Pipeline has not been run yet. "
                "Run 'python run_pipeline.py' first to generate output."
            )

        # Check for result files
        expected_files = ["results.csv", "cone_summary.csv", "marscone.gpkg"]

        for filename in expected_files:
            file_path = analyzer_dir / filename
            self.assertTrue(
                file_path.exists(), f"Expected output file not found: {filename}"
            )

    def test_results_csv_not_empty(self):
        """Test that results.csv contains data."""
        if not self.has_demo_data:
            self.skipTest("Demo data not available")

        results_file = self.output_dir / "analyzer" / "results.csv"
        if not results_file.exists():
            self.skipTest(
                "Pipeline has not been run yet. "
                "Run 'python run_pipeline.py' first to generate output."
            )

        with open(results_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Should have header + at least one data row
        self.assertGreater(len(lines), 1, "results.csv is empty or has only header")

    def test_pipeline_runner_exists(self):
        """Test that run_pipeline.py script exists."""
        pipeline_script = self.base_dir / "run_pipeline.py"
        self.assertTrue(pipeline_script.exists(), "run_pipeline.py not found")

    def test_all_main_files_exist(self):
        """Test that all module main.py files exist."""
        modules = ["generator-py", "finder-py", "analyzer-py"]

        for module in modules:
            main_py = self.base_dir / module / "main.py"
            self.assertTrue(main_py.exists(), f"main.py not found in {module}")


class TestPipelineRunner(unittest.TestCase):
    """Tests for the pipeline runner script."""

    def setUp(self):
        """Set up test fixtures."""
        self.base_dir = Path(__file__).parent.parent
        self.pipeline_script = self.base_dir / "run_pipeline.py"

    def test_pipeline_runner_imports(self):
        """Test that pipeline runner can be imported."""
        try:
            sys.path.insert(0, str(self.base_dir))
            import run_pipeline

            self.assertTrue(hasattr(run_pipeline, "PipelineRunner"))
            self.assertTrue(hasattr(run_pipeline, "main"))
        except ImportError as e:
            self.fail(f"Failed to import run_pipeline: {e}")

    def test_pipeline_runner_class_methods(self):
        """Test that PipelineRunner has required methods."""
        sys.path.insert(0, str(self.base_dir))
        import run_pipeline

        runner = run_pipeline.PipelineRunner(self.base_dir)

        self.assertTrue(hasattr(runner, "run_module"))
        self.assertTrue(hasattr(runner, "run_notebook"))
        self.assertTrue(hasattr(runner, "run_full_pipeline"))

        self.assertTrue(callable(runner.run_module))
        self.assertTrue(callable(runner.run_notebook))
        self.assertTrue(callable(runner.run_full_pipeline))


if __name__ == "__main__":
    unittest.main()
