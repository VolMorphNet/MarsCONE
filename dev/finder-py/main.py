"""
MarsCONE Finder CLI

Detects characteristic points (bottom, top, center) on terrain transects for cone-like landforms
using elevation profiles and signal analysis.

Authors: Jakub Śledziowski, Bartosz Pieterek, Thomas Jones
License: MIT
"""

import json
import os
from os.path import dirname, join

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.signal import find_peaks, savgol_filter
from shapely.geometry import Point
from tqdm import tqdm

YELLOW = "\033[93m"
RESET = "\033[0m"
GREEN = "\033[92m"
CYAN = "\033[96m"


def main():  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    """
    Main function for detecting bottom, top, and center points on each transect.
    Loads configuration, processes each transect, and exports results to GeoPackage and CSV.
    """
    with open("config.json", encoding="utf-8") as f:
        config = json.load(f)

    base = config["paths"]["base"]
    db_path = join(base, config["paths"]["db"])
    profiles_layer = config["db_layers"]["profiles"]
    points_layer = config["db_layers"]["points"]
    csv_output = join(base, config["paths"]["output"]["results_csv"])
    smoothing_cfg = config.get("smoothing", {})
    smoothing_enabled = bool(smoothing_cfg.get("enabled", False))
    smoothing_window_m = float(smoothing_cfg.get("window_m", 120.0))
    smoothing_polyorder = int(smoothing_cfg.get("polyorder", 2))
    detection_cfg = config.get("detection", {})
    bottom_edge_guard_frac = float(detection_cfg.get("bottom_edge_guard_frac", 0.12))

    print(
        f"{CYAN}Smoothing: enabled={smoothing_enabled}, "
        f"window={smoothing_window_m:.1f} m, polyorder={smoothing_polyorder}{RESET}"
    )
    print(f"{CYAN}Detection: bottom_edge_guard_frac={bottom_edge_guard_frac:.2f}{RESET}")

    os.makedirs(dirname(csv_output), exist_ok=True)
    gdf = gpd.read_file(db_path, layer=profiles_layer)
    points = []
    grouped = gdf.groupby("transect_id")

    for transect_id, group in tqdm(grouped, desc="Detecting base and top"):
        profile = group.sort_values("distance").copy()
        profile = apply_optional_smoothing(
            profile,
            enabled=smoothing_enabled,
            window_m=smoothing_window_m,
            polyorder=smoothing_polyorder,
        )
        cone_id = profile["cone_id"].iloc[0]
        orientation = (
            profile["orientation"].iloc[0] if "orientation" in profile.columns else None
        )
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
                bottom = detect_bottom_adaptive(
                    side, top_idx, center_x=center_dist,
                    edge_guard_frac=bottom_edge_guard_frac,
                )
            else:
                # Fallback: use lowest point in first 1/3 of segment or segment start
                if len(side) > 10:
                    bottom_segment_fallback = side.iloc[0 : len(side) // 3]
                    if not bottom_segment_fallback.empty:
                        bottom = bottom_segment_fallback.loc[
                            bottom_segment_fallback["elevation"].idxmin()
                        ]
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
                if is_top_suspicious(
                    top, side, bottom_dist, center_dist, transect_id=transect_id
                ):
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
                points.append(
                    {
                        "type": f"{suffix}_{label}",
                        "transect_id": transect_id,
                        "cone_id": cone_id,
                        "orientation": orientation,
                        "elevation": point.get("elevation_raw", point["elevation"]),
                        "slope": point["slope"],
                        "distance": point["distance"],
                        "x_geo": point["x_geo"],
                        "y_geo": point["y_geo"],
                        "status": status,
                        "geometry": Point(point["x_geo"], point["y_geo"]),
                    }
                )

        # Detect center point: min or max between tops if appropriate, else geometric center
        top_points = [
            p
            for p in points
            if p["transect_id"] == transect_id and p["type"].endswith("_top")
        ]
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
        points.append(
            {
                "type": "C",
                "transect_id": transect_id,
                "cone_id": cone_id,
                "orientation": orientation,
                "elevation": center.get("elevation_raw", center["elevation"]),
                "slope": center["slope"],
                "distance": center["distance"],
                "x_geo": center["x_geo"],
                "y_geo": center["y_geo"],
                "geometry": Point(center["x_geo"], center["y_geo"]),
            }
        )

    gdf_out = gpd.GeoDataFrame(points, crs=gdf.crs)
    gdf_out.to_file(db_path, layer=points_layer, driver="GPKG", overwrite="YES")
    gdf_out.drop(columns="geometry").to_csv(
        csv_output, sep=";", index=False, encoding="utf-8"
    )
    print(
        f"{GREEN}✔ Saved {len(gdf_out)} points to GPKG layer '{points_layer}' "
        f"and CSV '{csv_output}'{RESET}"
    )


def infer_direction(profile):
    """
    Infers transect orientation based on x/y spread.
    Returns 'EW' for east-west, 'NS' for north-south.
    """
    dx = profile["x_geo"].max() - profile["x_geo"].min()
    dy = profile["y_geo"].max() - profile["y_geo"].min()
    return "EW" if dx > dy else "NS"


def apply_optional_smoothing(
    profile: pd.DataFrame, enabled: bool, window_m: float, polyorder: int
) -> pd.DataFrame:
    """Apply optional Savitzky-Golay smoothing to profile elevation for detection.

    The original elevation is preserved in `elevation_raw` so exported points
    keep DEM-native values even when detection runs on smoothed signal.
    """
    if not enabled:
        return profile

    if len(profile) < 5:
        return profile

    out = profile.copy()
    out["elevation_raw"] = out["elevation"]

    elevation_series = pd.to_numeric(out["elevation"], errors="coerce")
    if elevation_series.isna().all():
        return profile

    filled = elevation_series.interpolate(limit_direction="both")
    if filled.isna().all():
        return profile

    diffs = np.diff(pd.to_numeric(out["distance"], errors="coerce").to_numpy(dtype=float))
    diffs = np.abs(diffs[np.isfinite(diffs)])
    diffs = diffs[diffs > 0]
    if len(diffs) == 0:
        return profile

    spacing = float(np.median(diffs))
    if not np.isfinite(spacing) or spacing <= 0:
        return profile

    window_samples = int(round(window_m / spacing))
    min_window = max(3, polyorder + 2)
    if window_samples < min_window:
        window_samples = min_window
    if window_samples % 2 == 0:
        window_samples += 1

    max_window = len(out) if len(out) % 2 == 1 else len(out) - 1
    if max_window < 3:
        return profile
    window_samples = min(window_samples, max_window)

    poly_eff = min(max(1, polyorder), window_samples - 1)
    if poly_eff >= window_samples:
        return profile

    try:
        smoothed = savgol_filter(
            filled.to_numpy(dtype=float),
            window_length=window_samples,
            polyorder=poly_eff,
            mode="interp",
        )
    except ValueError:
        return profile

    out["elevation"] = smoothed
    return out


def get_side_prefix(direction, side_index):
    """
    Returns prefix for side of transect based on orientation and side index.
    """
    if direction == "EW":
        return "W" if side_index == 0 else "E"
    return "S" if side_index == 0 else "N"


def _search_non_edge_bottom(
    segment, smoothed_elevation, top_elevation, top_x,
    min_dist_h, min_dist_v, in_edge_zone, elev_range
):
    """Search for the deepest valid bottom candidate outside the edge zone.

    Uses local minima of the smoothed elevation profile (find_peaks on
    inverted signal).  Returns the best non-edge candidate as a Series
    with .status == 'accepted_local_min', or None if nothing qualifies.
    """
    if elev_range <= 0 or len(smoothed_elevation) < 3:
        return None
    inv_e = -smoothed_elevation.copy()
    inv_e = np.where(np.isfinite(inv_e), inv_e, 0.0)
    min_prominence = max(0.02 * elev_range, 0.1)
    peaks, _ = find_peaks(inv_e, prominence=min_prominence)
    best = None
    best_depth = 0.0
    for idx in peaks:
        if idx >= len(segment):
            continue
        pt = segment.iloc[idx].copy()
        if in_edge_zone(float(pt["distance"])):
            continue
        depth = top_elevation - float(pt["elevation"])
        dist_from_top = abs(float(pt["distance"]) - top_x)
        if depth > min_dist_v and dist_from_top > min_dist_h and depth > best_depth:
            best = pt
            best_depth = depth
    if best is not None:
        best.status = "accepted_local_min"
    return best


def detect_bottom_adaptive(profile, top_idx, center_x, edge_guard_frac=0.12):
    # pylint: disable=too-many-branches,too-many-locals,too-many-statements,too-many-return-statements
    """Detect the bottom (base) of a cone flank, with edge guard and adaptive thresholds.

    Enhanced over the original implementation with:
    - Adaptive ``min_drop_height``: scales with 2 % of the full profile
      elevation range instead of a fixed 0.5 m, making it usable across
      Mars/Earth/submarine terrains with very different relief.
    - Edge guard: the outer ``edge_guard_frac`` fraction of the outward segment
      distance span is treated as an *edge zone*.  Candidates inside this zone
      are accepted only when no valid non-edge alternative exists, and they
      receive the explicit status ``edge_accepted`` so that downstream quality
      assessment can flag them.
    - Non-edge alternative search: when the main slope-knee path or the
      extended-search path lands in the edge zone, ``_search_non_edge_bottom``
      is called to find local minima outside the zone.

    Args:
        profile: DataFrame of the full transect side.
        top_idx: Integer position of the detected top in *profile*.
        center_x: Distance value of the transect geometric centre.
        edge_guard_frac: Fraction of segment length treated as edge zone
            (0.0 = disabled, default 0.12).
    Returns:
        Series with a ``.status`` attribute set to one of:
        ``accepted``, ``accepted_local_min``, ``edge_accepted``,
        ``extended_search_lowest``, ``fallback_drop_start``,
        ``fallback_lowest``, ``fallback_segment_lowest``.
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

    # --- Adaptive thresholds --------------------------------------------------
    elev_range = float(profile["elevation"].max() - profile["elevation"].min())
    elev_range = max(elev_range, 1.0)
    significant_drop_slope_thresh = -0.05
    stabilization_slope_thresh = 0.01
    # Scale min drop to profile relief: 2 % of range, minimum 0.3 m
    min_drop_height = max(0.3, 0.02 * elev_range)
    min_dist_from_top_horizontal = 0.1 * abs(top_x - center_x)
    min_dist_from_top_vertical = 0.05 * elev_range

    # --- Edge guard -----------------------------------------------------------
    dist_vals = segment["distance"].values.astype(float)
    seg_dist_min = float(np.nanmin(dist_vals))
    seg_dist_max = float(np.nanmax(dist_vals))
    seg_span = seg_dist_max - seg_dist_min
    guard_width = seg_span * max(0.0, min(0.5, float(edge_guard_frac)))
    outward_ascending = float(dist_vals[-1]) > float(dist_vals[0])
    if outward_ascending:
        edge_threshold = seg_dist_max - guard_width
        def in_edge_zone(d): return float(d) > edge_threshold  # noqa: E731
    else:
        edge_threshold = seg_dist_min + guard_width
        def in_edge_zone(d): return float(d) < edge_threshold  # noqa: E731

    # --- Smooth + gradient ----------------------------------------------------
    smooth_window = min(5, max(1, len(segment) // 5))
    smoothed_elevation = (
        segment["elevation"]
        .rolling(window=smooth_window, center=True, min_periods=1)
        .mean()
        .values
    )
    distances = segment["distance"].values
    slopes = np.gradient(smoothed_elevation, distances)

    # --- Step 1: Find first significant slope drop ----------------------------
    drop_start_idx = -1
    for idx, slope in enumerate(slopes):
        if slope < significant_drop_slope_thresh:
            if (top_elevation - smoothed_elevation[idx]) > min_drop_height:
                drop_start_idx = idx
                break

    if drop_start_idx == -1:
        # No slope drop found – prefer lowest point outside edge zone
        valid_all = segment["elevation"].dropna()
        if not valid_all.empty:
            non_edge_mask = ~segment["distance"].apply(in_edge_zone)
            non_edge_seg = segment[non_edge_mask]
            for try_seg in [non_edge_seg, segment]:
                if try_seg.empty:
                    continue
                valid = try_seg["elevation"].dropna()
                if valid.empty:
                    continue
                pt = try_seg.loc[valid.idxmin()].copy()
                if float(pt["elevation"]) < top_elevation:
                    pt.status = "fallback_lowest"
                    return pt
        return top_point

    # --- Step 2: Find stabilisation after drop start --------------------------
    bottom_candidate_idx = drop_start_idx
    for i in range(drop_start_idx, len(slopes)):
        if abs(slopes[i]) < stabilization_slope_thresh or slopes[i] > 0:
            bottom_candidate_idx = i
            break
        if (
            i >= 2
            and slopes[i] > slopes[i - 1]
            and slopes[i - 1] > slopes[i - 2]
            and slopes[i] > 0.02
        ):
            bottom_candidate_idx = i
            break

    search_segment = segment.iloc[drop_start_idx : bottom_candidate_idx + 1]
    if search_segment.empty:
        search_segment = segment.iloc[drop_start_idx : drop_start_idx + 1]
    valid_elevations_for_min = search_segment["elevation"].dropna()
    if valid_elevations_for_min.empty:
        return top_point
    min_elev_point = search_segment.loc[valid_elevations_for_min.idxmin()].copy()

    is_far_enough_horizontally = (
        abs(float(min_elev_point["distance"]) - top_x) > min_dist_from_top_horizontal
    )
    is_low_enough_vertically = (
        top_elevation - float(min_elev_point["elevation"])
    ) > min_dist_from_top_vertical

    if is_far_enough_horizontally and is_low_enough_vertically:
        if not in_edge_zone(min_elev_point["distance"]):
            min_elev_point.status = "accepted"
            return min_elev_point
        # Main candidate is in edge zone – look for non-edge local-minima alt
        alt = _search_non_edge_bottom(
            segment, smoothed_elevation, top_elevation, top_x,
            min_dist_from_top_horizontal, min_dist_from_top_vertical,
            in_edge_zone, elev_range,
        )
        if alt is not None:
            return alt
        min_elev_point.status = "edge_accepted"
        return min_elev_point

    # --- Step 3: Extended search in remaining segment -------------------------
    remaining_segment = segment.iloc[bottom_candidate_idx + 1 :]
    if not remaining_segment.empty:
        valid_remaining = remaining_segment["elevation"].dropna()
        if not valid_remaining.empty:
            deeper_bottom = remaining_segment.loc[valid_remaining.idxmin()].copy()
            if (
                top_elevation - float(deeper_bottom["elevation"])
            ) > min_dist_from_top_vertical:
                if not in_edge_zone(deeper_bottom["distance"]):
                    deeper_bottom.status = "extended_search_lowest"
                    return deeper_bottom
                # Extended candidate is in edge zone – try non-edge local min
                alt = _search_non_edge_bottom(
                    segment, smoothed_elevation, top_elevation, top_x,
                    min_dist_from_top_horizontal, min_dist_from_top_vertical,
                    in_edge_zone, elev_range,
                )
                if alt is not None:
                    return alt
                deeper_bottom.status = "extended_search_lowest"
                return deeper_bottom

    # --- Step 4: Fallback from drop start point --------------------------------
    potential_bottom_from_drop_start = segment.iloc[drop_start_idx].copy()
    if (
        top_elevation - float(potential_bottom_from_drop_start["elevation"])
    ) > min_dist_from_top_vertical:
        potential_bottom_from_drop_start.status = "fallback_drop_start"
        return potential_bottom_from_drop_start

    # --- Step 5: Segment-wide lowest, non-edge zone first ----------------------
    non_edge_mask = ~segment["distance"].apply(in_edge_zone)
    non_edge_seg = segment[non_edge_mask]
    for try_seg in [non_edge_seg, segment]:
        if try_seg.empty:
            continue
        valid = try_seg["elevation"].dropna()
        if valid.empty:
            continue
        pt = try_seg.loc[valid.idxmin()].copy()
        if float(pt["elevation"]) < top_elevation:
            pt.status = "fallback_segment_lowest"
            return pt
    return top_point


def detect_top_by_drop(profile, bottom_dist=None, center_dist=None):
    # pylint: disable=too-many-branches,too-many-return-statements,too-many-locals
    """
    Detects the 'top' (summit) point of a cone side profile using prominence
    and drop analysis. Prioritizes peaks within a reasonable distance from
    the center.
    Args:
        profile: DataFrame of the side profile.
        bottom_dist: Distance of detected bottom (optional).
        center_dist: Distance of geometric center (optional).
    Returns:
        Series: Row corresponding to detected top point (with .status).
    """
    elev = profile["elevation"].values
    height_range = np.nanmax(elev) - np.nanmin(elev)

    min_peak_height_abs = np.nanmin(elev) + 0.5 * height_range
    min_peak_height_relative_to_segment_start = 0.05 * height_range
    prominence_threshold = max(0.08 * height_range, 0.5)
    min_peak_width = 3
    search_segment_profile = profile.copy()
    if bottom_dist is not None and center_dist is not None:
        if profile["distance"].iloc[0] < profile["distance"].iloc[-1]:
            if bottom_dist < center_dist:
                search_segment_profile = profile[
                    (profile["distance"] >= bottom_dist)
                    & (profile["distance"] <= center_dist)
                ].copy()
            else:
                search_segment_profile = profile[
                    (profile["distance"] >= center_dist)
                    & (profile["distance"] <= bottom_dist)
                ].copy()
        else:
            print(
                f"{YELLOW}[WARN] Profile for {profile['transect_id'].iloc[0]} "
                "is not sorted ascending by distance. Top search segment may "
                f"be incorrect.{RESET}"
            )
            search_segment_profile = profile.copy()
    if search_segment_profile.empty or len(search_segment_profile) < 5:
        result = profile.loc[profile["elevation"].idxmax()]
        result.status = "fallback_segment_empty"
        return result
    elev_segment = search_segment_profile["elevation"].values
    peaks, properties = find_peaks(
        elev_segment,
        height=min_peak_height_abs,
        prominence=prominence_threshold,
        width=min_peak_width,
    )
    if len(peaks) == 0:
        max_elev_in_segment_idx = search_segment_profile["elevation"].idxmax()
        potential_top = search_segment_profile.loc[max_elev_in_segment_idx]
        min_elev_in_segment = np.nanmin(elev_segment)
        if (
            potential_top["elevation"] - min_elev_in_segment
        ) > min_peak_height_relative_to_segment_start:
            potential_top.status = "fallback_highest_in_segment"
            return potential_top
        result = profile.loc[profile["elevation"].idxmax()]
        result.status = "fallback_overall_highest"
        return result

    best_peak_idx_in_segment = peaks[np.argmax(properties["peak_heights"])]
    original_index = search_segment_profile.index[best_peak_idx_in_segment]
    result = profile.loc[original_index]
    result.status = "accepted"
    return result


def is_top_suspicious(
    top,
    profile,
    bottom_dist,
    center_dist,
    transect_id="",
    threshold_height_ratio=0.08,
    threshold_dist_ratio=0.3,
):
    """
    Determines if a detected top is suspicious (e.g., too close to bottom,
    too flat, or not a real peak).
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
    # pylint: disable=too-many-locals,too-many-arguments,too-many-positional-arguments
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
    too_flat_vertically = (top_elev - bottom_elev) < (
        threshold_height_ratio * total_elevation_range
    )
    if top_dist < center_dist:
        mid_section = profile[
            (profile["distance"] > top_dist) & (profile["distance"] < center_dist)
        ]
    else:
        mid_section = profile[
            (profile["distance"] < top_dist) & (profile["distance"] > center_dist)
        ]
    growing_ahead_threshold = 0.05 * total_elevation_range
    growing_ahead = False
    if not mid_section.empty:
        if mid_section["elevation"].max() > top_elev + growing_ahead_threshold:
            growing_ahead = True
    suspicious_score = sum([too_close_horizontally, too_flat_vertically, growing_ahead])
    if suspicious_score >= 2:
        print(
            f"{CYAN}[DEBUG] Suspicious top @ {top['distance']:.1f} m "
            f"(elev {top['elevation']:.2f}) — transect {transect_id}. "
            "Criteria: close="
            f"{too_close_horizontally}, flat={too_flat_vertically}, "
            f"rising={growing_ahead}. Skipping.{RESET}"
        )
        return True
    return False


def search_alternative_top(
    profile, bottom_dist, center_dist, min_delta_height_ratio=0.1
):
    """
    Searches for an alternative 'top' point closer to the center, in the
    expected summit region.
    Args:
        profile: DataFrame of the side profile.
        bottom_dist: Distance value of detected bottom.
        center_dist: Distance value of center.
        min_delta_height_ratio: Minimum height difference for candidate
            (fraction of elevation range).
    Returns:
        Series or None: Row corresponding to alternative top (with .status),
        or None if not found.
    """
    # pylint: disable=too-many-locals
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
        print(
            "[WARN] Profile not sorted ascending by distance; "
            "search_alternative_top may not work correctly."
        )
        subrange = profile[(dist > bottom_dist) & (dist < center_dist)]
    if subrange.empty or len(subrange) < 5:
        return None
    elev_subrange = subrange["elevation"].values
    alt_prominence_threshold = max(0.05 * total_elevation_range, 0.3)
    peaks_alt, properties_alt = find_peaks(
        elev_subrange,
        prominence=alt_prominence_threshold,
        height=np.nanmin(elev_subrange) + min_delta,
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
