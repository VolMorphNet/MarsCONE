# shape.py for MarsCONE Finder
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from os.path import join

def extract_extreme_points(config):
    base = config["paths"]["base"]
    db_path = join(base, config["paths"]["db"])
    profiles_layer = config["db_layers"]["profiles"]
    points_layer = config["db_layers"]["points"]

    gdf = gpd.read_file(db_path, layer=profiles_layer)
    points = []

    grouped = gdf.groupby("transect_id")
    for transect_id, group in grouped:
        group_sorted = group.sort_values("distance")
        half = int(len(group_sorted) / 2)
        direction = _infer_direction(group_sorted)

        # Split into left/right or north/south
        first_half = group_sorted.iloc[:half]
        second_half = group_sorted.iloc[half:]

        # Find min/max in each half
        bottom_1 = first_half.loc[first_half["elevation"].idxmin()]
        top_1 = first_half.loc[first_half["elevation"].idxmax()]
        bottom_2 = second_half.loc[second_half["elevation"].idxmin()]
        top_2 = second_half.loc[second_half["elevation"].idxmax()]

        center_idx = (group_sorted["distance"] - group_sorted["distance"].max()/2).abs().idxmin()
        center = group_sorted.loc[center_idx]

        cone_id = bottom_1["cone_id"]

        labels = ("{}_bottom", "{}_top")
        if direction == "EW":
            pairs = zip(["W", "W", "E", "E"], [bottom_1, top_1, bottom_2, top_2])
        else:
            pairs = zip(["N", "N", "S", "S"], [bottom_1, top_1, bottom_2, top_2])

        for prefix, row in pairs:
            points.append({
                "type": f"{prefix}_{'bottom' if row['elevation'] == min(bottom_1['elevation'], bottom_2['elevation']) else 'top'}",
                "transect_id": transect_id,
                "cone_id": cone_id,
                "elevation": row["elevation"],
                "slope": row["slope"],
                "distance": row["distance"],
                "geometry": Point(row["x_geo"], row["y_geo"])
            })

        # Add center point
        points.append({
            "type": "C",
            "transect_id": transect_id,
            "cone_id": cone_id,
            "elevation": center["elevation"],
            "slope": center["slope"],
            "distance": center["distance"],
            "geometry": Point(center["x_geo"], center["y_geo"])
        })

    points_gdf = gpd.GeoDataFrame(points, crs=gdf.crs)
    points_gdf.to_file(db_path, layer=points_layer, driver="GPKG", overwrite="YES")
    print(f"Saved {len(points_gdf)} points to layer '{points_layer}'")

def _infer_direction(group):
    x_span = group["x_geo"].max() - group["x_geo"].min()
    y_span = group["y_geo"].max() - group["y_geo"].min()
    return "EW" if x_span > y_span else "NS"
