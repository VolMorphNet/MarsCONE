"""Data generation module for DEM processing and profile creation.

Orchestrates the MarsCONE processing pipeline: DEM cropping,
transect generation, and elevation profile extraction.
"""

from pgen.dem import get_DEM  # noqa: F401
from pgen.helper import init  # noqa: F401
from pgen.profile import generate_profiles  # noqa: F401
from pgen.transect import generate_transects  # noqa: F401

__all__ = [
    "get_DEM",
    "init",
    "generate_profiles",
    "generate_transects",
]

# from pgen.profile import crop_profiles
