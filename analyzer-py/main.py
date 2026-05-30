"""
MarsCONE Analyzer Module
------------------------
Performs morphometric and geometric analysis of cone-like landforms.
Calculates metrics such as height, width, volume, and shape,
and exports aggregated results as CSV and GeoPackage files.

Authors: Jakub Śledziowski, Bartosz Pieterek, Thomas Jones
License: MIT
"""

# pylint: disable=no-name-in-module,too-many-arguments
# pylint: disable=too-many-positional-arguments,too-many-lines
# pylint: disable=too-many-locals,too-many-branches,too-many-statements
# pylint: disable=R0912,R0914,R0915

import json
import math
import os
from os.path import join
from typing import Optional

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point, Polygon
from skimage.measure import EllipseModel  # pylint: disable=no-name-in-module
from tqdm import tqdm

YELLOW = "\033[93m"
RESET = "\033[0m"
RED = "\033[91m"
GREEN = "\033[92m"


DEFAULT_QUALITY_PRESETS = {
    "mars": {
        "n_transects_min": 6,
        "height_ratio_mid": 0.10,
        "height_ratio_high": 0.22,
        "bottom_width_ratio_mid": 0.12,
        "bottom_width_ratio_high": 0.30,
        "bottom_elev_rmse_mid": 8.0,
        "bottom_elev_rmse_high": 25.0,
        "center_top_rmse_mid": 8.0,
        "center_top_rmse_high": 16.0,
    },
    "terrestrial": {
        "n_transects_min": 6,
        "height_ratio_mid": 0.12,
        "height_ratio_high": 0.25,
        "bottom_width_ratio_mid": 0.15,
        "bottom_width_ratio_high": 0.35,
        "bottom_elev_rmse_mid": 12.0,
        "bottom_elev_rmse_high": 35.0,
        "center_top_rmse_mid": 10.0,
        "center_top_rmse_high": 20.0,
    },
    "bathymetry": {
        "n_transects_min": 6,
        "height_ratio_mid": 0.14,
        "height_ratio_high": 0.28,
        "bottom_width_ratio_mid": 0.18,
        "bottom_width_ratio_high": 0.40,
        "bottom_elev_rmse_mid": 18.0,
        "bottom_elev_rmse_high": 50.0,
        "center_top_rmse_mid": 12.0,
        "center_top_rmse_high": 24.0,
    },
}


def _resolve_quality_thresholds(config: dict) -> tuple[dict, str]:
    """Resolve quality thresholds from preset + optional user overrides."""
    quality_cfg = config.get("quality", {})
    preset_name = str(quality_cfg.get("preset", "terrestrial")).strip().lower()
    presets_cfg = quality_cfg.get("presets", {})

    # Merge built-in presets with config-level preset overrides.
    presets = {key: value.copy() for key, value in DEFAULT_QUALITY_PRESETS.items()}
    for name, vals in presets_cfg.items():
        if not isinstance(vals, dict):
            continue
        key = str(name).strip().lower()
        base = presets.get(key, DEFAULT_QUALITY_PRESETS["terrestrial"]).copy()
        base.update(vals)
        presets[key] = base

    if preset_name not in presets:
        print(
            f"{YELLOW}✔ Unknown quality preset '{preset_name}', using 'terrestrial'.{RESET}"
        )
        preset_name = "terrestrial"

    thresholds = presets[preset_name].copy()
    overrides = quality_cfg.get("thresholds", {})
    if isinstance(overrides, dict):
        for key, value in overrides.items():
            if value is not None:
                thresholds[key] = value

    numeric_keys = {
        "n_transects_min": int,
        "height_ratio_mid": float,
        "height_ratio_high": float,
        "bottom_width_ratio_mid": float,
        "bottom_width_ratio_high": float,
        "bottom_elev_rmse_mid": float,
        "bottom_elev_rmse_high": float,
        "center_top_rmse_mid": float,
        "center_top_rmse_high": float,
    }
    for key, caster in numeric_keys.items():
        if key not in thresholds:
            continue
        try:
            thresholds[key] = caster(thresholds[key])
        except (TypeError, ValueError):
            thresholds[key] = DEFAULT_QUALITY_PRESETS["terrestrial"][key]

    return thresholds, preset_name


def safe_degrees(value):
    """Convert radians to degrees while preserving None values."""
    if value is None:
        return None
    return float(np.degrees(value))


def to_point_geometry(geometry):
    """Normalize input geometry to a Point for center extraction."""
    if geometry is None or geometry.is_empty:
        return None

    geom_type = geometry.geom_type
    if geom_type == "Point":
        return geometry
    if geom_type == "MultiPoint":
        if len(geometry.geoms) == 0:
            return None
        return geometry.geoms[0]

    return geometry.centroid


# pylint: disable=too-many-arguments,too-many-positional-arguments
def ellipse_to_polygon(
    cx: float,
    cy: float,
    major_diameter: float,
    minor_diameter: float,
    angle_deg: float,
    n_points: int = 180,
) -> Polygon:  # pylint: disable=too-many-arguments,too-many-positional-arguments
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


def angle_from_transect_id(tid: str) -> Optional[int]:
    """Extract axis angle from transect_id.

    Extracts angle from transect IDs in format like '12_45deg' or '12_5.625deg',
    returning 45 or 6 respectively (rounded to nearest integer, mod 180).
    Angles are modulo 180 so that 45 and 225 share the same axis.

    Parameters
    ----------
    tid : str
        The transect ID string.

    Returns
    -------
    int or None
        The extracted angle (rounded), or None if extraction fails.
    """
    if not isinstance(tid, str):
        return None
    try:
        angle = float(tid.split("_")[1].replace("deg", ""))
        return int(round(angle)) % 180
    except (ValueError, IndexError):
        return None


# pylint: disable=too-many-locals
def apply_manual_point_overrides(
    features: pd.DataFrame,
    overrides_path: str,
    csv_sep: str,
) -> pd.DataFrame:
    """Apply saved manual point overrides to finder features.

    Overrides are matched by (cone_id, transect_id, type) and replace x/y/elevation.
    """
    if not os.path.exists(overrides_path):
        print(
            f"{YELLOW}✔ Manual fix enabled, but overrides file not found: "
            f"{overrides_path}{RESET}"
        )
        return features

    overrides = pd.read_csv(overrides_path, sep=csv_sep)
    if overrides.empty:
        print(
            f"{YELLOW}✔ Manual fix enabled, but overrides file is empty: "
            f"{overrides_path}{RESET}"
        )
        return features

    required_columns = {
        "cone_id",
        "transect_id",
        "type",
        "x_geo",
        "y_geo",
        "elevation",
    }
    if not required_columns.issubset(set(overrides.columns)):
        print(
            f"{RED}✘ Manual fix file missing required columns. "
            f"Expected: {sorted(required_columns)}{RESET}"
        )
        return features

    working = features.copy()
    working["cone_id_norm"] = working["cone_id"].astype(str).str.replace(r"\\.0$", "", regex=True)
    working["transect_id_norm"] = working["transect_id"].astype(str)
    working["type_norm"] = working["type"].astype(str)

    overrides = overrides.copy()
    overrides["cone_id_norm"] = overrides["cone_id"].astype(str).str.replace(
        r"\\.0$", "", regex=True
    )
    overrides["transect_id_norm"] = overrides["transect_id"].astype(str)
    overrides["type_norm"] = overrides["type"].astype(str)

    if "updated_at_utc" in overrides.columns:
        overrides = overrides.sort_values("updated_at_utc", kind="mergesort")

    overrides_latest = overrides.drop_duplicates(
        subset=["cone_id_norm", "transect_id_norm", "type_norm"], keep="last"
    )

    has_axis_col = "axis_deg" in overrides_latest.columns

    applied = 0
    for _, row in overrides_latest.iterrows():
        slot = str(row.get("slot", "")).strip().lower()
        if slot == "center" and has_axis_col and pd.notna(row.get("axis_deg")):
            same_axis = overrides_latest[
                (overrides_latest["cone_id_norm"] == row["cone_id_norm"])
                & pd.notna(overrides_latest["axis_deg"])
                & (overrides_latest["axis_deg"] == row.get("axis_deg"))
            ]
            axis_transects = set(same_axis["transect_id_norm"].dropna().astype(str).tolist())
            if axis_transects:
                mask = (
                    (working["cone_id_norm"] == row["cone_id_norm"])
                    & (working["type_norm"] == "C")
                    & (working["transect_id_norm"].isin(axis_transects))
                )
            else:
                mask = (
                    (working["cone_id_norm"] == row["cone_id_norm"])
                    & (working["transect_id_norm"] == row["transect_id_norm"])
                    & (working["type_norm"] == row["type_norm"])
                )
        else:
            mask = (
                (working["cone_id_norm"] == row["cone_id_norm"])
                & (working["transect_id_norm"] == row["transect_id_norm"])
                & (working["type_norm"] == row["type_norm"])
            )
        if not mask.any():
            continue

        indices = working[mask].index
        for idx in indices:
            working.at[idx, "x_geo"] = float(row["x_geo"])
            working.at[idx, "y_geo"] = float(row["y_geo"])
            working.at[idx, "elevation"] = float(row["elevation"])
            applied += 1

    working = working.drop(columns=["cone_id_norm", "transect_id_norm", "type_norm"])
    print(f"{GREEN}✔ Applied manual fix overrides to {applied} point(s){RESET}")
    return working

# pylint: disable-next=too-many-locals,too-many-branches,too-many-statements
def main():
    """Perform morphometric analysis of cone-like landforms.

    Loads configuration, processes cone profiles, calculates metrics
    (height, width, volume, shape), and exports results as CSV and
    GeoPackage files. Also generates ellipse fits for cone bases and
    crater center points.
    """
    hybrid_results = []
    with open("config.json", encoding="utf-8") as f:
        config = json.load(f)

    base = config["paths"]["base"]
    crs = config["shape"]["crs"]
    csv_sep = config["csv"].get("sep", ";")
    export_geojson = config.get("export_geojson", True)
    manual_fix_config = config.get("manual_fix", {})
    use_manual_fix = manual_fix_config.get("enabled", False)
    quality_thresholds, quality_preset = _resolve_quality_thresholds(config)
    print(f"{YELLOW}✔ Quality preset: {quality_preset}{RESET}")

    profiles_dir = join(base, config["paths"]["input"]["profiles"])
    points_file = join(base, config["paths"]["input"]["points"], "finder_method.csv")
    output_csv = (
        join(base, "output/analyzer/fix_results.csv")
        if use_manual_fix
        else join(base, config["paths"]["output"]["csv"])
    )
    cone_output_csv = (
        join(base, "output/analyzer/fix_cone_summary.csv")
        if use_manual_fix
        else join(base, "output/analyzer/cone_summary.csv")
    )
    output_shapes_dir = join(base, config["paths"]["output"]["shapes"])

    os.makedirs(output_shapes_dir, exist_ok=True)

    print(f"{YELLOW}✔ Reading profile points and detected features{RESET}")
    profiles = pd.concat(
        [
            pd.read_csv(join(profiles_dir, f), sep=csv_sep)
            for f in os.listdir(profiles_dir)
            if f.endswith(".csv")
        ],
        ignore_index=True,
    )
    gdf_profiles = gpd.GeoDataFrame(
        profiles, geometry=gpd.points_from_xy(profiles.x_geo, profiles.y_geo), crs=crs
    )

    features = pd.read_csv(points_file, sep=csv_sep)
    if use_manual_fix:
        overrides_rel = manual_fix_config.get(
            "overrides_csv", "output/figures/cross_sections/manual_point_overrides.csv"
        )
        overrides_path = join(base, overrides_rel)
        print(f"{YELLOW}✔ Applying manual point fixes from: {overrides_path}{RESET}")
        features = apply_manual_point_overrides(features, overrides_path, csv_sep)

    gdf_features = gpd.GeoDataFrame(
        features, geometry=gpd.points_from_xy(features.x_geo, features.y_geo), crs=crs
    )

    results = []

    grouped = gdf_features.groupby("transect_id")
    for transect_id, group in tqdm(grouped, desc="Analyzing profiles"):
        cone_id = group["cone_id"].iloc[0]
        subset = gdf_profiles[gdf_profiles["transect_id"] == transect_id].sort_values(
            "distance"
        )

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

            bottom_width = (
                (bottom_last.x_geo - bottom_first.x_geo) ** 2
                + (bottom_last.y_geo - bottom_first.y_geo) ** 2
            ) ** 0.5
            width = round(bottom_width, 3)
        else:
            width = 0

        if len(top) >= 2:
            top_first = top.iloc[0]
            top_last = top.iloc[-1]
            top_width = (
                (top_last.x_geo - top_first.x_geo) ** 2
                + (top_last.y_geo - top_first.y_geo) ** 2
            ) ** 0.5
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

        results.append(
            {
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
                "shape": shape_class,
            }
        )

        if export_geojson:
            group_out = group.copy()
            line = LineString(subset.geometry.tolist())
            shape_path = join(
                output_shapes_dir, f"cone_{cone_id}_{transect_id}.geojson"
            )
            group_out["geometry_type"] = group_out["type"]
            group_out = pd.concat(
                [
                    group_out,
                    gpd.GeoDataFrame(
                        [{"geometry": line, "geometry_type": "profile_line"}], crs=crs
                    ),
                ]
            )
            group_out.to_file(shape_path, driver="GeoJSON")

    df_out = pd.DataFrame(results)
    # Preserve per-transect classification in results output.
    df_out["shape_transect"] = df_out["shape"]

    df_cone_base = (
        df_out.groupby("cone_id")
        .agg(
            {
                "height": "mean",
                "bottom_width": "mean",
                "top_elev": "mean",
                "bottom_elev": "mean",
                "center_elev": "mean",
                "center_to_top_diff": "mean",
                "center_x": "mean",
                "center_y": "mean",
            }
        )
        .reset_index()
    )

    def _rmse_around_mean(series: pd.Series) -> float | None:
        values = pd.to_numeric(series, errors="coerce").dropna().to_numpy(dtype=float)
        if values.size == 0:
            return None
        mean_val = float(np.mean(values))
        return float(np.sqrt(np.mean((values - mean_val) ** 2)))

    df_uncertainty = (
        df_out.groupby("cone_id")
        .agg(
            {
                "transect_id": "count",
                "height": _rmse_around_mean,
                "bottom_width": _rmse_around_mean,
                "top_width": _rmse_around_mean,
                "top_elev": _rmse_around_mean,
                "bottom_elev": _rmse_around_mean,
                "center_elev": _rmse_around_mean,
                "center_to_top_diff": _rmse_around_mean,
            }
        )
        .reset_index()
        .rename(
            columns={
                "transect_id": "n_transects",
                "height": "rmse_height",
                "bottom_width": "rmse_bottom_width",
                "top_width": "rmse_top_width",
                "top_elev": "rmse_top_elev",
                "bottom_elev": "rmse_bottom_elev",
                "center_elev": "rmse_center_elev",
                "center_to_top_diff": "rmse_center_to_top_diff",
            }
        )
    )

    df_cone_base = df_cone_base.merge(df_uncertainty, on="cone_id", how="left")

    def _cone_shape_from_votes(shape_series: pd.Series) -> str | None:
        votes = shape_series.dropna().astype(str)
        if votes.empty:
            return None
        counts = votes.value_counts()
        top_shape = str(counts.index[0])
        top_count = int(counts.iloc[0])
        total_count = int(counts.sum())
        if top_count <= (total_count / 2.0):
            return "mixed"
        return top_shape

    shape_cone = df_out.groupby("cone_id")["shape_transect"].agg(_cone_shape_from_votes)
    df_cone_base["shape"] = df_cone_base["cone_id"].map(shape_cone)

    cone_metrics = []

    gdf_bottom = gdf_features[
        gdf_features["type"].str.contains("bottom", regex=True)
    ].copy()
    gdf_top = gdf_features[gdf_features["type"].str.contains("top", regex=True)].copy()

    bottom_clean_list = []
    top_clean_list = []

    print(
        f"{YELLOW}✔ Calculating advanced morphometric parameters for each cone...{RESET}"
    )
    for cone_id in tqdm(df_out["cone_id"].unique(), desc="Analyzing cone geometry"):
        bottom_points = gdf_bottom[gdf_bottom["cone_id"] == cone_id]
        top_points = gdf_top[gdf_top["cone_id"] == cone_id]
        cone_rows = df_out[df_out["cone_id"] == cone_id]
        bottom_width_mean = pd.to_numeric(
            cone_rows["bottom_width"], errors="coerce"
        ).dropna().mean()
        top_width_mean = pd.to_numeric(
            cone_rows["top_width"], errors="coerce"
        ).dropna().mean()

        bottom_clean = filter_iqr(bottom_points)
        top_clean = filter_iqr(top_points)

        bottom_clean_list.append(bottom_clean)
        top_clean_list.append(top_clean)
        base_area, major_diameter_b, minor_diameter_b, ellipticity, azimuth = (
            None,
            None,
            None,
            None,
            None,
        )
        major_diameter_t, minor_diameter_t = None, None
        volume, avg_slope, h_wb_ratio, wcr_wb_ratio = None, None, None, None
        xc_b, yc_b, theta_b = None, None, None
        xc_t, yc_t, theta_t = None, None, None
        coords_b = np.array(list(zip(bottom_clean.geometry.x, bottom_clean.geometry.y)))
        coords_t = np.array(list(zip(top_clean.geometry.x, top_clean.geometry.y)))
        if coords_b.size > 0:
            coords_b = np.unique(coords_b, axis=0)
        if coords_t.size > 0:
            coords_t = np.unique(coords_t, axis=0)

        if len(coords_b) >= 5:
            ell_b = EllipseModel()
            success_b = len(coords_b) >= 5 and ell_b.estimate(coords_b)

            if success_b and ell_b.params is not None:
                xc_b, yc_b, a_b, b_b, theta_b = ell_b.params

                major_diameter_b = 2 * a_b
                minor_diameter_b = 2 * b_b
                base_area = math.pi * a_b * b_b
                ellipticity = 1 - (b_b / a_b)
                azimuth = (90 - math.degrees(theta_b)) % 180

                if (
                    pd.notna(bottom_width_mean)
                    and bottom_width_mean > 0
                    and major_diameter_b > (bottom_width_mean * 5.0)
                ):
                    major_diameter_b = None
                    minor_diameter_b = None
                    base_area = None
                    ellipticity = None
                    azimuth = None
                    xc_b, yc_b, theta_b = None, None, None

        if major_diameter_b is None and pd.notna(bottom_width_mean) and bottom_width_mean > 0:
            major_diameter_b = float(bottom_width_mean)
            minor_diameter_b = float(bottom_width_mean)
            radius_b = major_diameter_b / 2.0
            base_area = math.pi * radius_b * radius_b
            ellipticity = 0.0
            if len(coords_b) > 0:
                xc_b = float(np.mean(coords_b[:, 0]))
                yc_b = float(np.mean(coords_b[:, 1]))
            if len(coords_b) >= 2:
                centered_b = coords_b - np.mean(coords_b, axis=0)
                cov_b = np.cov(centered_b.T)
                eigvals_b, eigvecs_b = np.linalg.eigh(cov_b)
                principal_b = eigvecs_b[:, int(np.argmax(eigvals_b))]
                theta_b = math.atan2(float(principal_b[1]), float(principal_b[0]))
                azimuth = (90 - math.degrees(theta_b)) % 180

        if len(coords_t) >= 5:
            ell_t = EllipseModel()
            success_t = len(coords_t) >= 5 and ell_t.estimate(coords_t)

            if success_t and ell_t.params is not None:
                xc_t, yc_t, a_t, b_t, theta_t = ell_t.params
                major_diameter_t = 2 * a_t
                minor_diameter_t = 2 * b_t

        if major_diameter_t is None and pd.notna(top_width_mean) and top_width_mean > 0:
            major_diameter_t = float(top_width_mean)
            minor_diameter_t = float(top_width_mean)
            if len(coords_t) > 0:
                xc_t = float(np.mean(coords_t[:, 0]))
                yc_t = float(np.mean(coords_t[:, 1]))
            if len(coords_t) >= 2:
                centered_t = coords_t - np.mean(coords_t, axis=0)
                cov_t = np.cov(centered_t.T)
                eigvals_t, eigvecs_t = np.linalg.eigh(cov_t)
                principal_t = eigvecs_t[:, int(np.argmax(eigvals_t))]
                theta_t = math.atan2(float(principal_t[1]), float(principal_t[0]))

        height = df_cone_base.loc[df_cone_base["cone_id"] == cone_id, "height"].iloc[0]

        if (
            height is not None
            and major_diameter_b is not None
            and major_diameter_t is not None
        ):
            R = major_diameter_b / 2  # pylint: disable=invalid-name
            r = major_diameter_t / 2

            # Volume of a cone: V = (1/3) * pi * h * (R^2 + R*r + r^2)
            volume = (1 / 3) * math.pi * height * (R**2 + R * r + r**2)

            # Average slope gradient
            if (R - r) > 0:
                slope_rad = math.atan(height / (R - r))
                avg_slope = math.degrees(slope_rad)

        # Calculation of indicators
        if height is not None and major_diameter_b is not None and major_diameter_b > 0:
            h_wb_ratio = height / major_diameter_b

        if (
            major_diameter_t is not None
            and major_diameter_b is not None
            and major_diameter_b > 0
        ):
            wcr_wb_ratio = major_diameter_t / major_diameter_b

        cone_metrics.append(
            {
                "cone_id": cone_id,
                "base_area": base_area,
                "base_major_diameter (WCO)": major_diameter_b,
                "base_minor_diameter": minor_diameter_b,
                "base_center_x": xc_b,
                "base_center_y": yc_b,
                "base_angle_deg": safe_degrees(theta_b),
                "top_major_diameter (WCR)": major_diameter_t,
                "top_minor_diameter": minor_diameter_t,
                "top_center_x": xc_t,
                "top_center_y": yc_t,
                "top_angle_deg": safe_degrees(theta_t),
                "volume": volume,
                "base_ellipticity": ellipticity,
                "elongation_azimuth": azimuth,
                "avg_slope_deg": avg_slope,
                "H_WCO_ratio": h_wb_ratio,
                "WCR_WCO_ratio": wcr_wb_ratio,
            }
        )

    gdf_bottom_clean = gpd.GeoDataFrame(
        pd.concat(bottom_clean_list, ignore_index=True), crs=crs
    )
    gdf_top_clean = gpd.GeoDataFrame(
        pd.concat(top_clean_list, ignore_index=True), crs=crs
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

    def _safe_ratio(numerator: float, denominator: float) -> float | None:
        num = pd.to_numeric(pd.Series([numerator]), errors="coerce").iloc[0]
        den = pd.to_numeric(pd.Series([denominator]), errors="coerce").iloc[0]
        if pd.isna(num) or pd.isna(den) or den == 0:
            return None
        return float(num / den)

    df_cone["rmse_height_ratio"] = df_cone.apply(
        lambda row: _safe_ratio(row.get("rmse_height"), row.get("height")), axis=1
    )
    df_cone["rmse_bottom_width_ratio"] = df_cone.apply(
        lambda row: _safe_ratio(row.get("rmse_bottom_width"), row.get("bottom_width")), axis=1
    )

    # ── Settle (1979) height correction ──────────────────────────────────────
    # H_co = A_co - (A_BM + A_Bm) / 2  where A_BM = global max basal elev,
    # A_Bm = global min basal elev across all transects of the cone.
    # This reference level (A_avg) is independent of transect azimuth,
    # so it removes the tilt-of-base component from height variability.
    settle_rows = []
    for cone_id, grp in df_out.groupby("cone_id"):
        top_mean = grp["top_elev"].mean()
        bot_max = grp["bottom_elev"].max()   # A_BM
        bot_min = grp["bottom_elev"].min()   # A_Bm
        a_avg = (bot_max + bot_min) / 2.0    # A_avg
        h_settle = top_mean - a_avg
        base_asym = _safe_ratio(bot_max - bot_min, h_settle)  # (A_BM-A_Bm)/H

        # Per-transect height measured from the same Settle A_avg:
        # h_i = top_i - A_avg  → RMSE around h_settle reflects only detection noise
        h_per = grp["top_elev"] - a_avg
        vals = pd.to_numeric(h_per, errors="coerce").dropna().to_numpy(float)
        rmse_settle = float(np.sqrt(np.mean((vals - h_settle) ** 2))) if vals.size else None

        settle_rows.append(
            {
                "cone_id": cone_id,
                "height_settle": round(h_settle, 3),
                "base_elev_max": round(bot_max, 3),
                "base_elev_min": round(bot_min, 3),
                "base_asymmetry": round(base_asym, 4) if base_asym is not None else None,
                "rmse_height_settle": round(rmse_settle, 3) if rmse_settle is not None else None,
            }
        )
    df_settle = pd.DataFrame(settle_rows)
    df_cone = df_cone.merge(df_settle, on="cone_id", how="left")

    df_cone["rmse_height_settle_ratio"] = df_cone.apply(
        lambda row: _safe_ratio(row.get("rmse_height_settle"), row.get("height_settle")), axis=1
    )

    # Remove azimuthal base-tilt component from bottom_elev RMSE.
    # Model per-cone bottom trend as: z(theta) = c0 + c1*cos(theta) + c2*sin(theta).
    # Residual RMSE approximates detection/local-roughness variability.
    bottom_detrended_rows = []
    for cone_id, grp in df_out.groupby("cone_id"):
        work = grp[["transect_id", "bottom_elev"]].copy()
        work["axis_deg"] = work["transect_id"].apply(angle_from_transect_id)
        work = work.dropna(subset=["axis_deg", "bottom_elev"])

        rmse_bottom_detrended = None
        rmse_bottom_tilt_amp = None
        if len(work) >= 3:
            theta = np.deg2rad(pd.to_numeric(work["axis_deg"], errors="coerce").to_numpy(float))
            z = pd.to_numeric(work["bottom_elev"], errors="coerce").to_numpy(float)
            valid = np.isfinite(theta) & np.isfinite(z)
            theta = theta[valid]
            z = z[valid]

            if len(z) >= 3:
                design_matrix = np.column_stack(
                    [np.ones_like(theta), np.cos(theta), np.sin(theta)]
                )
                beta, *_ = np.linalg.lstsq(design_matrix, z, rcond=None)
                z_fit = design_matrix @ beta
                resid = z - z_fit
                rmse_bottom_detrended = float(np.sqrt(np.mean(resid**2)))
                rmse_bottom_tilt_amp = float(np.sqrt(beta[1] ** 2 + beta[2] ** 2))

        bottom_detrended_rows.append(
            {
                "cone_id": cone_id,
                "rmse_bottom_elev_detrended": round(rmse_bottom_detrended, 3)
                if rmse_bottom_detrended is not None
                else None,
                "rmse_bottom_elev_tilt_amp": round(rmse_bottom_tilt_amp, 3)
                if rmse_bottom_tilt_amp is not None
                else None,
            }
        )

    df_bottom_detrended = pd.DataFrame(bottom_detrended_rows)
    df_cone = df_cone.merge(df_bottom_detrended, on="cone_id", how="left")
    # ─────────────────────────────────────────────────────────────────────────

    # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    def _quality_assessment(
        row: pd.Series,
    ) -> pd.Series:
        n_transects = pd.to_numeric(
            pd.Series([row.get("n_transects")]), errors="coerce"
        ).iloc[0]
        rmse_height_ratio = pd.to_numeric(
            pd.Series([row.get("rmse_height_ratio")]), errors="coerce"
        ).iloc[0]
        rmse_height_settle_ratio = pd.to_numeric(
            pd.Series([row.get("rmse_height_settle_ratio")]), errors="coerce"
        ).iloc[0]
        rmse_bottom_width_ratio = pd.to_numeric(
            pd.Series([row.get("rmse_bottom_width_ratio")]), errors="coerce"
        ).iloc[0]
        rmse_bottom_elev = pd.to_numeric(
            pd.Series([row.get("rmse_bottom_elev")]), errors="coerce"
        ).iloc[0]
        rmse_bottom_elev_detrended = pd.to_numeric(
            pd.Series([row.get("rmse_bottom_elev_detrended")]), errors="coerce"
        ).iloc[0]
        rmse_center_to_top_diff = pd.to_numeric(
            pd.Series([row.get("rmse_center_to_top_diff")]), errors="coerce"
        ).iloc[0]

        severe = 0
        moderate = 0
        reasons = []

        if not pd.isna(n_transects) and n_transects < quality_thresholds["n_transects_min"]:
            severe += 1
            reasons.append("few_transects")

        # Use Settle-corrected ratio as primary height quality metric;
        # fall back to legacy rmse_height_ratio if not available.
        h_ratio_for_qa = (
            rmse_height_settle_ratio
            if not pd.isna(rmse_height_settle_ratio)
            else rmse_height_ratio
        )
        if not pd.isna(h_ratio_for_qa):
            if h_ratio_for_qa > quality_thresholds["height_ratio_high"]:
                severe += 1
                reasons.append("height_ratio_high")
            elif h_ratio_for_qa > quality_thresholds["height_ratio_mid"]:
                moderate += 1
                reasons.append("height_ratio_mid")

        if not pd.isna(rmse_bottom_width_ratio):
            if rmse_bottom_width_ratio > quality_thresholds["bottom_width_ratio_high"]:
                severe += 1
                reasons.append("bottom_width_ratio_high")
            elif rmse_bottom_width_ratio > quality_thresholds["bottom_width_ratio_mid"]:
                moderate += 1
                reasons.append("bottom_width_ratio_mid")

        # Use detrended bottom RMSE when available to avoid over-penalizing
        # cones on tilted bases; otherwise keep legacy behavior.
        bottom_rmse_for_qa = (
            rmse_bottom_elev_detrended
            if not pd.isna(rmse_bottom_elev_detrended)
            else rmse_bottom_elev
        )
        if not pd.isna(bottom_rmse_for_qa):
            if bottom_rmse_for_qa > quality_thresholds["bottom_elev_rmse_high"]:
                severe += 1
                reasons.append("bottom_elev_rmse_high")
            elif bottom_rmse_for_qa > quality_thresholds["bottom_elev_rmse_mid"]:
                moderate += 1
                reasons.append("bottom_elev_rmse_mid")

        if not pd.isna(rmse_center_to_top_diff):
            if rmse_center_to_top_diff > quality_thresholds["center_top_rmse_high"]:
                severe += 1
                reasons.append("center_top_rmse_high")
            elif rmse_center_to_top_diff > quality_thresholds["center_top_rmse_mid"]:
                moderate += 1
                reasons.append("center_top_rmse_mid")

        if severe >= 2:
            flag = "poor"
        elif severe == 1 or moderate >= 1:
            flag = "moderate"
        else:
            flag = "good"

        score = {"good": 2, "moderate": 1, "poor": 0}[flag]
        reason_text = ";".join(reasons) if reasons else "none"
        return pd.Series(
            {"quality_flag": flag, "quality_score": score, "quality_reasons": reason_text}
        )

    quality_df = df_cone.apply(_quality_assessment, axis=1)
    df_cone[["quality_flag", "quality_score", "quality_reasons"]] = quality_df

    # Detect impact craters: if depth > height, reclassify as 'impact_crater'
    # This takes precedence over concave/flat/convex classification
    mask_crater = (
        (df_cone["depth"] > df_cone["height"])
        & (df_cone["depth"].notna())
        & (df_cone["height"].notna())
    )
    df_cone.loc[mask_crater, "shape"] = "impact_crater"

    # Keep transect-level class in `shape`; expose cone-level class separately.
    cone_shapes = df_cone[["cone_id", "shape"]].set_index("cone_id")["shape"]
    df_out["shape_cone"] = df_out["cone_id"].map(cone_shapes)
    df_out["shape"] = df_out["shape_transect"]

    # Export updated results.csv with both transect and cone classifications
    df_out.to_csv(output_csv, sep=csv_sep, index=False, encoding="utf-8")
    print(f"{YELLOW}✔ Exported {len(df_out)} measurements to {output_csv}{RESET}")

    df_cone.to_csv(cone_output_csv, sep=csv_sep, index=False, encoding="utf-8")
    print(f"{YELLOW}✔ Exported aggregated results to {cone_output_csv}{RESET}")

    print(f"{YELLOW}✔ Generating GeoJSON buffers for cones by shape{RESET}")

    geojson_dir = os.path.join(base, "output/analyzer/shapes")
    os.makedirs(geojson_dir, exist_ok=True)

    gdf_cones = gpd.GeoDataFrame(
        df_cone,
        geometry=gpd.points_from_xy(df_cone["center_x"], df_cone["center_y"]),
        crs=crs,
    )

    gdf_cones["geometry"] = gdf_cones.geometry.buffer(gdf_cones["bottom_width"] / 2)

    for shape_class in gdf_cones["shape"].dropna().unique():
        shape_gdf = gdf_cones[gdf_cones["shape"] == shape_class]
        shape_path = os.path.join(geojson_dir, f"{shape_class}_cones.gpkg")
        shape_gdf.to_file(shape_path, driver="GPKG")
        print(f"{GREEN}✔ Saved: {shape_path}{RESET}")

    print(
        f"{YELLOW}✔ Computing crater centers using top points and least squares{RESET}"
    )

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
            dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
            iqr = np.percentile(dist, 75) - np.percentile(dist, 25)
            mask = dist < (np.percentile(dist, 75) + 1.5 * iqr)
            x = x[mask]
            y = y[mask]

        x_center = np.mean(x)
        y_center = np.mean(y)

        center_results.append(
            {
                "cone_id": cone_id,
                "x_geo": x_center,
                "y_geo": y_center,
                "geometry": Point(x_center, y_center),
            }
        )

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
        input_points_gdf["geometry"] = input_points_gdf.geometry.apply(to_point_geometry)
        input_points_gdf = input_points_gdf[input_points_gdf.geometry.notna()].copy()

        if "cone_id" not in input_points_gdf.columns:
            if "id" in input_points_gdf.columns:
                input_points_gdf = input_points_gdf.rename(columns={"id": "cone_id"})
            elif "Id" in input_points_gdf.columns:
                input_points_gdf = input_points_gdf.rename(columns={"Id": "cone_id"})
            elif "name" in input_points_gdf.columns:
                input_points_gdf = input_points_gdf.rename(columns={"name": "cone_id"})
            else:
                print(
                    f"{RED}✘ No valid ID column found in input center file. "
                    f"Expected 'cone_id', 'id', 'Id' or 'name'.{RESET}"
                )
                input_points_gdf["cone_id"] = None

        input_center_out = os.path.join(
            base, "output/analyzer/shapes/centers_input.gpkg"
        )
        input_points_gdf.to_file(input_center_out, driver="GPKG")
        print(f"{GREEN}✔ Saved input center points to {input_center_out}{RESET}")

    print(f"{YELLOW}✔ Computing hybrid crater centers (top + expert point){RESET}")

    hybrid_results = []

    if input_points_gdf is not None:
        for cone_id, group in gdf_top.groupby("cone_id"):
            input_point = input_points_gdf[
                input_points_gdf["cone_id"].astype(str) == str(cone_id)
            ]

            if input_point.empty:
                continue

            x = group["x_geo"].values
            y = group["y_geo"].values

            input_x = input_point.geometry.x.values[0]
            input_y = input_point.geometry.y.values[0]

            if len(group) >= 4:
                cx = np.median(x)
                cy = np.median(y)
                dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
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

            hybrid_results.append(
                {
                    "cone_id": cone_id,
                    "x_geo": hybrid_x,
                    "y_geo": hybrid_y,
                    "geometry": Point(hybrid_x, hybrid_y),
                }
            )

        if hybrid_results:
            gdf_hybrid = gpd.GeoDataFrame(hybrid_results, geometry="geometry", crs=crs)
            hybrid_out_path = os.path.join(
                base, "output/analyzer/shapes/centers_hybrid.gpkg"
            )
            gdf_hybrid.to_file(hybrid_out_path, driver="GPKG")
            print(f"{GREEN}✔ Saved hybrid center points to {hybrid_out_path}{RESET}")
        else:
            print(
                f"{RED}✘ No hybrid centers computed – check if cone_id values "
                f"match between top points and expert points.{RESET}"
            )

        if hybrid_results:
            df_hybrid = pd.DataFrame(hybrid_results)
            df_hybrid = df_hybrid.rename(
                columns={"x_geo": "hybrid_x", "y_geo": "hybrid_y"}
            )
            df_cone = df_cone.merge(
                df_hybrid[["cone_id", "hybrid_x", "hybrid_y"]], on="cone_id", how="left"
            )
        else:
            df_cone["hybrid_x"] = None
            df_cone["hybrid_y"] = None

        df_cone.to_csv(cone_output_csv, sep=csv_sep, index=False, encoding="utf-8")
        print(f"{YELLOW}✔ Updated {cone_output_csv} with hybrid coordinates{RESET}")

    else:
        print(
            f"{RED}✘ Skipping hybrid center calculation – no expert file found.{RESET}"
        )

    #  Summary GeoPackage with full representation of cones
    print(
        f"{YELLOW}✔ Exporting unified GeoPackage with cleaned points and fitted ellipses{RESET}"
    )

    summary_rel = config.get("output", {}).get(
        "summary_gpkg", "output/analyzer/marscone.gpkg"
    )
    summary_gpkg = os.path.join(base, summary_rel)

    os.makedirs(os.path.dirname(summary_gpkg), exist_ok=True)

    if os.path.exists(summary_gpkg):
        os.remove(summary_gpkg)

    gdf_bottom_clean.to_file(
        summary_gpkg, layer="points_bottom_near_and_far", driver="GPKG"
    )
    gdf_top_clean.to_file(summary_gpkg, layer="points_top", driver="GPKG")

    ellipse_base_rows = []
    ellipse_top_rows = []

    for _, row in df_cone.iterrows():
        cone_id = row["cone_id"]
        cx = row.get("top_center_x", row["center_x"])
        cy = row.get("top_center_y", row["center_y"])

        # base ellipse
        if not pd.isna(row.get("base_major_diameter", np.nan)) and not pd.isna(
            row.get("base_minor_diameter", np.nan)
        ):
            poly_b = ellipse_to_polygon(
                cx=cx,
                cy=cy,
                major_diameter=row["base_major_diameter"],
                minor_diameter=row["base_minor_diameter"],
                angle_deg=row.get("elongation_azimuth", 0.0),
            )
            ellipse_base_rows.append(
                {
                    "cone_id": cone_id,
                    "geometry": poly_b,
                    "shape": row.get("shape", None),
                    "base_major_diameter": row["base_major_diameter"],
                    "base_minor_diameter": row["base_minor_diameter"],
                    "base_area": row.get("base_area", None),
                    "elongation_azimuth": row.get("elongation_azimuth", None),
                }
            )

        # top ellipse
        if not pd.isna(row.get("top_major_diameter", np.nan)) and not pd.isna(
            row.get("top_minor_diameter", np.nan)
        ):
            poly_t = ellipse_to_polygon(
                cx=cx,
                cy=cy,
                major_diameter=row["top_major_diameter"],
                minor_diameter=row["top_minor_diameter"],
                angle_deg=row.get("elongation_azimuth", 0.0),
            )
            ellipse_top_rows.append(
                {
                    "cone_id": cone_id,
                    "geometry": poly_t,
                    "top_major_diameter": row["top_major_diameter"],
                    "top_minor_diameter": row["top_minor_diameter"],
                }
            )

    if ellipse_base_rows:
        gdf_ellipse_base = gpd.GeoDataFrame(
            ellipse_base_rows, geometry="geometry", crs=crs
        )
        gdf_ellipse_base.to_file(summary_gpkg, layer="ellipse_base", driver="GPKG")

    if ellipse_top_rows:
        gdf_ellipse_top = gpd.GeoDataFrame(
            ellipse_top_rows, geometry="geometry", crs=crs
        )
        gdf_ellipse_top.to_file(summary_gpkg, layer="ellipse_top", driver="GPKG")

    points_axis_rows = []

    if not gdf_bottom_clean.empty:
        for (cone_id, transect_id), sub in gdf_bottom_clean.groupby(
            ["cone_id", "transect_id"]
        ):
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
        gdf_bottom_axis = gpd.GeoDataFrame(
            points_axis_rows, geometry="geometry", crs=crs
        )
        gdf_bottom_axis.to_file(summary_gpkg, layer="points_bottom", driver="GPKG")
        print(
            f"{GREEN}✔ Saved per-transect bottom points to layer 'points_bottom'{RESET}"
        )

    centers_path = os.path.join(base, "output/analyzer/centers.gpkg")
    centers_input_path = os.path.join(base, "output/analyzer/centers_input.gpkg")
    centers_hybrid_path = os.path.join(base, "output/analyzer/centers_hybrid.gpkg")

    if os.path.exists(centers_path):
        gpd.read_file(centers_path).to_file(
            summary_gpkg, layer="centroid_top", driver="GPKG"
        )
    if os.path.exists(centers_input_path):
        gpd.read_file(centers_input_path).to_file(
            summary_gpkg, layer="centroid_input", driver="GPKG"
        )
    if os.path.exists(centers_hybrid_path):
        gpd.read_file(centers_hybrid_path).to_file(
            summary_gpkg, layer="centroid_hybrid", driver="GPKG"
        )

    print(f"{GREEN}✔ Saved unified GeoPackage to {summary_gpkg}{RESET}")


if __name__ == "__main__":
    main()
