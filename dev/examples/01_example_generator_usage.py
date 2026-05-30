#!/usr/bin/env python3
"""Example: Run MarsCONE Generator to create analysis inputs.

This example demonstrates the complete pipeline for preparing data:
1. DEM cropping
2. Transect generation
3. Profile creation

Prerequisites:
- Input DEM rasters in data/input/dem/
- Input cone geometries (shapefile or GeoPackage)
- Proper configuration in config.json

Usage:
    python 01_example_generator_usage.py

Note: Run from the repository root directory (dev/).
Order: Step 1 of 3. Run this before finder and analyzer.
"""

import json
from pathlib import Path

# Get the repository root (dev folder)
REPO_ROOT = Path(__file__).parent.parent


def show_pipeline_overview():
    """Display MarsCONE pipeline overview."""
    print("MarsCONE Data Generation Pipeline")
    print("=" * 50)
    print()
    print("Step 1: DEM Cropping")
    print("-" * 50)
    print("  Crops DEM rasters based on input cone geometries.")
    print("  Generates slope maps for cone locations.")
    print()
    print("Step 2: Transect Generation")
    print("-" * 50)
    print("  Creates radial transects from cone centers.")
    print("  Default: 4 transects per cone at 90° angles.")
    print()
    print("Step 3: Profile Extraction")
    print("-" * 50)
    print("  Samples DEM values along transects at regular intervals.")
    print("  Creates elevation and slope profiles for each transect.")
    print()


def check_input_data():
    """Verify that required input data exists."""
    config_path = REPO_ROOT / "generator-py" / "config.json"

    if not config_path.exists():
        print("Error: Config file not found")
        return False

    try:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)

        # Resolve paths relative to the config file's parent directory (generator-py/)
        config_dir = config_path.parent
        base_path = config_dir / config.get("paths", {}).get("base", ".")

        # Resolve to absolute path
        base_path = base_path.resolve()

        dem_dir = base_path / config.get("paths", {}).get("input", {}).get(
            "dem", "data/input/dem"
        )

        print("Configuration check:")
        print(f"  Config path: {config_path}")
        print(f"  Config dir: {config_dir}")
        print("  Base path (relative): ../data/test_set")
        print(f"  Base path (absolute): {base_path}")
        print(f"  DEM input: {dem_dir}")
        print(f"  DEM exists: {dem_dir.exists()}")

        return True
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error in configuration: {e}")
        return False


def main():
    """Run generator usage example."""
    show_pipeline_overview()
    print("Configuration Check")
    print("=" * 50)
    check_input_data()

    print()
    print("Execution order:")
    print("  1) Generator (this script)")
    print("  2) Finder (requires generator output)")
    print("  3) Analyzer (requires finder output)")

    print()
    print("To run the complete pipeline:")
    print("  cd generator-py")
    print("  python main.py")
    print()
    print("Or run individual steps:")
    print("  python -c 'import pgen; pgen.get_DEM(config)'")
    print("  python -c 'import pgen; pgen.generate_transects(config)'")
    print("  python -c 'import pgen; pgen.generate_profiles(config)'")


if __name__ == "__main__":
    main()
