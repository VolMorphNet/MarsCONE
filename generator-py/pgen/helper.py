"""Helper functions for pipeline initialization and configuration.

Handles path validation, mode detection, and input feature loading.
"""

import glob
import shutil
from os import makedirs, remove
from os.path import dirname, exists, isdir, join

import geopandas as gpd

RED = "\033[91m"
RESET = "\033[0m"


def init(config):
    """Initialize pipeline by validating paths and loading input data.

    Parameters
    ----------
    config : dict
        Configuration dictionary.

    Returns
    -------
    bool
        True if initialization successful.
    """
    check_paths(config["paths"])
    mode = detect_mode(config)
    config["mode"] = mode
    read_input_features(config, mode)
    read_transects(config)
    return True


def detect_mode(config):
    """Detect analysis mode (masks or points) from input data structure.

    Parameters
    ----------
    config : dict
        Configuration dictionary.

    Returns
    -------
    str
        Detected mode: 'masks' or 'points'.
    """
    mode = config["parameters"].get("mode", "auto")
    base = config["paths"]["base"]
    input_paths = config["paths"]["input"]

    if mode == "auto":
        has_masks = any(glob.glob(join(base, input_paths["masks"], "*.shp")))
        has_points = any(glob.glob(join(base, input_paths["points"], "*.shp")))

        if has_masks:
            return "masks"
        if has_points:
            return "points"
        raise FileNotFoundError(
            "No valid input shapefiles found in 'masks' or 'points'."
        )

    if mode in ["masks", "points"]:
        return mode

    raise ValueError(f"Unknown mode: {mode}")


def check_paths(config_paths):
    """Validate base, input, database, and output paths."""
    base = config_paths["base"]
    check_base_path(base)
    check_input_path(base, config_paths["input"])
    check_db_path(base, config_paths["db"])
    check_output_path(base, config_paths["output"])


def check_base_path(base):
    """Validate base path existence and directory type."""
    if not exists(base):
        raise FileNotFoundError(
            f"{RED}... paths error: base path cannot be located ({base}). "
            f"Check config.json.{RESET}"
        )
    if not isdir(base):
        raise NotADirectoryError(
            f"{RED}... paths error: base path ({base}) is not a directory. "
            f"Check config.json.{RESET}"
        )


def check_input_path(base, input_paths):
    """Validate input paths and create optional transects directory."""
    if "transects" in input_paths:
        tpath = join(base, input_paths["transects"])
        if not exists(tpath):
            makedirs(tpath)

    paths = list(input_paths.values())
    for path in paths:
        inpath = join(base, path)
        if not exists(inpath):
            raise FileNotFoundError(
                f"{RED}... paths error: one of input paths cannot be located "
                f"({inpath}). Check config.json.{RESET}"
            )
        if not isdir(inpath):
            raise NotADirectoryError(
                f"{RED}... paths error: one of input paths ({inpath}) is not "
                f"a directory. Check config.json.{RESET}"
            )


def check_db_path(base, db):
    """Prepare database path by removing any existing file."""
    dbpath = join(base, db)
    if exists(dbpath):
        remove(dbpath)
    dir_name = dirname(dbpath)
    if not exists(dir_name):
        makedirs(dir_name)


def check_output_path(base, output):
    """Validate output paths and ensure directories are ready."""
    paths = list(output.values())
    for path in paths:
        outpath = join(base, path)
        try:
            makedirs(outpath)
        except FileExistsError:
            files = glob.glob(join(outpath, "*"))
            for file in files:
                if isdir(file):
                    shutil.rmtree(file)
                else:
                    remove(file)
        except Exception as exc:
            raise RuntimeError(
                f"{RED}... paths error: there is a problem with one of output "
                f"paths ({outpath}). Check config.json.{RESET}"
            ) from exc


def read_input_features(config, mode):
    """Load input features based on detected mode."""
    if mode == "masks":
        read_masks(config)
    elif mode == "points":
        read_points(config)


def read_masks(config):
    """Read mask polygons from input directory into GeoPackage."""
    base = config["paths"]["base"]
    path = join(base, config["paths"]["input"]["masks"])
    shapes = glob.glob(join(path, "*.shp"))
    if not shapes:
        raise FileNotFoundError(f"... cannot find any mask SHP file ({path}).")

    gdf = gpd.read_file(shapes[0]).to_crs(config["crs"])
    gdf.to_file(
        join(base, config["paths"]["db"]),
        layer=config["db_layers"]["masks"],
        driver="GPKG",
    )


def read_points(config):
    """Read point features from input directory into GeoPackage."""
    base = config["paths"]["base"]
    path = join(base, config["paths"]["input"]["points"])
    shapes = glob.glob(join(path, "*.shp"))
    if not shapes:
        raise FileNotFoundError(f"... cannot find any points SHP file ({path}).")

    gdf = gpd.read_file(shapes[0]).to_crs(config["crs"])
    gdf.to_file(
        join(base, config["paths"]["db"]),
        layer=config["db_layers"]["points"],
        driver="GPKG",
    )


def read_transects(config):
    """Load pre-calculated transects if configured."""
    if (
        "transects" in config["paths"]["input"]
        and config["parameters"].get("use_precalculated_transects", False)
        and isdir(join(config["paths"]["base"], config["paths"]["input"]["transects"]))
    ):
        base = config["paths"]["base"]
        transects_path = join(base, config["paths"]["input"]["transects"])
        shapes = glob.glob(join(transects_path, "*.shp"))

        if shapes:
            transects = gpd.read_file(shapes[0]).to_crs(config["crs"])
            for key in ["fid", "id"]:
                if key in transects.columns:
                    transects[key] = transects[key].astype("int64")

            transects.to_file(
                join(base, config["paths"]["db"]),
                layer=config["db_layers"]["transects"],
                driver="GPKG",
            )
        else:
            print(
                f"{RED}... no transects SHP file found in {transects_path}. "
                f"Will generate from scratch.{RESET}"
            )
