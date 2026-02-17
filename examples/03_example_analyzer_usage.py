#!/usr/bin/env python3
"""Example: Run MarsCONE Analyzer on sample data.

This example shows how to use the MarsCONE Analyzer to perform
morphometric analysis on cone-like landforms.

Prerequisites:
- Download demo data using download_demo_data.py
- Configure config.json with correct paths

Usage:
    python 03_example_analyzer_usage.py

Note: Run from the repository root directory (dev/).
Order: Step 3 of 3. Requires finder output.
"""

import json
import sys
from pathlib import Path

# Get the repository root (dev folder)
REPO_ROOT = Path(__file__).parent.parent

# Add analyzer module to path
sys.path.insert(0, str(REPO_ROOT / "analyzer-py"))


def check_prerequisites():
    """Check if required configuration and data exist."""
    config_path = REPO_ROOT / "analyzer-py" / "config.json"
    if not config_path.exists():
        print(f"Error: Configuration file not found at {config_path}")
        print("Please configure config.json with correct paths.")
        return False

    try:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)

        # Resolve paths relative to config file's directory
        config_dir = config_path.parent
        base_path = config_dir / config.get("paths", {}).get("base", ".")
        base_path = base_path.resolve()

        print(f"✓ Configuration loaded from {config_path}")
        print(f"  Base path (absolute): {base_path}")
        return True
    except json.JSONDecodeError as e:
        print(f"Error reading config.json: {e}")
        return False


def main():
    """Run analysis example."""
    print("MarsCONE Analyzer Example")
    print("=" * 40)

    if not check_prerequisites():
        print("\nPlease ensure:")
        print("1. Demo data is downloaded")
        print("2. config.json is properly configured")
        print("3. Generator and Finder were run in order")
        return

    print("\nExecution order:")
    print("  1) Generator")
    print("  2) Finder")
    print("  3) Analyzer (this script)")

    print("\nTo run the analyzer:")
    print("  cd analyzer-py")
    print("  python main.py")
    print("\nThe analyzer will:")
    print("  - Load configuration from config.json")
    print("  - Process profile points and detected features")
    print("  - Calculate cone morphometry")
    print("  - Export results to CSV and GeoPackage")


if __name__ == "__main__":
    main()
