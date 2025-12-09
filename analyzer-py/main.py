"""
MarsCONE Analyzer Module
------------------------
Performs morphometric and geometric analysis of cone-like landforms.
Calculates metrics such as height, width, volume, and shape,
and exports aggregated results as CSV and GeoPackage files.

Authors: Jakub Śledziowski, Bartosz Pieterek, Thomas Kuhn
License: MIT
"""

import os
import sys
import json
import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon
from shapely.affinity import translate
from os.path import join
from tqdm import tqdm
import numpy as np
import math
from skimage.measure import EllipseModel

YELLOW = "\033[93m"
RESET = "\033[0m"
RED = "\033[91m"
GREEN = "\033[92m"

def ellipse_to_polygon(cx: float,
                       cy: float,
                       major_diameter: float,
                       minor_diameter: float,
                       angle_deg: float,
                       n_points: int = 180) -> Polygon:
    """
    Approximates an ellipse as a Shapely polygon.

    Parameters
    ----------
    cx, cy : float
        Coordinates of the centre of the ellipse.
    major_diameter, minor_diameter : float
        Main and auxiliary axis diameters (not radii).
    angle_deg : float
        Main axis rotation in degrees, CCW from the X axis.
    n_points : int
        Number of vertices approximating an ellipse.

    Returns
    -------
    Polygon
    """
    a = major_diameter / 2.0
    b = minor_diameter / 2.0
    theta = np.linspace(0.0, 2.0 * np.pi, n_points)
    angle = np.deg2rad(angle_deg)

    cos_a = np.cos(angle)
    sin_a = np.sin(angle)

    x = cx + a * np.cos(theta) * cos_a - b * np.sin(theta) * sin_a
    y = cy + a * np.cos(theta) * sin_a + b * np.sin(theta) * cos_a

    coords = np.column_stack([x, y])
    return Polygon(coords)


def filter_iqr(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Rejects outliers based on distance from the centroid (IQR).

    Leaves all points if there are fewer than 4.
    """
    if len(gdf) < 4:
        return gdf

    x = gdf.geometry.x.values
    y = gdf.geometry.y.values

    cx = np.median(x)
    cy = np.median(y)
    dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)

    q25 = np.percentile(dist, 25)
    q75 = np.percentile(dist, 75)
    iqr = q75 - q25
    thresh = q75 + 1.5 * iqr

    mask = dist <= thresh
    return gdf[mask]

def angle_from_transect_id(tid: str):
    """
    Extract axis angle from transect_id, e.g. '12_45deg' -> 45 (mod 180 so that 45/225 share the same axis).
    """
    if not isinstance(tid, str):
        return None
    try:
        angle = int(tid.split("_")[1].replace("deg", ""))
        return angle % 180
    except Exception:
        return None

def main():
    hybrid_results = []
    with open("config.json", "r") as f:
        config = json.load(f)

    base = config["paths"]["base"]
    db_path = join(base, config["paths"]["db"])
    crs = config["shape"]["crs"]
    csv_sep = config["csv"].get("sep", ";")
    buffer = config.get("buffer_distance", 1.0)
    export_geojson = config.get("export_geojson", True)

    profiles_dir = join(base, config["paths"]["input"]["profiles"])
    points_file = join(base, config["paths"]["input"]["points"], "finder_method.csv")
    output_csv = join(base, config["paths"]["output"]["csv"])
    output_shapes_dir = join(base, config["paths"]["output"]["shapes"])
    cone_csv = join(base, "output/analyzer/cone_summary.csv")

    os.makedirs(output_shapes_dir, exist_ok=True)

    print(f"{YELLOW}✔ Reading profile points and detected features{RESET}")
    profiles = pd.concat(
        [pd.read_csv(join(profiles_dir, f), sep=csv_sep) for f in os.listdir(profiles_dir) if f.endswith(".csv")],
        ignore_index=True
    )
    gdf_profiles = gpd.GeoDataFrame(profiles, geometry=gpd.points_from_xy(profiles.x_geo, profiles.y_geo), crs=crs)

    features = pd.read_csv(points_file, sep=csv_sep)
    gdf_features = gpd.GeoDataFrame(features, geometry=gpd.points_from_xy(features.x_geo, features.y_geo), crs=crs)

    results = []

    grouped = gdf_features.groupby("transect_id")
    for transect_id, group in tqdm(grouped, desc="Analyzing profiles"):
        cone_id = group["cone_id"].iloc[0]
        subset = gdf_profiles[gdf_profiles["transect_id"] == transect_id].sort_values("distance")

        top = group[group["type"].str.contains("top")]
        bottom = group[group["type"].str.contains("bottom")]
        center = group[group["type"] == "C"]

        if top.empty or bottom.empty:
            continue

        top_elev = top["elevation"].mean()
        bottom_elev = bottom["elevation"].mean()
        height = top_elev - bottom_elev

        if len(bottom) >= 2:
            bottom_first = bottom.iloc[0]
            bottom_last = bottom.iloc[-1]

            bottom_width = ((bottom_last.x_geo - bottom_first.x_geo) ** 2 + (bottom_last.y_geo - bottom_first.y_geo) ** 2) ** 0.5
            width = round(bottom_width, 3)
        else:
            width = 0

        if len(top) >= 2:
            top_first = top.iloc[0]
            top_last = top.iloc[-1]
            top_width = ((top_last.x_geo - top_first.x_geo) ** 2 + (top_last.y_geo - top_first.y_geo) ** 2) ** 0.5
            top_width = round(top_width, 3)
        else:
            top_width = 0
            
        if not center.empty:
            center_elev = center["elevation"].mean()
            center_x = center["x_geo"].mean()
            center_y = center["y_geo"].mean()
            center_to_top_diff = top_elev - center_elev  
        else:
            center_elev = None  
            center_to_top_diff = None
            center_x = None
            center_y = None

        shape_class = None
        shape_threshold = config.get("classification", {}).get("shape_threshold", 0.5)

        if center_elev is not None:
            if abs(center_elev - top_elev) < shape_threshold:
                shape_class = "flat"
            elif center_elev < top_elev:
                shape_class = "concave"
            else:
                shape_class = "convex"

        results.append({
            "transect_id": transect_id,
            "cone_id": cone_id,
            "height": round(height, 3),
            "bottom_width": width,
            "top_width": top_width,
            "top_elev": round(top_elev, 3),
            "bottom_elev": round(bottom_elev, 3),
            "center_elev": center_elev,
            "center_x": center_x,
            "center_y": center_y,
            "center_to_top_diff": center_to_top_diff,
            "shape": shape_class
        })

        if export_geojson:
            group_out = group.copy()
            line = LineString(subset.geometry.tolist())
            shape_path = join(output_shapes_dir, f"cone_{cone_id}_{transect_id}.geojson")
            group_out["geometry_type"] = group_out["type"]
            group_out = pd.concat([
                group_out,
                gpd.GeoDataFrame([{"geometry": line, "geometry_type": "profile_line"}], crs=crs)
            ])
            group_out.to_file(shape_path, driver="GeoJSON")

    df_out = pd.DataFrame(results)
    df_out.to_csv(output_csv, sep=csv_sep, index=False, encoding="utf-8")
    print(f"{YELLOW}✔ Exported {len(df_out)} measurements to {output_csv}{RESET}")


    df_cone_base = df_out.groupby('cone_id').agg({
        'height': 'mean',
        'bottom_width': 'mean',
        'top_elev': 'mean',
        'bottom_elev': 'mean',
        'center_elev': 'mean',
        'center_to_top_diff': 'mean',
        "center_x": "mean",
        "center_y": "mean"
    }).reset_index()

    shape_mode = df_out.groupby("cone_id")["shape"].agg(lambda x: x.mode().iloc[0] if not x.mode().empty else None)
    df_cone_base["shape"] = shape_mode.values

    cone_metrics = []
    
    gdf_bottom = gdf_features[gdf_features["type"].str.contains("bottom", regex=True)].copy()
    gdf_top = gdf_features[gdf_features["type"].str.contains("top", regex=True)].copy()

    bottom_clean_list = []
    top_clean_list = []

    print(f"{YELLOW}✔ Calculating advanced morphometric parameters for each cone...{RESET}")
    for cone_id in tqdm(df_out["cone_id"].unique(), desc="Analyzing cone geometry"):
        bottom_points = gdf_bottom[gdf_bottom["cone_id"] == cone_id]
        top_points = gdf_top[gdf_top["cone_id"] == cone_id]
        
        bottom_clean = filter_iqr(bottom_points)
        top_clean = filter_iqr(top_points)

        bottom_clean_list.append(bottom_clean)
        top_clean_list.append(top_clean)
        base_area, major_diameter_b, minor_diameter_b, ellipticity, azimuth = (None,) * 5
        major_diameter_t, minor_diameter_t = None, None
        volume, avg_slope, h_wb_ratio, wcr_wb_ratio = (None,) * 4
        
        if len(bottom_clean) >= 5:
            coords_b = np.array(list(zip(bottom_clean.geometry.x, bottom_clean.geometry.y)))
            
            ell_b = EllipseModel()
            success_b = ell_b.estimate(coords_b)

            if success_b and ell_b.params is not None:
                xc_b, yc_b, a_b, b_b, theta_b = ell_b.params

                major_diameter_b = 2 * a_b
                minor_diameter_b = 2 * b_b
                base_area = math.pi * a_b * b_b
                ellipticity = 1 - (b_b / a_b)
                azimuth = (90 - math.degrees(theta_b)) % 180

         
        if len(top_clean) >= 5:
            coords_t = np.array(list(zip(top_clean.geometry.x, top_clean.geometry.y)))
            ell_t = EllipseModel()
            success_t = ell_t.estimate(coords_t)

            if success_t and ell_t.params is not None:
                xc_t, yc_t, a_t, b_t, theta_t = ell_t.params
                major_diameter_t = 2 * a_t
                minor_diameter_t = 2 * b_t
        
        height = df_cone_base.loc[df_cone_base["cone_id"] == cone_id, "height"].iloc[0]

        if height is not None and major_diameter_b is not None and major_diameter_t is not None:
            R = major_diameter_b / 2  
            r = major_diameter_t / 2  
            
            # Volume of a cone: V = (1/3) * pi * h * (R^2 + R*r + r^2)
            volume = (1/3) * math.pi * height * (R**2 + R*r + r**2)
            
            # Average slope gradient
            if (R - r) > 0:
                slope_rad = math.atan(height / (R - r))
                avg_slope = math.degrees(slope_rad)

        # Calculation of indicators
        if height is not None and major_diameter_b is not None and major_diameter_b > 0:
            h_wb_ratio = height / major_diameter_b
        
        if major_diameter_t is not None and major_diameter_b is not None and major_diameter_b > 0:
            wcr_wb_ratio = major_diameter_t / major_diameter_b
            
        cone_metrics.append({
            "cone_id": cone_id,
            "base_area": base_area,
            "base_major_diameter": major_diameter_b,
            "base_minor_diameter": minor_diameter_b,
            "base_center_x": xc_b,
            "base_center_y": yc_b,
            "base_angle_deg": np.degrees(theta_b),
            "top_major_diameter": major_diameter_t,
            "top_minor_diameter": minor_diameter_t,
            "top_center_x": xc_t,
            "top_center_y": yc_t,
            "top_angle_deg": np.degrees(theta_t),
            "volume": volume,
            "base_ellipticity": ellipticity,
            "elongation_azimuth": azimuth,
            "avg_slope_deg": avg_slope,
            "H_WB_ratio": h_wb_ratio,
            "WCR_WB_ratio": wcr_wb_ratio
        })

    gdf_bottom_clean = gpd.GeoDataFrame(
        pd.concat(bottom_clean_list, ignore_index=True),
        crs=crs
    )
    gdf_top_clean = gpd.GeoDataFrame(
        pd.concat(top_clean_list, ignore_index=True),
        crs=crs
    )
    df_metrics = pd.DataFrame(cone_metrics)

    df_cone = pd.merge(df_cone_base, df_metrics, on="cone_id", how="left")
    df_cone = df_cone.round(3)

    # Add the lowest point of the centre (point C from Finder)
    center_c = gdf_features[gdf_features["type"] == "C"]
    center_lowest = center_c.groupby("cone_id")["elevation"].min().reset_index()
    center_lowest = center_lowest.rename(columns={"elevation": "center_lowest_elev"})
    df_cone = df_cone.merge(center_lowest, on="cone_id", how="left")
    df_cone["depth"] = (df_cone["top_elev"] - df_cone["center_lowest_elev"]).round(1)

    cone_output_csv = join(base, "output/analyzer/cone_summary.csv")
    df_cone.to_csv(cone_output_csv, sep=csv_sep, index=False, encoding="utf-8")
    print(f"{YELLOW}✔ Exported aggregated results to {cone_output_csv}{RESET}")

    print(f"{YELLOW}✔ Generating GeoJSON buffers for cones by shape{RESET}")

    geojson_dir = os.path.join(base, "output/analyzer/shapes")
    os.makedirs(geojson_dir, exist_ok=True)

    gdf_cones = gpd.GeoDataFrame(
        df_cone,
        geometry=gpd.points_from_xy(df_cone["center_x"], df_cone["center_y"]),
        crs=crs  
    )

    gdf_cones["geometry"] = gdf_cones.geometry.buffer(gdf_cones["bottom_width"] / 2)

    for shape_class in gdf_cones["shape"].dropna().unique():
        shape_gdf = gdf_cones[gdf_cones["shape"] == shape_class]
        shape_path = os.path.join(geojson_dir, f"{shape_class}_cones.gpkg")
        shape_gdf.to_file(shape_path, driver="GPKG")
        print(f"{GREEN}✔ Saved: {shape_path}{RESET}")

    print(f"{YELLOW}✔ Computing crater centers using top points and least squares{RESET}")

    # Filter only points of type *_top
    gdf_top = gdf_features[gdf_features["type"].str.contains("_top", regex=True)].copy()

    center_results = []

    for cone_id, group in gdf_top.groupby("cone_id"):
        if len(group) < 2:
            continue

        x = group["x_geo"].values
        y = group["y_geo"].values

        if len(group) >= 4:
            cx = np.median(x)
            cy = np.median(y)
            dist = np.sqrt((x - cx)**2 + (y - cy)**2)
            iqr = np.percentile(dist, 75) - np.percentile(dist, 25)
            mask = dist < (np.percentile(dist, 75) + 1.5 * iqr)
            x = x[mask]
            y = y[mask]

        x_center = np.mean(x)
        y_center = np.mean(y)

        center_results.append({
            "cone_id": cone_id,
            "x_geo": x_center,
            "y_geo": y_center,
            "geometry": Point(x_center, y_center)
        })
        

    # Export as a separate GeoJSON
    gdf_centers = gpd.GeoDataFrame(center_results, crs=crs)
    center_out_path = os.path.join(base, "output/analyzer/shapes/centers.gpkg")
    gdf_centers.to_file(center_out_path, driver="GPKG")

    print(f"{GREEN}✔ Saved center points to {center_out_path}{RESET}")

    print(f"{YELLOW}✔ Reading expert crater center points from input/centers{RESET}")
    
    centers_input_path = join(base, config["paths"]["input"]["centers"])
    expert_center_file = None

    for fname in os.listdir(centers_input_path):
        if fname.endswith(".shp") or fname.endswith(".gpkg"):
            expert_center_file = join(centers_input_path, fname)
            break

    if not expert_center_file:
        print(f"{RED}✘ No shapefile or geojson found in input/centers{RESET}")
        input_points_gdf = None
    else:
        input_points_gdf = gpd.read_file(expert_center_file).to_crs(crs)

        if "cone_id" not in input_points_gdf.columns:
            if "id" in input_points_gdf.columns:
                input_points_gdf = input_points_gdf.rename(columns={"id": "cone_id"})
            elif "Id" in input_points_gdf.columns:
                input_points_gdf = input_points_gdf.rename(columns={"Id": "cone_id"})
            elif "name" in input_points_gdf.columns:
                input_points_gdf = input_points_gdf.rename(columns={"name": "cone_id"})
            else:
                print(f"{RED}✘ No valid ID column found in input center file. Expected 'cone_id', 'id', 'Id' or 'name'.{RESET}")
                input_points_gdf["cone_id"] = None  

        input_center_out = os.path.join(base, "output/analyzer/shapes/centers_input.gpkg")
        input_points_gdf.to_file(input_center_out, driver="GPKG")
        print(f"{GREEN}✔ Saved input center points to {input_center_out}{RESET}")

    print(f"{YELLOW}✔ Computing hybrid crater centers (top + expert point){RESET}")

    hybrid_results = []

    if input_points_gdf is not None:
        for cone_id, group in gdf_top.groupby("cone_id"):
            input_point = input_points_gdf[input_points_gdf["cone_id"].astype(str) == str(cone_id)]

            if input_point.empty:
                continue

            x = group["x_geo"].values
            y = group["y_geo"].values

            input_x = input_point.geometry.x.values[0]
            input_y = input_point.geometry.y.values[0]

            if len(group) >= 4:
                cx = np.median(x)
                cy = np.median(y)
                dist = np.sqrt((x - cx)**2 + (y - cy)**2)
                iqr = np.percentile(dist, 75) - np.percentile(dist, 25)
                mask = dist < (np.percentile(dist, 75) + 1.5 * iqr)
                x = x[mask]
                y = y[mask]

            centroid_x = np.mean(x)
            centroid_y = np.mean(y)

            # Scales (adjust if needed)
            w_top = 0.7
            w_input = 0.3

            hybrid_x = w_top * centroid_x + w_input * input_x
            hybrid_y = w_top * centroid_y + w_input * input_y

            hybrid_results.append({
                "cone_id": cone_id,
                "x_geo": hybrid_x,
                "y_geo": hybrid_y,
                "geometry": Point(hybrid_x, hybrid_y)
            })

        if hybrid_results:
            gdf_hybrid = gpd.GeoDataFrame(hybrid_results, geometry="geometry", crs=crs)
            hybrid_out_path = os.path.join(base, "output/analyzer/shapes/centers_hybrid.gpkg")
            gdf_hybrid.to_file(hybrid_out_path, driver="GPKG")
            print(f"{GREEN}✔ Saved hybrid center points to {hybrid_out_path}{RESET}")
        else:
            print(f"{RED}✘ No hybrid centers were computed – check if cone_id values match between top points and expert points.{RESET}")


        if hybrid_results:
            df_hybrid = pd.DataFrame(hybrid_results)
            df_hybrid = df_hybrid.rename(columns={"x_geo": "hybrid_x", "y_geo": "hybrid_y"})
            df_cone = df_cone.merge(df_hybrid[["cone_id", "hybrid_x", "hybrid_y"]], on="cone_id", how="left")
        else:
            df_cone["hybrid_x"] = None
            df_cone["hybrid_y"] = None

        df_cone.to_csv(cone_output_csv, sep=csv_sep, index=False, encoding="utf-8")
        print(f"{YELLOW}✔ Updated cone_summary.csv with hybrid coordinates{RESET}")

    else:
        print(f"{RED}✘ Skipping hybrid center calculation – no expert file found.{RESET}")


    #  Summary GeoPackage with full representation of cones 
    print(f"{YELLOW}✔ Exporting unified GeoPackage with cleaned points and fitted ellipses{RESET}")

    summary_rel = config.get("output", {}).get("summary_gpkg", "output/analyzer/marscone.gpkg")
    summary_gpkg = os.path.join(base, summary_rel)

    os.makedirs(os.path.dirname(summary_gpkg), exist_ok=True)

    if os.path.exists(summary_gpkg):
        os.remove(summary_gpkg)

    gdf_bottom_clean.to_file(summary_gpkg, layer="points_bottom_near_and_far", driver="GPKG")
    gdf_top_clean.to_file(summary_gpkg, layer="points_top", driver="GPKG")

    ellipse_base_rows = []
    ellipse_top_rows = []

    for _, row in df_cone.iterrows():
        cone_id = row["cone_id"]
        cx = row.get("top_center_x", row["center_x"])
        cy = row.get("top_center_y", row["center_y"])


        # base ellipse
        if not pd.isna(row.get("base_major_diameter", np.nan)) and not pd.isna(row.get("base_minor_diameter", np.nan)):
            poly_b = ellipse_to_polygon(
                cx=cx,
                cy=cy,
                major_diameter=row["base_major_diameter"],
                minor_diameter=row["base_minor_diameter"],
                angle_deg=row.get("elongation_azimuth", 0.0)
            )
            ellipse_base_rows.append({
                "cone_id": cone_id,
                "geometry": poly_b,
                "shape": row.get("shape", None),
                "base_major_diameter": row["base_major_diameter"],
                "base_minor_diameter": row["base_minor_diameter"],
                "base_area": row.get("base_area", None),
                "elongation_azimuth": row.get("elongation_azimuth", None)
            })

        # top ellipse
        if not pd.isna(row.get("top_major_diameter", np.nan)) and not pd.isna(row.get("top_minor_diameter", np.nan)):
            poly_t = ellipse_to_polygon(
                cx=cx,
                cy=cy,
                major_diameter=row["top_major_diameter"],
                minor_diameter=row["top_minor_diameter"],
                angle_deg=row.get("elongation_azimuth", 0.0)
            )
            ellipse_top_rows.append({
                "cone_id": cone_id,
                "geometry": poly_t,
                "top_major_diameter": row["top_major_diameter"],
                "top_minor_diameter": row["top_minor_diameter"]
            })

    if ellipse_base_rows:
        gdf_ellipse_base = gpd.GeoDataFrame(ellipse_base_rows, geometry="geometry", crs=crs)
        gdf_ellipse_base.to_file(summary_gpkg, layer="ellipse_base", driver="GPKG")

    if ellipse_top_rows:
        gdf_ellipse_top = gpd.GeoDataFrame(ellipse_top_rows, geometry="geometry", crs=crs)
        gdf_ellipse_top.to_file(summary_gpkg, layer="ellipse_top", driver="GPKG")


    points_axis_rows = []

    if not gdf_bottom_clean.empty:
        for (cone_id, transect_id), sub in gdf_bottom_clean.groupby(["cone_id", "transect_id"]):
            if sub.empty:
                continue

            sub = sub.reset_index(drop=True)

            # if there is only one bottom – we take that one,
            # if there are at least two – we take the "second" one (usually closer to the ellipse)
            if len(sub) == 1:
                best = sub.iloc[0].copy()
            else:
                best = sub.iloc[1].copy()

            best["axis_deg"] = angle_from_transect_id(transect_id)
            points_axis_rows.append(best)

    if points_axis_rows:
        gdf_bottom_axis = gpd.GeoDataFrame(points_axis_rows,
                                           geometry="geometry",
                                           crs=crs)
        gdf_bottom_axis.to_file(summary_gpkg,
                                layer="points_bottom",
                                driver="GPKG")
        print(f"{GREEN}✔ Saved per-transect bottom points to layer 'points_bottom'{RESET}")

    centers_path = os.path.join(base, "output/analyzer/centers.gpkg")
    centers_input_path = os.path.join(base, "output/analyzer/centers_input.gpkg")
    centers_hybrid_path = os.path.join(base, "output/analyzer/centers_hybrid.gpkg")

    if os.path.exists(centers_path):
        gpd.read_file(centers_path).to_file(summary_gpkg, layer="centroid_top", driver="GPKG")
    if os.path.exists(centers_input_path):
        gpd.read_file(centers_input_path).to_file(summary_gpkg, layer="centroid_input", driver="GPKG")
    if os.path.exists(centers_hybrid_path):
        gpd.read_file(centers_hybrid_path).to_file(summary_gpkg, layer="centroid_hybrid", driver="GPKG")

    print(f"{GREEN}✔ Saved unified GeoPackage to {summary_gpkg}{RESET}")

if __name__ == "__main__":
    main()
