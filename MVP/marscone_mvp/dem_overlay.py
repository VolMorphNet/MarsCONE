"""Generate DEM overlay figures for cone diagnostics in MVP."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.lines import Line2D


# pylint: disable=too-many-instance-attributes
@dataclass
class DemOverlayConfig:
    """Configuration for DEM overlay rendering and export."""

    dem_dir: Path
    gpkg_path: Path
    output_dir: Path
    selected_cone_ids: list[str]
    dpi: int = 220
    azimuth_deg: float = 315.0
    altitude_deg: float = 45.0
    centers_hybrid_path: Path | None = None
    use_manual_fix_metrics: bool = False


def _compute_hillshade(
    dem: np.ndarray,
    transform: rasterio.Affine,
    azimuth_deg: float,
    altitude_deg: float,
) -> np.ndarray:
    xres = abs(transform.a) if transform.a else 1.0
    yres = abs(transform.e) if transform.e else 1.0

    grad_y, grad_x = np.gradient(dem.astype(float), yres, xres)
    slope = np.pi / 2.0 - np.arctan(np.sqrt(grad_x * grad_x + grad_y * grad_y))
    aspect = np.arctan2(-grad_x, grad_y)

    azimuth = np.radians(azimuth_deg)
    altitude = np.radians(altitude_deg)

    shaded = (
        np.sin(altitude) * np.sin(slope)
        + np.cos(altitude) * np.cos(slope) * np.cos(azimuth - aspect)
    )
    shaded = np.clip(shaded, 0, 1)
    return shaded


def _parse_cone_id_from_filename(path: Path) -> str | None:
    match = re.match(r"cone_(\d+)_dem\.(?:tif|tiff)$", path.name, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1)


def _normalize_id_series(series: pd.Series) -> pd.Series:
    return series.astype(str).str.replace(r"\.0$", "", regex=True)


def _resolve_output_root_from_gpkg(gpkg_path: Path) -> Path:
    for parent in [gpkg_path.parent, *gpkg_path.parents]:
        if parent.name == "output":
            return parent

    if gpkg_path.parent.name == "db":
        return gpkg_path.parent.parent / "output"

    return gpkg_path.parent.parent


# pylint: disable=too-many-locals
def _apply_manual_overrides_to_points(
    points_gdf: gpd.GeoDataFrame,
    overrides_path: Path,
    logger: Callable[[str], None],
) -> gpd.GeoDataFrame:
    """Apply saved manual point overrides to a points GeoDataFrame."""
    if not overrides_path.exists():
        logger(f"Manual fix requested, but overrides file not found: {overrides_path}")
        return points_gdf

    overrides_df = pd.read_csv(overrides_path, sep=";")
    if overrides_df.empty:
        logger(f"Manual fix requested, but overrides file is empty: {overrides_path}")
        return points_gdf

    required_columns = {"cone_id", "transect_id", "type", "x_geo", "y_geo", "elevation"}
    if not required_columns.issubset(set(overrides_df.columns)):
        logger(
            "Manual fix requested, but overrides file has missing columns. "
            f"Expected: {sorted(required_columns)}"
        )
        return points_gdf

    updated = points_gdf.copy()
    updated["cone_id_norm"] = _normalize_id_series(updated["cone_id"])
    updated["transect_id_norm"] = updated["transect_id"].astype(str)
    updated["type_norm"] = updated["type"].astype(str)

    overrides_df = overrides_df.copy()
    overrides_df["cone_id_norm"] = _normalize_id_series(overrides_df["cone_id"])
    overrides_df["transect_id_norm"] = overrides_df["transect_id"].astype(str)
    overrides_df["type_norm"] = overrides_df["type"].astype(str)

    if "updated_at_utc" in overrides_df.columns:
        overrides_df = overrides_df.sort_values("updated_at_utc", kind="mergesort")

    overrides_latest = overrides_df.drop_duplicates(
        subset=["cone_id_norm", "transect_id_norm", "type_norm"],
        keep="last",
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
                    (updated["cone_id_norm"] == row["cone_id_norm"])
                    & (updated["type_norm"] == "C")
                    & (updated["transect_id_norm"].isin(axis_transects))
                )
            else:
                mask = (
                    (updated["cone_id_norm"] == row["cone_id_norm"])
                    & (updated["transect_id_norm"] == row["transect_id_norm"])
                    & (updated["type_norm"] == row["type_norm"])
                )
        else:
            mask = (
                (updated["cone_id_norm"] == row["cone_id_norm"])
                & (updated["transect_id_norm"] == row["transect_id_norm"])
                & (updated["type_norm"] == row["type_norm"])
            )
        if not mask.any():
            continue

        indices = updated[mask].index
        for idx in indices:
            updated.at[idx, "x_geo"] = float(row["x_geo"])
            updated.at[idx, "y_geo"] = float(row["y_geo"])
            if "elevation" in updated.columns:
                updated.at[idx, "elevation"] = float(row["elevation"])
            applied += 1

    updated["geometry"] = gpd.points_from_xy(updated["x_geo"], updated["y_geo"], crs=updated.crs)
    updated = updated.drop(columns=["cone_id_norm", "transect_id_norm", "type_norm"])
    logger(f"Applied manual point overrides for DEM overlay: {applied} point(s)")
    return updated


# pylint: disable=too-many-locals,too-many-branches,too-many-statements
def run_dem_overlays(
    config: DemOverlayConfig,
    log: Callable[[str], None] | None = None,
) -> pd.DataFrame:
    """Build hillshade overlay PNGs and export an index for selected cones."""

    logger = log if log is not None else (lambda _msg: None)

    config.output_dir.mkdir(parents=True, exist_ok=True)

    dem_files = sorted(
        list(config.dem_dir.glob("cone_*_dem.tif"))
        + list(config.dem_dir.glob("cone_*_dem.tiff"))
        + list(config.dem_dir.glob("cone_*_dem.TIF"))
        + list(config.dem_dir.glob("cone_*_dem.TIFF"))
    )
    cone_to_dem: dict[str, Path] = {}
    for dem_file in dem_files:
        cone_id = _parse_cone_id_from_filename(dem_file)
        if cone_id is not None:
            cone_to_dem[cone_id] = dem_file

    if config.selected_cone_ids:
        cone_ids = [str(item) for item in config.selected_cone_ids]
    else:
        cone_ids = sorted(cone_to_dem.keys(), key=int)

    points_gdf = gpd.read_file(config.gpkg_path, layer="points")
    transects_gdf = gpd.read_file(config.gpkg_path, layer="transects")

    output_root = _resolve_output_root_from_gpkg(config.gpkg_path)

    if config.use_manual_fix_metrics:
        overrides_path = (
            output_root / "figures" / "cross_sections" / "manual_point_overrides.csv"
        )
        points_gdf = _apply_manual_overrides_to_points(points_gdf, overrides_path, logger)

    points_gdf = points_gdf.copy()
    transects_gdf = transects_gdf.copy()
    points_gdf["cone_id_norm"] = _normalize_id_series(points_gdf["cone_id"])
    transects_gdf["cone_id_norm"] = _normalize_id_series(transects_gdf["cone_id"])

    hybrid_centers_gdf = None
    if config.centers_hybrid_path and config.centers_hybrid_path.exists():
        hybrid_centers_gdf = gpd.read_file(config.centers_hybrid_path)
        hybrid_centers_gdf = hybrid_centers_gdf.copy()
        hybrid_centers_gdf["cone_id_norm"] = _normalize_id_series(hybrid_centers_gdf["cone_id"])

    cone_summary_df = None
    summary_filename = (
        "fix_cone_summary.csv" if config.use_manual_fix_metrics else "cone_summary.csv"
    )
    cone_summary_path = output_root / "analyzer" / summary_filename
    if config.use_manual_fix_metrics and not cone_summary_path.exists():
        fallback_path = output_root / "analyzer" / "cone_summary.csv"
        logger(
            f"Manual fix metrics requested, but file not found: {cone_summary_path}. "
            f"Using fallback: {fallback_path}"
        )
        cone_summary_path = fallback_path
    if cone_summary_path.exists():
        cone_summary_df = pd.read_csv(cone_summary_path, sep=";")
        if "cone_id" in cone_summary_df.columns:
            cone_summary_df = cone_summary_df.copy()
            cone_summary_df["cone_id_norm"] = _normalize_id_series(cone_summary_df["cone_id"])

    results: list[dict] = []

    for cone_id in cone_ids:
        dem_path = cone_to_dem.get(cone_id)
        if dem_path is None:
            logger(f"[cone {cone_id}] DEM not found - skipped")
            continue

        logger(f"=== Cone {cone_id} ===")

        cone_points = points_gdf[points_gdf["cone_id_norm"] == cone_id]
        cone_transects = transects_gdf[transects_gdf["cone_id_norm"] == cone_id]

        with rasterio.open(dem_path) as src:
            dem_band = src.read(1, masked=True)
            dem = np.asarray(dem_band.filled(np.nan), dtype=float)
            bounds = src.bounds
            extent = [bounds.left, bounds.right, bounds.bottom, bounds.top]
            hillshade = _compute_hillshade(
                dem,
                src.transform,
                config.azimuth_deg,
                config.altitude_deg,
            )

        fig, ax = plt.subplots(figsize=(8, 8))
        ax.imshow(hillshade, cmap="gray", extent=extent, origin="upper")

        if not cone_transects.empty:
            cone_transects.plot(
                ax=ax,
                color="black",
                linewidth=1.2,
                linestyle="--",
                alpha=0.5,
                zorder=2,
            )

        if not cone_points.empty:
            point_types = cone_points["type"].astype(str)
            top_points = cone_points[point_types.str.contains("_top", na=False)]
            bottom_points = cone_points[point_types.str.contains("_bottom", na=False)].copy()
            center_points = cone_points[point_types == "C"]

            near_bottom_points = bottom_points.iloc[0:0]
            far_bottom_points = bottom_points.iloc[0:0]
            if not bottom_points.empty:
                if not center_points.empty:
                    center_x = float(center_points.geometry.x.mean())
                    center_y = float(center_points.geometry.y.mean())
                    bottom_sorted = bottom_points.copy()
                    bottom_sorted["dist_to_center"] = np.sqrt(
                        (bottom_sorted.geometry.x - center_x) ** 2
                        + (bottom_sorted.geometry.y - center_y) ** 2
                    )

                    def _axis_from_transect_id(value: object) -> int | None:
                        if not isinstance(value, str):
                            return None
                        try:
                            angle = float(value.split("_")[1].replace("deg", ""))
                            return int(round(angle)) % 180
                        except (ValueError, IndexError):
                            return None

                    axis_key = bottom_sorted["transect_id"].astype(str).apply(
                        _axis_from_transect_id
                    )
                    axis_key = axis_key.where(
                        axis_key.notna(),
                        bottom_sorted["transect_id"].astype(str),
                    )

                    dx = bottom_sorted.geometry.x - center_x
                    dy = bottom_sorted.geometry.y - center_y
                    axis_side: list[int] = []
                    for idx, key in axis_key.items():
                        if isinstance(key, (int, np.integer)):
                            theta = np.deg2rad(float(key))
                            proj = float(dx.loc[idx]) * np.cos(theta) + float(
                                dy.loc[idx]
                            ) * np.sin(theta)
                            axis_side.append(1 if proj >= 0 else -1)
                        else:
                            axis_side.append(1 if float(dx.loc[idx]) >= 0 else -1)

                    bottom_sorted["_axis_key"] = axis_key
                    bottom_sorted["_axis_side"] = axis_side

                    near_idx: list[int] = []
                    far_idx: list[int] = []
                    for _, grp in bottom_sorted.groupby(["_axis_key", "_axis_side"], sort=False):
                        grp = grp.sort_values("dist_to_center", kind="mergesort")
                        near_count = max(1, len(grp) // 2)
                        near_idx.extend(grp.index[:near_count].tolist())
                        far_idx.extend(grp.index[near_count:].tolist())

                    near_bottom_points = bottom_sorted.loc[near_idx].copy()
                    far_bottom_points = bottom_sorted.loc[far_idx].copy()
                else:
                    # Fallback without center: keep historical type-based split.
                    bottom_types = bottom_points["type"].astype(str)
                    near_bottom_points = bottom_points[
                        bottom_types.isin(["E_bottom", "N_bottom"])
                    ].copy()
                    far_bottom_points = bottom_points[
                        bottom_types.isin(["S_bottom", "W_bottom"])
                    ].copy()

            if not top_points.empty:
                top_points.plot(ax=ax, color="#1E40FF", markersize=42, zorder=6)
            if not near_bottom_points.empty:
                near_bottom_points.plot(ax=ax, color="#FDE725", markersize=42, zorder=6)
            if not far_bottom_points.empty:
                far_bottom_points.plot(ax=ax, color="#00B400", markersize=42, zorder=6)
            if not center_points.empty:
                center_points.plot(ax=ax, color="#FF1E1E", markersize=54, zorder=7)

        if hybrid_centers_gdf is not None:
            cone_hybrid_center = hybrid_centers_gdf[
                hybrid_centers_gdf["cone_id_norm"] == cone_id
            ]
            if not cone_hybrid_center.empty:
                cone_hybrid_center.plot(ax=ax, color="green", markersize=80, marker="*", zorder=8)

        legend_elements = [
            Line2D(
                [0],
                [0],
                color="black",
                linestyle="--",
                linewidth=1.2,
                label="Transects",
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor="#1E40FF",
                markeredgecolor="k",
                markersize=8,
                label="Top",
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor="#FF1E1E",
                markeredgecolor="k",
                markersize=9,
                label="Center",
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor="#FDE725",
                markeredgecolor="k",
                markersize=8,
                label="Bottom (near)",
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor="#00B400",
                markeredgecolor="k",
                markersize=8,
                label="Bottom (far)",
            ),
            Line2D(
                [0],
                [0],
                marker="*",
                color="w",
                markerfacecolor="green",
                markeredgecolor="k",
                markersize=12,
                label="Hybrid Center",
            ),
        ]
        ax.legend(handles=legend_elements, loc="upper right")

        if cone_summary_df is not None and "cone_id_norm" in cone_summary_df.columns:
            cone_row = cone_summary_df[cone_summary_df["cone_id_norm"] == cone_id]
            if not cone_row.empty:
                row = cone_row.iloc[0]
                wco = pd.to_numeric(row.get("base_major_diameter (WCO)"), errors="coerce")
                wcr = pd.to_numeric(row.get("top_major_diameter (WCR)"), errors="coerce")
                height = pd.to_numeric(row.get("height"), errors="coerce")
                depth = pd.to_numeric(row.get("depth"), errors="coerce")
                d_wcr = np.nan
                if pd.notna(depth) and pd.notna(wcr) and wcr > 0:
                    d_wcr = float(depth / wcr)

                metrics_lines = [
                    f"Wco: {wco:.2f} m" if pd.notna(wco) else "Wco: n/a",
                    f"Wcr: {wcr:.2f} m" if pd.notna(wcr) else "Wcr: n/a",
                    f"H: {height:.2f} m" if pd.notna(height) else "H: n/a",
                    f"D: {depth:.2f} m" if pd.notna(depth) else "D: n/a",
                    f"D/Wcr: {d_wcr:.3f}" if pd.notna(d_wcr) else "D/Wcr: n/a",
                ]
                ax.text(
                    0.98,
                    0.02,
                    "\n".join(metrics_lines),
                    transform=ax.transAxes,
                    ha="right",
                    va="bottom",
                    fontsize=9,
                    bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.8},
                )

        mode_label = "manual fix" if config.use_manual_fix_metrics else "standard"
        ax.set_title(
            f"Cone {cone_id} - DEM hillshade with points and transects [{mode_label}]"
        )
        ax.set_xlabel("Easting (m)")
        ax.set_ylabel("Northing (m)")
        ax.set_aspect("equal")
        ax.grid(False)

        out_path = config.output_dir / f"cone{cone_id}_overlay.png"
        fig.tight_layout()
        fig.savefig(out_path, dpi=config.dpi)
        plt.close(fig)

        logger(f"Saved: {out_path}")
        results.append(
            {
                "cone_id": cone_id,
                "dem_path": str(dem_path),
                "points_count": int(len(cone_points)),
                "transects_count": int(len(cone_transects)),
                "overlay_path": str(out_path),
            }
        )

    summary_df = pd.DataFrame(results)
    summary_path = config.output_dir / "dem_overlay_index.csv"
    summary_df.to_csv(summary_path, index=False, sep=";")
    logger(f"Overlay index saved: {summary_path}")
    logger("Done - DEM overlays generated")
    return summary_df
