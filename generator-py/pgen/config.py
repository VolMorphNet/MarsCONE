"""Configuration parsing utilities for pipeline parameter extraction."""

from os.path import join


def parse(cfg, fname):
    """Parse configuration and extract parameters for a specific function.

    Parameters
    ----------
    cfg : dict
        Configuration dictionary.
    fname : str
        Function name to extract parameters for.

    Returns
    -------
    tuple
        Extracted parameters for the specified function.
    """
    parser = _PARSERS.get(fname)
    if parser is None:
        raise KeyError(f"Unsupported config parser name: {fname}")
    return parser(cfg)


def _get_dem(cfg):
    base_path = cfg["paths"]["base"]
    mode = cfg.get("mode", "masks")
    cones_layer = (
        cfg["db_layers"]["points"] if mode == "points" else cfg["db_layers"]["masks"]
    )
    return (
        join(base_path, cfg["paths"]["input"]["dem"]),
        join(base_path, cfg["paths"]["output"]["dem_cropped"]),
        join(base_path, cfg["paths"]["output"]["dem_slope"]),
        join(base_path, cfg["paths"]["db"]),
        cones_layer,
        cfg["crs"],
    )


def _generate_transects(cfg):
    mode = cfg.get("mode", "masks")
    layer = (
        cfg["db_layers"]["points"] if mode == "points" else cfg["db_layers"]["masks"]
    )
    return (
        join(cfg["paths"]["base"], cfg["paths"]["db"]),
        cfg["crs"],
        layer,
        cfg["db_layers"]["transects"],
        cfg["parameters"]["transect_length"],
    )


def _generate_profiles(cfg):
    base_path = cfg["paths"]["base"]
    return (
        cfg["crs"],
        join(base_path, cfg["paths"]["output"]["dem_cropped"]),  # dem_path
        join(base_path, cfg["paths"]["output"]["dem_slope"]),  # slope_path
        join(base_path, cfg["paths"]["db"]),  # db
        cfg["db_layers"]["profiles"],  # profiles_layer
        cfg["db_layers"]["transects"],  # transects_layer
        cfg["parameters"]["profile_resolution"],  # resolution
    )


_PARSERS = {
    "get_DEM": _get_dem,
    "generate_transects": _generate_transects,
    "generate_profiles": _generate_profiles,
}
