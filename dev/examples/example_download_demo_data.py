#!/usr/bin/env python3
"""Example: Download and prepare demo dataset for MarsCONE.

This example demonstrates how to download the test dataset
required to run MarsCONE analysis.

Usage:
    python example_download_demo_data.py
"""

import sys
from pathlib import Path

DEFAULT_URL = "https://zenodo.org/records/17885902/files/test_set.zip?download=1"
DEFAULT_DATA_DIR = "./demo_data"


def main():
    """Download and extract demo dataset."""
    repo_root = Path(__file__).parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    # Import from the parent directory
    import importlib.util
    spec = importlib.util.spec_from_file_location("download_demo_data", repo_root / "download_demo_data.py")
    download_demo_data = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(download_demo_data)
    download_file = download_demo_data.download_file
    extract_zip = download_demo_data.extract_zip

    data_dir = Path(DEFAULT_DATA_DIR).resolve()
    zip_path = data_dir / "test_set.zip"

    print(f"Demo dataset will be downloaded to: {data_dir}")
    print(f"URL: {DEFAULT_URL}")

    # Download
    download_file(DEFAULT_URL, zip_path)

    # Extract
    extract_zip(zip_path, data_dir, remove_zip=True)

    print("\nDemo data ready!")
    print(f"Data location: {data_dir}")
    print("You can now run MarsCONE analysis on this demo dataset.")


if __name__ == "__main__":
    main()
