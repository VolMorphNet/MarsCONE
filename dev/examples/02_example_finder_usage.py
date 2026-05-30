#!/usr/bin/env python3
"""Example: Run MarsCONE Finder to detect cone features.

This example demonstrates how to use the MarsCONE Finder module
to detect characteristic points (bottom, top, center) on cone profiles.

Prerequisites:
- Demo data downloaded
- Profile data generated

Usage:
    python 02_example_finder_usage.py

Note: Run from the repository root directory (dev/).
Order: Step 2 of 3. Requires generator output.
"""

import json
from pathlib import Path

# Get the repository root (dev folder)
REPO_ROOT = Path(__file__).parent.parent


def check_setup():
    """Check if setup is ready."""
    config_path = REPO_ROOT / "finder-py" / "config.json"
    if not config_path.exists():
        print("Error: Finder configuration not found")
        return False

    try:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)

        # Resolve paths relative to config file's directory
        config_dir = config_path.parent
        base_path = config_dir / config.get("paths", {}).get("base", ".")
        base_path = base_path.resolve()

        input_profiles_rel = (
            config.get("paths", {})
            .get("input", {})
            .get(
                "profiles",
                "output/generator/profiles/whole",
            )
        )
        input_profiles = (base_path / input_profiles_rel).resolve()

        print("✓ Finder configuration loaded")
        print(f"  Config path: {config_path}")
        print(f"  Base path (absolute): {base_path}")
        print(f"  Input profiles (relative): {input_profiles_rel}")
        print(f"  Input profiles (absolute): {input_profiles}")
        print(f"  Profiles exist: {input_profiles.exists()}")
        return True
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error reading configuration: {e}")
        return False


def main():
    """Show finder usage example."""
    print("MarsCONE Finder Example")
    print("=" * 40)

    if not check_setup():
        return

    print("\nExecution order:")
    print("  1) Generator (must be run first)")
    print("  2) Finder (this script)")
    print("  3) Analyzer (requires finder output)")

    print("\nTo run the finder:")
    print("  cd finder-py")
    print("  python main.py")
    print("\nThe finder will:")
    print("  - Load elevation profiles")
    print("  - Detect bottom points (lowest elevations)")
    print("  - Detect top points (highest elevations)")
    print("  - Detect center points")
    print("  - Classify by transect direction (N/S/E/W)")
    print("  - Export results as GeoPackage and CSV")
    print("\nOutput files:")
    print("  - results/finder_method.csv")
    print("  - results/finder_results.gpkg")


if __name__ == "__main__":
    main()
