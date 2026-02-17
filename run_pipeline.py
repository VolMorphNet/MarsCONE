#!/usr/bin/env python3
"""Run complete MarsCONE analysis pipeline.

This script orchestrates the full analysis workflow:
1. Generator: Create DEM crops, transects, and profiles
2. Finder: Detect cone features (bottom, top, center points)
3. Analyzer: Calculate morphometric parameters
4. Visualizer: Generate cross-section plots (optional)

Usage:
    python run_pipeline.py                    # Run all steps
    python run_pipeline.py --skip-generator   # Skip generator step
    python run_pipeline.py --only-analyzer    # Run only analyzer
    python run_pipeline.py --with-viz         # Include visualization
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path


class PipelineRunner:
    """MarsCONE pipeline orchestrator."""

    def __init__(self, base_dir: Path):
        """Initialize pipeline runner.

        Parameters
        ----------
        base_dir : Path
            Base directory containing module folders.
        """
        self.base_dir = base_dir
        self.generator_dir = base_dir / "generator-py"
        self.finder_dir = base_dir / "finder-py"
        self.analyzer_dir = base_dir / "analyzer-py"
        self.notebook_path = base_dir / "cross-section.ipynb"

    def run_module(self, module_dir: Path, module_name: str) -> bool:
        """Run a single module (generator, finder, or analyzer).

        Parameters
        ----------
        module_dir : Path
            Directory containing the module's main.py.
        module_name : str
            Name of the module for logging.

        Returns
        -------
        bool
            True if module ran successfully, False otherwise.
        """
        main_py = module_dir / "main.py"

        if not main_py.exists():
            print(f"✘ {module_name} main.py not found: {main_py}")
            return False

        print(f"\n{'=' * 60}")
        print(f"▶ Running {module_name}...")
        print(f"{'=' * 60}")

        start_time = time.time()

        try:
            result = subprocess.run(
                [sys.executable, "main.py"],
                cwd=module_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            elapsed = time.time() - start_time
            print(result.stdout)

            print(f"✔ {module_name} completed successfully in {elapsed:.1f}s")
            return True

        except subprocess.CalledProcessError as e:
            elapsed = time.time() - start_time
            print(f"✘ {module_name} failed after {elapsed:.1f}s")
            print(f"Error output:\n{e.stderr}")
            return False

    def run_notebook(self) -> bool:
        """Execute Jupyter notebook for visualization.

        Returns
        -------
        bool
            True if notebook executed successfully, False otherwise.
        """
        if not self.notebook_path.exists():
            print(f"✘ Notebook not found: {self.notebook_path}")
            return False

        print(f"\n{'=' * 60}")
        print("▶ Running visualization notebook...")
        print(f"{'=' * 60}")

        start_time = time.time()

        try:
            # Use nbconvert to execute notebook
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "jupyter",
                    "nbconvert",
                    "--to",
                    "notebook",
                    "--execute",
                    "--inplace",
                    str(self.notebook_path),
                ],
                cwd=self.base_dir,
                check=True,
                capture_output=True,
                text=True,
            )

            elapsed = time.time() - start_time
            print(f"✔ Notebook executed successfully in {elapsed:.1f}s")
            return True

        except subprocess.CalledProcessError as e:
            elapsed = time.time() - start_time
            print(f"✘ Notebook execution failed after {elapsed:.1f}s")
            print(f"Error: {e.stderr}")
            return False
        except FileNotFoundError:
            print("✘ Jupyter not found. Install with: pip install jupyter nbconvert")
            return False

    def run_full_pipeline(
        self,
        skip_generator: bool = False,
        skip_finder: bool = False,
        skip_analyzer: bool = False,
        with_visualization: bool = False,
    ) -> bool:
        """Run the complete pipeline.

        Parameters
        ----------
        skip_generator : bool, optional
            Skip generator step, by default False.
        skip_finder : bool, optional
            Skip finder step, by default False.
        skip_analyzer : bool, optional
            Skip analyzer step, by default False.
        with_visualization : bool, optional
            Run visualization notebook, by default False.

        Returns
        -------
        bool
            True if all steps completed successfully, False otherwise.
        """
        print("╔" + "=" * 58 + "╗")
        print("║" + " " * 10 + "MarsCONE Analysis Pipeline" + " " * 22 + "║")
        print("╚" + "=" * 58 + "╝")

        start_time = time.time()
        results = {}

        # Step 1: Generator
        if not skip_generator:
            results["generator"] = self.run_module(self.generator_dir, "Generator")
            if not results["generator"]:
                print("\n✘ Pipeline stopped: Generator failed")
                return False
        else:
            print("\n⊘ Skipping Generator step")

        # Step 2: Finder
        if not skip_finder:
            results["finder"] = self.run_module(self.finder_dir, "Finder")
            if not results["finder"]:
                print("\n✘ Pipeline stopped: Finder failed")
                return False
        else:
            print("\n⊘ Skipping Finder step")

        # Step 3: Analyzer
        if not skip_analyzer:
            results["analyzer"] = self.run_module(self.analyzer_dir, "Analyzer")
            if not results["analyzer"]:
                print("\n✘ Pipeline stopped: Analyzer failed")
                return False
        else:
            print("\n⊘ Skipping Analyzer step")

        # Step 4: Visualization (optional)
        if with_visualization:
            results["visualization"] = self.run_notebook()

        # Summary
        total_time = time.time() - start_time
        print(f"\n{'=' * 60}")
        print("Pipeline Summary:")
        print(f"{'=' * 60}")

        for step, success in results.items():
            status = "✔ PASSED" if success else "✘ FAILED"
            print(f"  {step.capitalize():20s} {status}")

        print(f"\n⏱ Total execution time: {total_time:.1f}s")

        all_success = all(results.values())
        if all_success:
            print("\n✔ Pipeline completed successfully!")
        else:
            print("\n✘ Pipeline completed with errors")

        return all_success


def main():
    """Parse arguments and run pipeline."""
    parser = argparse.ArgumentParser(
        description="Run MarsCONE analysis pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_pipeline.py                     # Run full pipeline
  python run_pipeline.py --skip-generator    # Skip generator step
  python run_pipeline.py --only-analyzer     # Run only analyzer
  python run_pipeline.py --with-viz          # Include visualization
        """,
    )

    parser.add_argument(
        "--skip-generator",
        action="store_true",
        help="Skip generator step (use existing transects/profiles)",
    )

    parser.add_argument(
        "--skip-finder",
        action="store_true",
        help="Skip finder step (use existing feature points)",
    )

    parser.add_argument(
        "--skip-analyzer", action="store_true", help="Skip analyzer step"
    )

    parser.add_argument(
        "--only-generator", action="store_true", help="Run only generator step"
    )

    parser.add_argument(
        "--only-finder", action="store_true", help="Run only finder step"
    )

    parser.add_argument(
        "--only-analyzer", action="store_true", help="Run only analyzer step"
    )

    parser.add_argument(
        "--with-viz",
        action="store_true",
        help="Run visualization notebook after analysis",
    )

    args = parser.parse_args()

    # Handle "only" flags
    if args.only_generator:
        args.skip_finder = True
        args.skip_analyzer = True
    elif args.only_finder:
        args.skip_generator = True
        args.skip_analyzer = True
    elif args.only_analyzer:
        args.skip_generator = True
        args.skip_finder = True

    # Initialize and run pipeline
    base_dir = Path(__file__).parent
    runner = PipelineRunner(base_dir)

    success = runner.run_full_pipeline(
        skip_generator=args.skip_generator,
        skip_finder=args.skip_finder,
        skip_analyzer=args.skip_analyzer,
        with_visualization=args.with_viz,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
