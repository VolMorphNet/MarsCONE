#!/usr/bin/env python3
"""
download_demo_data.py

Download and unpack the MarsCONE demo dataset (test_set.zip)
into the local `data/` directory.

Usage (from repository root):

    python download_demo_data.py
    python download_demo_data.py --data-dir ./data --url https://zenodo.org/records/17885902/files/test_set.zip?download=1
"""

import argparse
import os
from pathlib import Path
import shutil
import sys
import urllib.request
import zipfile


# TODO: replace this with the actual URL of your ZIP file
DEFAULT_URL = "https://zenodo.org/records/17885902/files/test_set.zip?download=1"
DEFAULT_DATA_DIR = "data"
ZIP_NAME = "test_set.zip"


def download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"✔ Downloading demo data from:\n  {url}")
    try:
        with urllib.request.urlopen(url) as response, open(dest, "wb") as out_file:
            shutil.copyfileobj(response, out_file)
    except Exception as e:
        print(f"✘ Download failed: {e}")
        if dest.exists():
            dest.unlink()
        sys.exit(1)
    print(f"✔ Saved ZIP to: {dest}")


def extract_zip(zip_path: Path, target_dir: Path, remove_zip: bool = True) -> None:
    """Extract a ZIP archive into target_dir."""
    print(f"✔ Extracting {zip_path.name} to: {target_dir}")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(target_dir)
    except zipfile.BadZipFile as e:
        print(f"✘ Invalid ZIP file: {e}")
        sys.exit(1)

    if remove_zip:
        zip_path.unlink(missing_ok=True)
        print(f"✔ Removed ZIP file: {zip_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download and unpack the MarsCONE demo dataset (test_set.zip)."
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"URL of test_set.zip (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--data-dir",
        default=DEFAULT_DATA_DIR,
        help=f"Target data directory (default: {DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--keep-zip",
        action="store_true",
        help="Keep the downloaded ZIP file instead of deleting it after extraction.",
    )

    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    zip_path = data_dir / ZIP_NAME

    print(f"Target data directory: {data_dir}")

    # Quick safety check: warn if test_set already exists
    test_set_dir = data_dir / "test_set"
    if test_set_dir.exists():
        print(f"Detected existing directory: {test_set_dir}")
        print("Existing files will be left as-is, but extracted demo data may overwrite files with the same names.")
        print("If you want a clean demo, consider removing `data/test_set` first.\n")

    download_file(args.url, zip_path)
    extract_zip(zip_path, data_dir, remove_zip=not args.keep_zip)

    print("\n✔ Demo dataset ready.")
    print(f"You should now have: {test_set_dir}")
    print("You can run MarsCONE using this demo as described in the README.")


if __name__ == "__main__":
    main()