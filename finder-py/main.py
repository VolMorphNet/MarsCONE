"""
MarsCONE Finder CLI

Detects characteristic points (bottom, top, center) on terrain transects for cone-like landforms
using elevation profiles and signal analysis.

Authors: Jakub Śledziowski, Bartosz Pieterek, Thomas Jones
License: MIT
"""

import sys
import json
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from os.path import join, dirname
from tqdm import tqdm
import numpy as np
from sklearn.linear_model import LinearRegression
import os
from scipy.signal import argrelextrema
from scipy.signal import find_peaks

YELLOW = "\033[93m"
RESET = "\033[0m"
GREEN = "\033[92m"
CYAN = "\033[96m"

def main():
    """
    Main function for detecting bottom, top, and center points on each transect.
    Loads configuration, processes each transect, and exports results to GeoPackage and CSV.
    """
    with open("config.json", "r") as f:
        config = json.load(f)

    base = config["paths"]["base"]
    db_path = join(base, config["paths"]["db"])
    profiles_layer = config["db_layers"]["profiles"]
    points_layer = config["db_layers"]["points"]
    csv_output = join(base, config["paths"]["output"]["results_csv"])

    os.makedirs(dirname(csv_output), exist_ok=True)
    gdf = gpd.read_file(db_path, layer=profiles_layer)
    points = []
    grouped = gdf.groupby("transect_id")

    for transect_id, group in tqdm(grouped, desc="Detecting base and top"):
        profile = group.sort_values("distance").copy()
        cone_id = profile["cone_id"].iloc[0]
        orientation = profile["orientation"].iloc[0] if "orientation" in profile.columns else None
        direction = infer_direction(profile)

        max_dist = profile["distance"].max()
        center_dist = max_dist / 2
        center_idx = (profile["distance"] - center_dist).abs().idxmin()
        center = profile.loc[center_idx]

        side1 = profile[profile["distance"] <= center_dist].copy()
        side2 = profile[profile["distance"] > center_dist].copy()

        for i, side in enumerate([side1, side2]):
            if len(side) < 5 or side["elevation"].isna().all():
                continue
            suffix = get_side_prefix(direction, i)

            # Step 1: Initial top detection (search whole segment if bottom is not yet found)
            top = detect_top_by_drop(side, center_dist=center_dist)
            top_valid = top is not None and not pd.isna(top["distance"])
            top_idx = side.index.get_loc(top.name) if top_valid else None

            # Step 2: Bottom detection (requires top_idx)
            if top_idx is not None:
                bottom = detect_bottom_adaptive(side, top_idx, center_x=center_dist)
            else:
                # Fallback: use lowest point in first 1/3 of segment or segment start
                if len(side) > 10:
                    bottom_segment_fallback = side.iloc[0:len(side)//3]
                    if not bottom_segment_fallback.empty:
                        bottom = bottom_segment_fallback.loc[bottom_segment_fallback["elevation"].idxmin()]
                        bottom.status = "fallback_no_top"
                    else:
                        bottom = side.iloc[0]
                        bottom.status = "fallback_side_start"
                else:
                    bottom = side.iloc[0]
                    bottom.status = "fallback_side_start"

            bottom_valid = bottom is not None and not pd.isna(bottom["distance"])
            bottom_dist = bottom["distance"] if bottom_valid else None

            # Step 3: Top refinement using bottom information
            if top is not None and bottom is not None:
                if is_top_suspicious(top, side, bottom_dist, center_dist, transect_id=transect_id):
                    alt_top = search_alternative_top(side, bottom_dist, center_dist)
                    if alt_top is not None:
                        alt_top.status = "refined"
                        top = alt_top
                        top_idx = side.index.get_loc(top.name)

            # Add detected points to list
            for point, label in [(bottom, "bottom"), (top, "top")]:
                if point is None:
                    continue
                if hasattr(point, "status"):
                    status = point.status
                else:
                    status = "accepted" if label == "bottom" else "fallback"
                points.append({
                    "type": f"{suffix}_{label}",
                    "transect_id": transect_id,
                    "cone_id": cone_id,
                    "orientation": orientation,
                    "elevation": point["elevation"],
                    "slope": point["slope"],
                    "distance": point["distance"],
                    "x_geo": point["x_geo"],
                    "y_geo": point["y_geo"],
                    "status": status,
                    "geometry": Point(point["x_geo"], point["y_geo"])
                })

        # Detect center point: min or max between tops if appropriate, else geometric center
        top_points = [p for p in points if p["transect_id"] == transect_id and p["type"].endswith("_top")]
        if len(top_points) == 2:
            d1, d2 = sorted([top_points[0]["distance"], top_points[1]["distance"]])
            seg = profile[(profile["distance"] >= d1) & (profile["distance"] <= d2)]
            if not seg.empty and not seg["elevation"].isna().all():
                elev_center = center["elevation"]
                elev_top1 = top_points[0]["elevation"]
                elev_top2 = top_points[1]["elevation"]
                if elev_center < elev_top1 and elev_center < elev_top2:
                    center = seg.loc[seg["elevation"].idxmin()]
                elif elev_center > elev_top1 and elev_center > elev_top2:
                    center = seg.loc[seg["elevation"].idxmax()]
                # Otherwise, keep geometric center
        points.append({
            "type": "C",
            "transect_id": transect_id,
            "cone_id": cone_id,
            "orientation": orientation,
            "elevation": center["elevation"],
            "slope": center["slope"],
            "distance": center["distance"],
            "x_geo": center["x_geo"],
            "y_geo": center["y_geo"],
            "geometry": Point(center["x_geo"], center["y_geo"])
        })

    gdf_out = gpd.GeoDataFrame(points, crs=gdf.crs)
    gdf_out.to_file(db_path, layer=points_layer, driver="GPKG", overwrite="YES")
    gdf_out.drop(columns="geometry").to_csv(csv_output, sep=";", index=False, encoding="utf-8")
    print(f"{GREEN}✔ Saved {len(gdf_out)} points to GPKG layer '{points_layer}' and CSV '{csv_output}'{RESET}")


def infer_direction(profile):
    """
    Infers transect orientation based on x/y spread.
    Returns 'EW' for east-west, 'NS' for north-south.
    """
    dx = profile["x_geo"].max() - profile["x_geo"].min()
    dy = profile["y_geo"].max() - profile["y_geo"].min()
    return "EW" if dx > dy else "NS"

def get_side_prefix(direction, side_index):
    """
    Returns prefix for side of transect based on orientation and side index.
    """
    if direction == "EW":
        return "W" if side_index == 0 else "E"
    else:
        return "S" if side_index == 0 else "N"

def detect_bottom_adaptive(profile, top_idx, center_x):
    """
    Detects the 'bottom' point (base) of a cone side profile by searching outward from the top point.
    Looks for a significant drop and then terrain stabilization (low slope) or local minimum.
    Args:
        profile: DataFrame of the side profile.
        top_idx: Index of the detected top point in the profile.
        center_x: Distance value of the geometric center.
    Returns:
        Series: Row corresponding to detected bottom point (with .status).
    """
    top_point = profile.iloc[top_idx]
    top_x = top_point["distance"]
    top_elevation = top_point["elevation"]
    if top_x < center_x:
        segment = profile[profile["distance"] < top_x].copy()
        segment = segment.sort_values("distance", ascending=False)
    else:
        segment = profile[profile["distance"] > top_x].copy()
        segment = segment.sort_values("distance", ascending=True)
    if segment.empty or len(segment) < 5:
        return top_point
    smooth_window = min(5, max(1, len(segment) // 5))
    smoothed_elevation = segment["elevation"].rolling(window=smooth_window, center=True, min_periods=1).mean().values
    distances = segment["distance"].values
    slopes = np.gradient(smoothed_elevation, distances)
    significant_drop_slope_thresh = -0.05
    stabilization_slope_thresh = 0.01
    min_drop_height = 0.5
    drop_start_idx = -1
    for i in range(len(slopes)):
        if slopes[i] < significant_drop_slope_thresh:
            if (top_elevation - smoothed_elevation[i]) > min_drop_height:
                drop_start_idx = i
                break
    if drop_start_idx == -1:
        valid_elevations_for_lowest = segment["elevation"].dropna()
        if not valid_elevations_for_lowest.empty:
            lowest_point_in_segment = segment.loc[valid_elevations_for_lowest.idxmin()]
            if lowest_point_in_segment["elevation"] < top_elevation:
                lowest_point_in_segment.status = "fallback_lowest"
                return lowest_point_in_segment
        return top_point
    bottom_candidate_idx = drop_start_idx
    for i in range(drop_start_idx, len(slopes)):
        if abs(slopes[i]) < stabilization_slope_thresh or slopes[i] > 0:
            bottom_candidate_idx = i
            break
        if i >= 2 and slopes[i] > slopes[i-1] and slopes[i-1] > slopes[i-2] and slopes[i] > 0.02:
            bottom_candidate_idx = i
            break
    search_segment = segment.iloc[drop_start_idx : bottom_candidate_idx + 1]
    if search_segment.empty:
        return segment.iloc[drop_start_idx] if drop_start_idx != -1 else top_point
    valid_elevations_for_min = search_segment["elevation"].dropna()
    if valid_elevations_for_min.empty:
        return top_point
    min_elev_point = search_segment.loc[valid_elevations_for_min.idxmin()]
    min_dist_from_top_horizontal = 0.1 * abs(top_x - center_x)
    min_dist_from_top_vertical = 0.05 * (profile["elevation"].max() - profile["elevation"].min())
    is_far_enough_horizontally = abs(min_elev_point["distance"] - top_x) > min_dist_from_top_horizontal
    is_low_enough_vertically = (top_elevation - min_elev_point["elevation"]) > min_dist_from_top_vertical
    if is_far_enough_horizontally and is_low_enough_vertically:
        min_elev_point.status = "accepted"
        return min_elev_point
    else:
        remaining_segment = segment.iloc[bottom_candidate_idx + 1:]
        if not remaining_segment.empty:
            valid_elevations_remaining = remaining_segment["elevation"].dropna()
            if not valid_elevations_remaining.empty and valid_elevations_remaining.min() < min_elev_point["elevation"]:
                deeper_bottom = remaining_segment.loc[valid_elevations_remaining.idxmin()]
                if (top_elevation - deeper_bottom["elevation"]) > min_dist_from_top_vertical:
                    deeper_bottom.status = "extended_search_lowest"
                    return deeper_bottom
        potential_bottom_from_drop_start = segment.iloc[drop_start_idx]
        if (top_elevation - potential_bottom_from_drop_start["elevation"]) > min_dist_from_top_vertical:
            potential_bottom_from_drop_start.status = "fallback_drop_start"
            return potential_bottom_from_drop_start
        valid_elevations_full_segment = segment["elevation"].dropna()
        if not valid_elevations_full_segment.empty:
            lowest_point_in_full_segment = segment.loc[valid_elevations_full_segment.idxmin()]
            if lowest_point_in_full_segment["elevation"] < top_elevation:
                lowest_point_in_full_segment.status = "fallback_segment_lowest"
                return lowest_point_in_full_segment
        return top_point


def detect_top_by_drop(profile, bottom_dist=None, center_dist=None):
    """
    Detects the 'top' (summit) point of a cone side profile using prominence and drop analysis.
    Prioritizes peaks within a reasonable distance from the center.
    Args:
        profile: DataFrame of the side profile.
        bottom_dist: Distance of detected bottom (optional).
        center_dist: Distance of geometric center (optional).
    Returns:
        Series: Row corresponding to detected top point (with .status).
    """
    elev = profile["elevation"].values
    dist = profile["distance"].values
    height_range = np.nanmax(elev) - np.nanmin(elev)

    min_peak_height_abs = np.nanmin(elev) + 0.5 * height_range
    min_peak_height_relative_to_segment_start = 0.05 * height_range
    prominence_threshold = max(0.08 * height_range, 0.5)
    min_peak_width = 3
    search_segment_profile = profile.copy()
    if bottom_dist is not None and center_dist is not None:
        if profile["distance"].iloc[0] < profile["distance"].iloc[-1]:
            if bottom_dist < center_dist:
                search_segment_profile = profile[(profile["distance"] >= bottom_dist) & (profile["distance"] <= center_dist)].copy()
            else:
                search_segment_profile = profile[(profile["distance"] >= center_dist) & (profile["distance"] <= bottom_dist)].copy()
        else:
            print(f"{YELLOW}[WARN] Profile for {profile['transect_id'].iloc[0]} is not sorted ascending by distance. Top search segment may be incorrect.{RESET}")
            search_segment_profile = profile.copy()
    if search_segment_profile.empty or len(search_segment_profile) < 5:
        result = profile.loc[profile["elevation"].idxmax()]
        result.status = "fallback_segment_empty"
        return result
    elev_segment = search_segment_profile["elevation"].values
    dist_segment = search_segment_profile["distance"].values
    peaks, properties = find_peaks(
        elev_segment,
        height=min_peak_height_abs,
        prominence=prominence_threshold,
        width=min_peak_width
    )
    if len(peaks) == 0:
        max_elev_in_segment_idx = search_segment_profile["elevation"].idxmax()
        potential_top = search_segment_profile.loc[max_elev_in_segment_idx]
        min_elev_in_segment = np.nanmin(elev_segment)
        if (potential_top["elevation"] - min_elev_in_segment) > min_peak_height_relative_to_segment_start:
            potential_top.status = "fallback_highest_in_segment"
            return potential_top
        else:
            result = profile.loc[profile["elevation"].idxmax()]
            result.status = "fallback_overall_highest"
            return result
    else:
        best_peak_idx_in_segment = peaks[np.argmax(properties["peak_heights"])]
        original_index = search_segment_profile.index[best_peak_idx_in_segment]
        result = profile.loc[original_index]
        result.status = "accepted"
        return result


def is_top_suspicious(top, profile, bottom_dist, center_dist, transect_id="", threshold_height_ratio=0.08, threshold_dist_ratio=0.3):
    """
    Determines if a detected top is suspicious (e.g., too close to bottom, too flat, or not a real peak).
    Args:
        top: Series, detected top point.
        profile: DataFrame of the side profile.
        bottom_dist: Distance value of detected bottom.
        center_dist: Distance value of center.
        transect_id: Optional transect ID for debugging.
        threshold_height_ratio: Minimum vertical separation (fraction of profile elevation range).
        threshold_dist_ratio: Minimum horizontal separation (fraction of segment).
    Returns:
        bool: True if the top is suspicious.
    """
    if top is None or bottom_dist is None:
        return False
    top_dist = top["distance"]
    top_elev = top["elevation"]
    bottom_row_idx = (profile["distance"] - bottom_dist).abs().idxmin()
    bottom_point = profile.loc[bottom_row_idx]
    bottom_elev = bottom_point["elevation"]
    total_elevation_range = profile["elevation"].max() - profile["elevation"].min()
    distance_to_bottom = abs(top_dist - bottom_dist)
    total_span = abs(center_dist - bottom_dist)
    too_close_horizontally = distance_to_bottom < (threshold_dist_ratio * total_span)
    too_flat_vertically = (top_elev - bottom_elev) < (threshold_height_ratio * total_elevation_range)
    if top_dist < center_dist:
        mid_section = profile[(profile["distance"] > top_dist) & (profile["distance"] < center_dist)]
    else:
        mid_section = profile[(profile["distance"] < top_dist) & (profile["distance"] > center_dist)]
    growing_ahead_threshold = 0.05 * total_elevation_range
    growing_ahead = False
    if not mid_section.empty:
        if mid_section["elevation"].max() > top_elev + growing_ahead_threshold:
            growing_ahead = True
    suspicious_score = sum([too_close_horizontally, too_flat_vertically, growing_ahead])
    if suspicious_score >= 2:
        print(f"{CYAN}[DEBUG] Suspicious top @ {top['distance']:.1f} m (elev {top['elevation']:.2f}) — transect {transect_id}. Criteria: close={too_close_horizontally}, flat={too_flat_vertically}, rising={growing_ahead}. Skipping.{RESET}")
        return True
    return False


def search_alternative_top(profile, bottom_dist, center_dist, min_delta_height_ratio=0.1):
    """
    Searches for an alternative 'top' point closer to the center, in the expected summit region.
    Args:
        profile: DataFrame of the side profile.
        bottom_dist: Distance value of detected bottom.
        center_dist: Distance value of center.
        min_delta_height_ratio: Minimum height difference for candidate (fraction of elevation range).
    Returns:
        Series or None: Row corresponding to alternative top (with .status), or None if not found.
    """
    elev = profile["elevation"].values
    dist = profile["distance"].values
    total_elevation_range = np.nanmax(elev) - np.nanmin(elev)
    min_delta = min_delta_height_ratio * total_elevation_range
    if profile["distance"].iloc[0] < profile["distance"].iloc[-1]:
        if profile["distance"].max() < center_dist:
            subrange = profile[(dist > bottom_dist) & (dist < center_dist)]
        else:
            subrange = profile[(dist > center_dist) & (dist < bottom_dist)]
    else:
        print("[WARN] Profile not sorted ascending by distance, search_alternative_top may not work correctly.")
        subrange = profile[(dist > bottom_dist) & (dist < center_dist)]
    if subrange.empty or len(subrange) < 5:
        return None
    elev_subrange = subrange["elevation"].values
    alt_prominence_threshold = max(0.05 * total_elevation_range, 0.3)
    peaks_alt, properties_alt = find_peaks(
        elev_subrange,
        prominence=alt_prominence_threshold,
        height=np.nanmin(elev_subrange) + min_delta
    )
    if len(peaks_alt) == 0:
        return None
    best_alt_peak_idx_in_subrange = peaks_alt[np.argmax(properties_alt["peak_heights"])]
    candidate_original_index = subrange.index[best_alt_peak_idx_in_subrange]
    candidate = profile.loc[candidate_original_index]
    candidate.status = "refined_alt"
    return candidate


if __name__ == "__main__":
    main()
