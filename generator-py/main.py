"""
MarsCONE Generator CLI

This module initializes and runs the MarsCONE data processing pipeline,
including DEM cropping, transect generation, and profile creation.

Authors: Jakub Śledziowski, Bartosz Pieterek, Thomas Jones
License: MIT
"""

import json
import sys

import pgen

IS_GUI = "--gui" in sys.argv

YELLOW = "\033[93m"
RESET = "\033[0m"
RED = "\033[91m"
GREEN = "\033[92m"


def main():
    """Run the MarsCONE generator pipeline."""
    with open("config.json", encoding="utf-8") as jsonfile:
        config = json.load(jsonfile)

    try:
        print(f"{YELLOW}Initializing data structures...{RESET}")
        pgen.init(config)

        mode = config["mode"]
        print(f"{YELLOW}Running in mode: {mode.upper()}{RESET}")

        print(
            f"{YELLOW}Cropping DEM rasters using input geometries "
            f"({mode})...{RESET}"
        )
        pgen.get_DEM(config)

        source_label = "points" if mode == "points" else "mask centroids"
        print(f"{YELLOW}Generating transects from {source_label}...{RESET}")
        pgen.generate_transects(config)

        print(f"{YELLOW}Generating profiles from DEM and transects...{RESET}")
        pgen.generate_profiles(config)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"{RED}{type(exc).__name__}: {exc}{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
