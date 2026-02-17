"""Elevation profile extraction from DEM data.

Samples DEM rasters along transects to generate elevation profiles
for cone morphometric analysis.
"""

import os
import warnings
from os import makedirs
from os.path import join

import geopandas as gpd
import numpy as np
import shapely
from osgeo import gdal
from shapely.geometry import Point
from tqdm import tqdm

warnings.filterwarnings("ignore", category=shapely.errors.ShapelyDeprecationWarning)

GREEN = "\033[92m"


def generate_profiles(config):  # pylint: disable=too-many-locals,too-many-statements
    """Generate elevation profiles from DEM along transects.

    Samples DEM raster values at regular intervals along each transect
    to create slope and elevation profiles.

    Parameters
    ----------
    config : dict
        Configuration dictionary with paths and parameters.
    """
    base = config["paths"]["base"]
    db_path = join(base, config["paths"]["db"])
    dem_dir = join(base, config["paths"]["output"]["dem_cropped"])
    slope_dir = join(base, config["paths"]["output"]["dem_slope"])
    transects_layer = config["db_layers"]["transects"]
    profiles_layer = config["db_layers"]["profiles"]
    crs = config["crs"]
    resolution = config["parameters"]["profile_resolution"]

    gdf = gpd.read_file(db_path, layer=transects_layer).to_crs(crs)

    profiles = []

    for idx, row in tqdm(
        gdf.iterrows(), total=len(gdf), desc="... generating profiles"
    ):
        transect_id = row.get("id", idx + 1)
        line = row.geometry

        cone_id_raw = str(row.get("cone_id", transect_id))
        # We separate the ID from the angle, e.g. 12_45deg -> 12
        if "_" in cone_id_raw and cone_id_raw.rsplit("_", maxsplit=1)[-1].endswith(
            "deg"
        ):
            cone_id = cone_id_raw.rsplit("_", maxsplit=1)[0]
        else:
            cone_id = cone_id_raw

        orientation = row.get("orientation", None)

        dem_file = join(dem_dir, f"cone_{cone_id}_dem.tif")
        slope_file = join(slope_dir, f"cone_{cone_id}_slope.tif")

        if not os.path.exists(dem_file) or not os.path.exists(slope_file):
            print(f"Missing files for cone {cone_id}: {dem_file} or {slope_file}")
            continue

        dem = gdal.Open(dem_file)
        slope = gdal.Open(slope_file)
        if not dem or not slope:
            continue

        arr_dem = dem.GetRasterBand(1).ReadAsArray()
        arr_slope = slope.GetRasterBand(1).ReadAsArray()
        nodata = dem.GetRasterBand(1).GetNoDataValue()
        gt = dem.GetGeoTransform()

        dist = 0
        while dist < line.length:
            pt = line.interpolate(dist)
            col = int((pt.x - gt[0]) / gt[1])
            row = int((gt[3] - pt.y) / abs(gt[5]))

            if 0 <= row < arr_dem.shape[0] and 0 <= col < arr_dem.shape[1]:
                elev = arr_dem[row, col]
                slope_val = arr_slope[row, col]
                if elev == nodata:
                    elev = np.nan
                profiles.append(
                    {
                        "transect_id": transect_id,
                        "cone_id": cone_id,
                        "distance": dist,
                        "x_geo": pt.x,
                        "y_geo": pt.y,
                        "elevation": elev,
                        "slope": slope_val,
                        "geometry": Point(pt.x, pt.y),
                        "orientation": orientation,
                    }
                )
            dist += resolution

    if not profiles:
        print("No profiles generated.")
        return

    profiles_gdf = gpd.GeoDataFrame(profiles, crs=crs)
    profiles_gdf.to_file(db_path, layer=profiles_layer, driver="GPKG", overwrite="YES")
    print(f"✔ Saved {len(profiles_gdf)} profile points to layer '{profiles_layer}'")

    out_csv_dir = join(base, "output/generator/profiles/whole")
    makedirs(out_csv_dir, exist_ok=True)

    for transect_id, group in profiles_gdf.groupby("transect_id"):
        group.drop(columns="geometry").to_csv(
            join(out_csv_dir, f"profile_{transect_id}.csv"),
            sep=";",
            index=False,
            encoding="utf-8",
        )

    print(f"✔ {GREEN}Exported profiles as individual CSV files to {out_csv_dir}")
