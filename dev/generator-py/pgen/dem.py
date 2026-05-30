"""
DEM processing module for cropping and slope calculation.

Handles GIS raster operations including cropping DEM files using
input geometries and calculating slope gradients.
"""

import glob
import os
import sys
from os.path import join

import geopandas as gpd
from osgeo import gdal, gdalconst
from tqdm import tqdm

IS_GUI = "--gui" in sys.argv

RED = "\033[91m"
RESET = "\033[0m"

gdal.UseExceptions()
gdal.SetConfigOption("GDAL_NUM_THREADS", "ALL_CPUS")
gdal.SetConfigOption("CPL_TMPDIR", "/tmp")
gdal.SetConfigOption("GDAL_CACHEMAX", "512")
gdal.SetConfigOption("VSI_CACHE", "TRUE")
gdal.SetConfigOption("VSI_CACHE_SIZE", "32000000")

try:
    gdal.SetConfigOption("GDAL_USE_OPENCL", "TRUE")
except (RuntimeError, ValueError):
    pass


def get_DEM(
    config,
):  # pylint: disable=invalid-name,too-many-locals,too-many-branches,too-many-statements
    """Crop DEM rasters using input cone geometries.

    Extracts DEM tiles for each cone location and calculates slope gradients.

    Parameters
    ----------
    config : dict
        Configuration dictionary with paths and parameters.
    """
    base = config["paths"]["base"]
    dem_dir = join(base, config["paths"]["input"]["dem"])
    dem_input_files = glob.glob(join(dem_dir, "*.tif"))

    if not dem_input_files:
        print("No DEM files found in the input directory.")
        return

    dem_input_file = dem_input_files[0]
    dem_out_dir = join(base, config["paths"]["output"]["dem_cropped"])
    slope_out_dir = join(base, config["paths"]["output"]["dem_slope"])
    os.makedirs(dem_out_dir, exist_ok=True)
    os.makedirs(slope_out_dir, exist_ok=True)

    db_path = join(base, config["paths"]["db"])
    crs = config["crs"]
    mode = config.get("mode", "masks")  # default to 'masks'

    if mode == "points":
        gdf = gpd.read_file(db_path, layer=config["db_layers"]["points"]).to_crs(crs)
        buffer_width = config["parameters"].get("buffer_width", 100)
        gdf["geometry"] = gdf.geometry.buffer(buffer_width / 2)

        found_id_col = False
        for col_name in gdf.columns:
            if col_name.lower() == "id":
                if col_name != "id":
                    gdf = gdf.rename(columns={col_name: "id"})
                found_id_col = True
                break

        if not found_id_col:
            gdf["id"] = (gdf.index + 1).astype(int)

        gdf["id"] = gdf["id"].astype(str)
        cones = gdf
        cones_layer = "temp_cones_buffer"
        cones.to_file(db_path, layer=cones_layer, driver="GPKG", overwrite="YES")
    else:
        cones_layer = config["db_layers"]["masks"]
        cones = gpd.read_file(db_path, layer=cones_layer).to_crs(crs)

        found_id_col = False
        for col_name in cones.columns:
            if col_name.lower() == "id":
                if col_name != "id":
                    cones = cones.rename(columns={col_name: "id"})
                found_id_col = True
                break
        if not found_id_col:
            print(
                f"{RED}Warning: No 'id' or 'Id' column in layer "
                f"'{cones_layer}'. DataFrame index used as ID.{RESET}"
            )
            cones["id"] = (cones.index + 1).astype(int)

        cones["id"] = cones["id"].astype(str)

    # Get NODATA info
    sample = gdal.Open(dem_input_file, gdal.GA_ReadOnly)
    src_nodata = sample.GetRasterBand(1).GetNoDataValue()
    dst_nodata = -9999
    sample = None

    with tqdm(
        total=len(cones), desc="... clipping DEM by cones", disable=IS_GUI
    ) as progress:
        for _, row in cones.iterrows():
            cone_id = row["id"]
            cone_geom = f"id='{cone_id}'"

            out_dem = join(dem_out_dir, f"cone_{cone_id}_dem.tif")
            out_slope = join(slope_out_dir, f"cone_{cone_id}_slope.tif")

            options = gdal.WarpOptions(
                format="GTiff",
                srcSRS=crs,
                dstSRS=crs,
                srcNodata=src_nodata,
                dstNodata=dst_nodata,
                cutlineDSName=db_path,
                cutlineLayer=cones_layer,
                cutlineWhere=cone_geom,
                cropToCutline=True,
                outputType=gdalconst.GDT_Float32,
            )

            dem_input = gdal.Open(dem_input_file, gdal.GA_ReadOnly)
            result = gdal.Warp(out_dem, dem_input, options=options)
            dem_input = None

            if result:
                gdal.DEMProcessing(out_slope, gdal.Open(out_dem), "slope")
            progress.update(1)
