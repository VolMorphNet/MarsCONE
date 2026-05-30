"""Cross-section plotting and metric utilities used by MVP."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D


@dataclass
class CrossSectionConfig:
    """Configuration for cross-section generation and export."""

    profile_dir: Path
    finder_path: Path
    output_dir: Path
    selected_cone_ids: list[str]
    dpi: int = 300
    angle_pair_tolerance_deg: float = 1e-3


METRIC_COLUMNS = ["Wco", "Wcr", "H_left", "H_right", "D_left", "D_right"]


def parse_deg(value: str) -> float:
    """Parse orientation text like '45deg' into float degrees."""
    return float(str(value).replace("deg", "").strip())


def attach_distance_to_finder_points(
    profile_df: pd.DataFrame,
    points_df: pd.DataFrame,
) -> pd.DataFrame:
    """Attach nearest profile distance values to finder points."""
    if points_df.empty:
        return points_df

    dx = profile_df["x_geo"].to_numpy()[None, :] - points_df["x_geo"].to_numpy()[:, None]
    dy = profile_df["y_geo"].to_numpy()[None, :] - points_df["y_geo"].to_numpy()[:, None]
    nearest_idx = (dx**2 + dy**2).argmin(axis=1)

    out = points_df.copy()
    out["distance"] = profile_df["distance"].to_numpy()[nearest_idx]
    return out


def _find_opposite_transect(
    transect_angles: dict[str, float],
    transect_id: str,
    base_angle: float,
) -> tuple[str | None, float]:
    complement = (base_angle + 180.0) % 360.0
    candidate = None
    best_diff = math.inf

    for tr2, ang2 in transect_angles.items():
        if tr2 == transect_id:
            continue
        diff = min(abs(ang2 - complement), 360.0 - abs(ang2 - complement))
        if diff < best_diff:
            best_diff = diff
            candidate = tr2

    return candidate, float(best_diff)


# pylint: disable=too-many-arguments,too-many-positional-arguments
# pylint: disable=too-many-locals,too-many-branches,too-many-statements
def _plot_axis_pair(
    cone_id: str,
    transect_a: str,
    transect_b: str,
    angle_axis: float,
    finder_df: pd.DataFrame,
    config: CrossSectionConfig,
) -> dict | None:
    def load_profile(transect_id: str) -> pd.DataFrame:
        path = config.profile_dir / f"profile_{transect_id}.csv"
        return pd.read_csv(path, sep=";")

    prof_a = load_profile(transect_a)
    prof_b = load_profile(transect_b)

    pts_a = finder_df[finder_df["transect_id"] == transect_a].copy()
    pts_b = finder_df[finder_df["transect_id"] == transect_b].copy()

    pts_a = attach_distance_to_finder_points(prof_a, pts_a)
    pts_b = attach_distance_to_finder_points(prof_b, pts_b)

    center_a = pts_a[pts_a["type"] == "C"]
    center_b = pts_b[pts_b["type"] == "C"]
    if center_a.empty or center_b.empty:
        return None

    ca_dist = float(center_a["distance"].iloc[0])
    ca_elev = float(center_a["elevation"].iloc[0])
    cb_dist = float(center_b["distance"].iloc[0])

    x_min = float(prof_a["distance"].min())
    x_max = float(prof_a["distance"].max())
    center_target = 0.5 * (x_min + x_max)

    prof_a_x = prof_a["distance"] - ca_dist + center_target
    prof_b_x = cb_dist - prof_b["distance"] + center_target

    def transform_x(distances: pd.Series, center_dist: float, mirror: bool = False) -> pd.Series:
        if mirror:
            return center_dist - distances + center_target
        return distances - center_dist + center_target

    pts_a["x_plot"] = transform_x(pts_a["distance"], ca_dist, mirror=False)
    pts_b["x_plot"] = transform_x(pts_b["distance"], cb_dist, mirror=True)

    all_pts = pd.concat([pts_a, pts_b], ignore_index=True)

    c_x = float(pts_a.loc[pts_a["type"] == "C", "x_plot"].iloc[0])
    c_z = ca_elev

    tops = all_pts[all_pts["type"].str.contains("_top", na=False)].copy().sort_values("x_plot")
    top_left = tops.iloc[0] if len(tops) >= 1 else None
    top_right = tops.iloc[-1] if len(tops) >= 2 else None
    tops_to_plot = []
    if top_left is not None:
        tops_to_plot.append(top_left)
    if top_right is not None and top_right is not top_left:
        tops_to_plot.append(top_right)

    bottoms = all_pts[all_pts["type"].str.contains("_bottom", na=False)].copy()
    bottoms_near: list[dict] = []
    bottoms_far: list[dict] = []
    bottom_left_near = None
    bottom_right_near = None

    if not bottoms.empty:
        left = bottoms[bottoms["x_plot"] < c_x].copy()
        if not left.empty:
            left_sorted = left.iloc[(left["x_plot"] - c_x).abs().argsort()]
            bottom_left_near = left_sorted.iloc[0]
            bottoms_near.append(bottom_left_near.to_dict())
            if len(left_sorted) > 1:
                bottoms_far.append(left_sorted.iloc[1].to_dict())

        right = bottoms[bottoms["x_plot"] >= c_x].copy()
        if not right.empty:
            right_sorted = right.iloc[(right["x_plot"] - c_x).abs().argsort()]
            bottom_right_near = right_sorted.iloc[0]
            bottoms_near.append(bottom_right_near.to_dict())
            if len(right_sorted) > 1:
                bottoms_far.append(right_sorted.iloc[1].to_dict())

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(prof_a_x, prof_a["elevation"], "k-", label=f"Profile {transect_a}")
    ax.plot(prof_b_x, prof_b["elevation"], "k--", label=f"Profile {transect_b}")

    for top in tops_to_plot:
        ax.scatter(top["x_plot"], top["elevation"], s=70, color="blue", edgecolor="k", zorder=5)

    ax.scatter(c_x, c_z, s=70, color="red", edgecolor="k", zorder=5)

    for btm in bottoms_near:
        ax.scatter(btm["x_plot"], btm["elevation"], s=70, color="yellow", edgecolor="k", zorder=5)

    for btm in bottoms_far:
        ax.scatter(btm["x_plot"], btm["elevation"], s=70, color="green", edgecolor="k", zorder=5)

    ax.set_xlabel("Distance (m)")
    ax.set_ylabel("Elevation (m)")
    ax.set_title(f"Cross section - cone {cone_id} (axis ~ {angle_axis:.0f} deg)")
    ax.grid(True, alpha=0.3)

    legend_elements = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor="blue",
            markeredgecolor="k",
            markersize=8,
            label="Top",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor="red",
            markeredgecolor="k",
            markersize=8,
            label="Center",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor="yellow",
            markeredgecolor="k",
            markersize=8,
            label="Bottom (near)",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor="green",
            markeredgecolor="k",
            markersize=8,
            label="Bottom (far)",
        ),
    ]
    ax.legend(handles=legend_elements, loc="upper right")

    h_left = d_left = None
    h_right = d_right = None
    wco = wcr = None
    d_wcr_left = d_wcr_right = None

    if top_left is not None and bottom_left_near is not None:
        h_left = float(top_left["elevation"] - bottom_left_near["elevation"])
        d_left = float(top_left["elevation"] - c_z)

    if top_right is not None and bottom_right_near is not None:
        h_right = float(top_right["elevation"] - bottom_right_near["elevation"])
        d_right = float(top_right["elevation"] - c_z)

    if bottom_left_near is not None and bottom_right_near is not None:
        wco = float(bottom_right_near["x_plot"] - bottom_left_near["x_plot"])

    if top_left is not None and top_right is not None:
        wcr = float(top_right["x_plot"] - top_left["x_plot"])

    if wcr is not None and wcr > 0:
        if d_left is not None:
            d_wcr_left = float(d_left / wcr)
        if d_right is not None:
            d_wcr_right = float(d_right / wcr)

    metrics_lines = []
    if wco is not None:
        metrics_lines.append(f"Wco = {wco:.2f} m")
    if wcr is not None:
        metrics_lines.append(f"Wcr = {wcr:.2f} m")
    if h_left is not None:
        metrics_lines.append(f"H_left = {h_left:.2f} m")
    if h_right is not None:
        metrics_lines.append(f"H_right = {h_right:.2f} m")
    if d_left is not None:
        metrics_lines.append(f"D_left = {d_left:.2f} m")
    if d_right is not None:
        metrics_lines.append(f"D_right = {d_right:.2f} m")
    if d_wcr_left is not None:
        metrics_lines.append(f"D_left/Wcr = {d_wcr_left:.3f}")
    if d_wcr_right is not None:
        metrics_lines.append(f"D_right/Wcr = {d_wcr_right:.3f}")

    text_str = "\n".join(metrics_lines) if metrics_lines else "No metrics\n(too few points)"
    ax.text(
        0.02,
        0.98,
        text_str,
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=9,
        bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.8},
    )

    out_name = f"cone{cone_id}_axis{int(round(angle_axis))}.png"
    out_path = config.output_dir / out_name
    fig.tight_layout()
    fig.savefig(out_path, dpi=config.dpi)
    plt.close(fig)

    return {
        "cone_id": cone_id,
        "axis_deg": float(angle_axis),
        "transect_a": transect_a,
        "transect_b": transect_b,
        "Wco": wco,
        "Wcr": wcr,
        "H_left": h_left,
        "H_right": h_right,
        "D_left": d_left,
        "D_right": d_right,
        "plot_path": str(out_path),
    }


# pylint: disable=too-many-locals,too-many-statements
def run_cross_sections(
    config: CrossSectionConfig,
    log: Callable[[str], None] | None = None,
) -> pd.DataFrame:
    """Generate cross-section plots and return per-axis metrics."""
    logger = log or (lambda _msg: None)

    config.output_dir.mkdir(parents=True, exist_ok=True)

    finder_df = pd.read_csv(config.finder_path, sep=";")
    finder_df["angle_deg"] = finder_df["orientation"].apply(parse_deg)

    transects_info = (
        finder_df.groupby("transect_id")
        .agg({"angle_deg": "first", "cone_id": "first"})
        .reset_index()
    )

    if config.selected_cone_ids:
        selected_ids = config.selected_cone_ids
    else:
        selected_ids = sorted(transects_info["cone_id"].astype(str).unique())

    metrics: list[dict] = []

    for cone_id in selected_ids:
        cone_id_str = str(cone_id)
        subset = transects_info[transects_info["cone_id"].astype(str) == cone_id_str]
        if subset.empty:
            logger(f"[cone {cone_id_str}] no transects - skipped")
            continue

        transect_angles = subset.set_index("transect_id")["angle_deg"].to_dict()
        visited: set[str] = set()

        logger(f"=== Cone {cone_id_str} ===")

        for transect_id, angle in transect_angles.items():
            if transect_id in visited:
                continue

            candidate, diff = _find_opposite_transect(transect_angles, transect_id, angle % 360.0)
            if candidate is None or diff > config.angle_pair_tolerance_deg:
                continue

            visited.add(transect_id)
            visited.add(candidate)

            axis_mid = angle % 180.0
            logger(
                f"  Axis ~{axis_mid:.1f} deg -> {transect_id} + {candidate}"
            )

            row = _plot_axis_pair(
                cone_id=cone_id_str,
                transect_a=transect_id,
                transect_b=candidate,
                angle_axis=axis_mid,
                finder_df=finder_df,
                config=config,
            )
            if row is not None:
                metrics.append(row)
                logger(f"    Saved: {row['plot_path']}")

    metrics_df = pd.DataFrame(metrics)
    metrics_path = config.output_dir / "cross_section_metrics.csv"
    if config.selected_cone_ids and metrics_path.exists():
        existing_df = pd.read_csv(metrics_path, sep=";")
        selected_ids = {str(item) for item in config.selected_cone_ids}
        if "cone_id" in existing_df.columns:
            existing_df = existing_df[~existing_df["cone_id"].astype(str).isin(selected_ids)]
        metrics_df = pd.concat([existing_df, metrics_df], ignore_index=True)

    if not metrics_df.empty:
        sort_columns = [
            column for column in ["cone_id", "axis_deg"] if column in metrics_df.columns
        ]
        if sort_columns:
            metrics_df = metrics_df.sort_values(
                sort_columns,
                kind="mergesort",
            ).reset_index(drop=True)

    metrics_df.to_csv(metrics_path, index=False, sep=";")
    stats_df = build_metrics_stats_dataframe(metrics_df)
    stats_path = config.output_dir / "cross_section_stats.csv"
    stats_df.to_csv(stats_path, index=False, sep=";")
    logger(f"Metrics saved: {metrics_path}")
    logger(f"Stats saved: {stats_path}")
    logger("Done - cross-sections generated")
    return metrics_df


def build_metrics_stats_dataframe(metrics_df: pd.DataFrame) -> pd.DataFrame:
    """Compute descriptive stats for available cross-section metric columns."""
    present_columns = [column for column in METRIC_COLUMNS if column in metrics_df.columns]
    if not present_columns:
        return pd.DataFrame(
            columns=[
                "metric",
                "count",
                "min",
                "p05",
                "p25",
                "p50 (median)",
                "mean",
                "p75",
                "p95",
                "max",
            ]
        )

    rows = []
    for column in present_columns:
        series = pd.to_numeric(metrics_df[column], errors="coerce").dropna()
        if series.empty:
            continue
        rows.append(
            {
                "metric": column,
                "count": int(series.count()),
                "min": series.min(),
                "p05": series.quantile(0.05),
                "p25": series.quantile(0.25),
                "p50 (median)": series.quantile(0.50),
                "mean": series.mean(),
                "p75": series.quantile(0.75),
                "p95": series.quantile(0.95),
                "max": series.max(),
            }
        )
    return pd.DataFrame(rows)
