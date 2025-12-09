import glob
import shutil
import geopandas as gpd
import shapely.ops
from os.path import exists, isdir, join, dirname
from os import makedirs, remove

RED = "\033[91m"
RESET = "\033[0m"

def init(config):
    check_paths(config["paths"])
    mode = detect_mode(config)
    config["mode"] = mode 
    read_input_features(config, mode)
    read_transects(config)
    return True


def detect_mode(config):
    mode = config["parameters"].get("mode", "auto")
    base = config["paths"]["base"]
    input_paths = config["paths"]["input"]

    if mode == "auto":
        has_masks = any(glob.glob(join(base, input_paths["masks"], "*.shp")))
        has_points = any(glob.glob(join(base, input_paths["points"], "*.shp")))

        if has_masks:
            return "masks"
        elif has_points:
            return "points"
        else:
            raise Exception("No valid input shapefiles found in 'masks' or 'points'.")
    elif mode in ["masks", "points"]:
        return mode
    else:
        raise ValueError(f"Unknown mode: {mode}")


def check_paths(config_paths):
    base = config_paths["base"]
    check_base_path(base)
    check_input_path(base, config_paths["input"])
    check_db_path(base, config_paths["db"])
    check_output_path(base, config_paths["output"])


def check_base_path(base):
    if not exists(base):
        raise Exception(
            1001,
            f"{RED}... paths error: base path cannot be located ({base}). Check config.json.{RESET}",
        )
    if not isdir(base):
        raise Exception(
            f"{RED}... paths error: base path ({base}) is not a directory. Check config.json.{RESET}",
        )


def check_input_path(base, input):
    if "transects" in input:
        tpath = join(base, input["transects"])
        if not exists(tpath):
            makedirs(tpath)

    paths = list(input.values())
    for path in paths:
        inpath = join(base, path)
        if not exists(inpath):
            raise Exception(
                f"{RED}... paths error: one of input paths cannot be located ({inpath}). Check config.json.{RESET}",
            )
        if not isdir(inpath):
            raise Exception(
                f"{RED}... paths error: one of input paths ({inpath}) is not a directory. Check config.json.{RESET}"
            )


def check_db_path(base, db):
    dbpath = join(base, db)
    if exists(dbpath):
        remove(dbpath)
    dir_name = dirname(dbpath)
    if not exists(dir_name):
        makedirs(dir_name)


def check_output_path(base, output):
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
        except:
            raise Exception(
                f"{RED}... paths error: there is a problem with one of output paths ({outpath}). Check config.json.{RESET}",
            )


def read_input_features(config, mode):
    if mode == "masks":
        read_masks(config)
    elif mode == "points":
        read_points(config)


def read_masks(config):
    base = config["paths"]["base"]
    path = join(base, config["paths"]["input"]["masks"])
    shapes = glob.glob(join(path, "*.shp"))
    if not shapes:
        raise Exception(f"... cannot find any mask SHP file ({path}).")

    gdf = gpd.read_file(shapes[0]).to_crs(config["crs"])
    gdf.to_file(
        join(base, config["paths"]["db"]),
        layer=config["db_layers"]["masks"],
        driver="GPKG",
    )


def read_points(config):
    base = config["paths"]["base"]
    path = join(base, config["paths"]["input"]["points"])
    shapes = glob.glob(join(path, "*.shp"))
    if not shapes:
        raise Exception(f"... cannot find any points SHP file ({path}).")

    gdf = gpd.read_file(shapes[0]).to_crs(config["crs"])
    gdf.to_file(
        join(base, config["paths"]["db"]),
        layer=config["db_layers"]["points"],
        driver="GPKG",
    )


def read_transects(config):
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
            print(f"{RED}... no transects SHP file found in {transects_path}. Will generate from scratch.{RESET}")
