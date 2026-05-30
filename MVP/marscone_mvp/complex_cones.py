"""Helpers for reading, normalizing, and deriving complex-cone outputs."""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.errors import EmptyDataError
from skimage import measure as sk_measure
from shapely.geometry import MultiPoint


PAIR_COLUMNS = ["complex_id", "member_ids", "topology_type", "notes", "active"]
BREACH_COLUMNS = ["cone_id", "topology_type", "reason", "active"]
DERIVED_FILE_NAMES = {
    "pairs": "complex_pairs.csv",
    "breached_singles": "breached_singles.csv",
    "summary": "complex_summary.csv",
    "members": "complex_members.csv",
    "topology": "cone_topology.csv",
    "topology_stats": "topology_stats.csv",
}


def normalize_cone_id(value) -> str:
    """Normalize a cone identifier to the compact string form used in outputs."""

    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def parse_member_ids(value: str) -> list[str]:
    """Parse a comma-separated complex member list into unique normalized ids."""

    if not value:
        return []
    seen: set[str] = set()
    members: list[str] = []
    for chunk in str(value).split(","):
        cone_id = normalize_cone_id(chunk)
        if not cone_id or cone_id in seen:
            continue
        seen.add(cone_id)
        members.append(cone_id)
    return members


def complex_output_dir(base_path: Path) -> Path:
    """Return the directory that stores derived complex-cone CSV outputs."""

    return base_path / "output" / "mvp_complex"


def complex_pairs_path(base_path: Path) -> Path:
    """Return the CSV path for saved complex-pair definitions."""

    return complex_output_dir(base_path) / DERIVED_FILE_NAMES["pairs"]


def breach_singles_path(base_path: Path) -> Path:
    """Return the CSV path for saved breached-single definitions."""

    return complex_output_dir(base_path) / DERIVED_FILE_NAMES["breached_singles"]


def ensure_pair_columns(dataframe: pd.DataFrame | None) -> pd.DataFrame:
    """Coerce a complex-pairs table to the expected schema and value formats."""

    if dataframe is None or dataframe.empty:
        return pd.DataFrame(columns=PAIR_COLUMNS)

    out = dataframe.copy()
    for column in PAIR_COLUMNS:
        if column not in out.columns:
            out[column] = "" if column != "active" else True

    out["complex_id"] = out["complex_id"].astype(str).str.strip()
    out["member_ids"] = out["member_ids"].astype(str).apply(
        lambda value: ", ".join(parse_member_ids(value))
    )
    out["topology_type"] = out["topology_type"].astype(str).str.strip().str.lower()
    out["notes"] = out["notes"].astype(str).replace({"nan": ""})
    out["active"] = out["active"].apply(_to_bool)

    valid_types = {"simple", "breached", "complex"}
    out.loc[~out["topology_type"].isin(valid_types), "topology_type"] = "complex"
    out = out[PAIR_COLUMNS]
    out = out[out["complex_id"] != ""].reset_index(drop=True)
    return out


def ensure_breach_columns(dataframe: pd.DataFrame | None) -> pd.DataFrame:
    """Coerce a breached-singles table to the expected schema and value formats."""

    if dataframe is None or dataframe.empty:
        return pd.DataFrame(columns=BREACH_COLUMNS)

    out = dataframe.copy()
    for column in BREACH_COLUMNS:
        if column not in out.columns:
            out[column] = "" if column != "active" else True

    out["cone_id"] = out["cone_id"].astype(str).apply(normalize_cone_id)
    out["topology_type"] = out["topology_type"].astype(str).str.strip().str.lower()
    out["reason"] = out["reason"].astype(str).replace({"nan": ""})
    out["active"] = out["active"].apply(_to_bool)

    valid_types = {"simple", "breached", "heavily_eroded", "collapsed"}
    out.loc[~out["topology_type"].isin(valid_types), "topology_type"] = "breached"
    out = out[BREACH_COLUMNS]
    out = out[out["cone_id"] != ""].reset_index(drop=True)
    return out


def load_complex_pairs(base_path: Path) -> pd.DataFrame:
    """Load saved complex-pair definitions or return an empty normalized table."""

    path = complex_pairs_path(base_path)
    if not path.exists():
        return ensure_pair_columns(None)
    try:
        return ensure_pair_columns(pd.read_csv(path, sep=";"))
    except EmptyDataError:
        return ensure_pair_columns(None)


def load_breach_singles(base_path: Path) -> pd.DataFrame:
    """Load saved breached-single definitions or return an empty normalized table."""

    path = breach_singles_path(base_path)
    if not path.exists():
        return ensure_breach_columns(None)
    try:
        return ensure_breach_columns(pd.read_csv(path, sep=";"))
    except EmptyDataError:
        return ensure_breach_columns(None)


def save_complex_pairs(base_path: Path, pairs_df: pd.DataFrame) -> Path:
    """Persist normalized complex-pair definitions and return the written path."""

    output_dir = complex_output_dir(base_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = complex_pairs_path(base_path)
    ensure_pair_columns(pairs_df).to_csv(path, sep=";", index=False)
    return path


def save_breach_singles(base_path: Path, breach_df: pd.DataFrame) -> Path:
    """Persist normalized breached-single definitions and return the written path."""

    output_dir = complex_output_dir(base_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = breach_singles_path(base_path)
    ensure_breach_columns(breach_df).to_csv(path, sep=";", index=False)
    return path


def build_complex_outputs(
    base_path: Path,
    pairs_df: pd.DataFrame,
    breach_df: pd.DataFrame | None = None,
    use_manual_fix: bool = False,
) -> dict[str, pd.DataFrame]:
    """Build all derived complex-cone outputs from pair and breach definitions."""

    cone_summary = _prepare_cone_summary(
        _load_cone_summary(base_path, use_manual_fix=use_manual_fix)
    )
    finder_points = _prepare_finder_points(
        _load_finder_points(base_path, use_manual_fix=use_manual_fix)
    )
    breaches = ensure_breach_columns(breach_df)
    active_pairs = ensure_pair_columns(pairs_df)
    active_pairs = active_pairs[active_pairs["active"]].copy().reset_index(drop=True)
    member_rows, complex_summary_rows = _collect_complex_rows(
        base_path=base_path,
        cone_summary=cone_summary,
        finder_points=finder_points,
        active_pairs=active_pairs,
        use_manual_fix=use_manual_fix,
    )

    topology_df = _build_topology_dataframe(cone_summary, active_pairs)
    topology_df = _apply_breach_singles_to_topology(topology_df, breaches)

    return {
        "pairs": active_pairs,
        "breached_singles": _active_breaches_only(breaches),
        "summary": pd.DataFrame(complex_summary_rows),
        "members": (
            pd.concat(member_rows, ignore_index=True)
            if member_rows
            else pd.DataFrame()
        ),
        "topology": topology_df,
        "topology_stats": _build_topology_stats(topology_df, cone_summary),
    }


def save_complex_outputs(base_path: Path, outputs: dict[str, pd.DataFrame]) -> dict[str, Path]:
    """Persist all derived complex-cone output tables and return their paths."""

    output_dir = complex_output_dir(base_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: dict[str, Path] = {}
    for key, file_name in DERIVED_FILE_NAMES.items():
        dataframe = outputs.get(key)
        if dataframe is None:
            continue
        path = output_dir / file_name
        dataframe.to_csv(path, sep=";", index=False)
        saved_paths[key] = path
    return saved_paths


def _collect_complex_rows(
    base_path: Path,
    cone_summary: pd.DataFrame,
    finder_points: pd.DataFrame,
    active_pairs: pd.DataFrame,
    use_manual_fix: bool,
) -> tuple[list[pd.DataFrame], list[dict]]:
    """Collect per-complex member rows and derived summary rows."""

    member_rows: list[pd.DataFrame] = []
    complex_summary_rows: list[dict] = []
    for _, pair in active_pairs.iterrows():
        members = parse_member_ids(pair["member_ids"])
        if not members:
            continue

        member_df = _resolve_member_rows(
            base_path=base_path,
            cone_summary=cone_summary,
            pair=pair,
            members=members,
            use_manual_fix=use_manual_fix,
        )
        annotated_rows = _annotate_member_rows(member_df, pair, members)
        if not annotated_rows.empty:
            member_rows.append(annotated_rows)

        complex_summary_rows.append(
            _build_complex_summary_row(pair, members, member_df, finder_points)
        )
    return member_rows, complex_summary_rows


def get_complex_finder_points(
    base_path: Path, member_ids: list[str], use_manual_fix: bool = False
) -> dict[str, pd.DataFrame]:
    """
    Load finder points for each member of a complex cone group.
    Returns dict with string indices as keys ('0', '1', '2', ...)
    containing finder points DataFrames.
    """
    finder_points = _load_finder_points(base_path, use_manual_fix=use_manual_fix)
    if not member_ids:
        return {}

    finder_points = finder_points.copy()
    finder_points["cone_id_norm"] = finder_points["cone_id"].apply(normalize_cone_id)

    result = {}
    for idx, member_id in enumerate(member_ids):
        member_norm = normalize_cone_id(member_id)
        member_points = finder_points[finder_points["cone_id_norm"] == member_norm].copy()
        result[str(idx)] = member_points

    return result


def _load_cone_summary(base_path: Path, use_manual_fix: bool) -> pd.DataFrame:
    """Load the analyzer summary table for either base or manual-fix output."""

    file_name = "fix_cone_summary.csv" if use_manual_fix else "cone_summary.csv"
    path = base_path / "output" / "analyzer" / file_name
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, sep=";")


def _load_finder_points(base_path: Path, use_manual_fix: bool) -> pd.DataFrame:
    """Load finder points and optionally apply manual cross-section overrides."""

    path = base_path / "output" / "finder" / "finder_method.csv"
    if not path.exists():
        return pd.DataFrame()

    points = pd.read_csv(path, sep=";")
    if not use_manual_fix:
        return points

    overrides_path = (
        base_path / "output" / "figures" / "cross_sections" / "manual_point_overrides.csv"
    )
    if not overrides_path.exists():
        return points

    overrides = pd.read_csv(overrides_path, sep=";")
    if overrides.empty:
        return points

    required_columns = {"cone_id", "transect_id", "type", "x_geo", "y_geo", "elevation"}
    if not required_columns.issubset(set(overrides.columns)):
        return points

    working = points.copy()
    working["cone_id_norm"] = working["cone_id"].apply(normalize_cone_id)
    working["transect_id_norm"] = working["transect_id"].astype(str)
    working["type_norm"] = working["type"].astype(str)

    overrides = overrides.copy()
    overrides["cone_id_norm"] = overrides["cone_id"].apply(normalize_cone_id)
    overrides["transect_id_norm"] = overrides["transect_id"].astype(str)
    overrides["type_norm"] = overrides["type"].astype(str)

    if "updated_at_utc" in overrides.columns:
        overrides = overrides.sort_values("updated_at_utc", kind="mergesort")

    overrides_latest = overrides.drop_duplicates(
        subset=["cone_id_norm", "transect_id_norm", "type_norm"],
        keep="last",
    )

    for _, row in overrides_latest.iterrows():
        mask = (
            (working["cone_id_norm"] == row["cone_id_norm"])
            & (working["transect_id_norm"] == row["transect_id_norm"])
            & (working["type_norm"] == row["type_norm"])
        )
        if not mask.any():
            continue
        working.loc[mask, "x_geo"] = float(row["x_geo"])
        working.loc[mask, "y_geo"] = float(row["y_geo"])
        working.loc[mask, "elevation"] = float(row["elevation"])

    return working.drop(columns=["cone_id_norm", "transect_id_norm", "type_norm"])


def _prepare_cone_summary(cone_summary: pd.DataFrame) -> pd.DataFrame:
    """Attach normalized cone identifiers used by downstream joins."""

    if cone_summary.empty:
        return cone_summary
    out = cone_summary.copy()
    out["cone_id_norm"] = out["cone_id"].apply(normalize_cone_id)
    return out


def _prepare_finder_points(finder_points: pd.DataFrame) -> pd.DataFrame:
    """Attach normalized cone and point-type columns used by derived metrics."""

    if finder_points.empty:
        return finder_points
    out = finder_points.copy()
    out["cone_id_norm"] = out["cone_id"].apply(normalize_cone_id)
    out["type_norm"] = out["type"].astype(str)
    return out


def _resolve_member_rows(
    base_path: Path,
    cone_summary: pd.DataFrame,
    pair: pd.Series,
    members: list[str],
    use_manual_fix: bool,
) -> pd.DataFrame:
    """Resolve summary rows for complex members, including fallback summary lookup."""

    member_df = cone_summary[cone_summary["cone_id_norm"].isin(members)].copy()
    found_members = set(member_df["cone_id_norm"].tolist()) if not member_df.empty else set()
    missing_members = [member_id for member_id in members if member_id not in found_members]
    if not missing_members:
        return member_df

    _warn_on_missing_members(pair, missing_members, use_manual_fix)
    alt_summary = _prepare_cone_summary(
        _load_cone_summary(base_path, use_manual_fix=not use_manual_fix)
    )
    if alt_summary.empty:
        return member_df

    fallback_rows = alt_summary[alt_summary["cone_id_norm"].isin(missing_members)]
    if fallback_rows.empty:
        return member_df
    return pd.concat([member_df, fallback_rows], ignore_index=True)


def _warn_on_missing_members(
    pair: pd.Series,
    missing_members: list[str],
    use_manual_fix: bool,
) -> None:
    """Warn when complex members are only available in the alternate summary file."""

    alt_label = "cone_summary.csv" if use_manual_fix else "fix_cone_summary.csv"
    warnings.warn(
        f"Complex {pair['complex_id']}: cones {missing_members} not found in current summary. "
        f"Falling back to {alt_label}. Re-run analyzer to fix this.",
        UserWarning,
        stacklevel=3,
    )


def _annotate_member_rows(
    member_df: pd.DataFrame,
    pair: pd.Series,
    members: list[str],
) -> pd.DataFrame:
    """Attach complex metadata to member summary rows."""

    if member_df.empty:
        return member_df

    out = member_df.copy()
    out["complex_id"] = pair["complex_id"]
    out["topology_type"] = pair["topology_type"]
    out["member_ids"] = ", ".join(members)
    out["notes"] = pair["notes"]
    return out


def _active_breaches_only(breaches: pd.DataFrame) -> pd.DataFrame:
    """Return only active breached-single rows with a stable empty fallback."""

    if breaches.empty:
        return pd.DataFrame(columns=BREACH_COLUMNS)
    return breaches[breaches["active"]].copy()


def _build_complex_summary_row(
    pair_row: pd.Series,
    members: list[str],
    member_df: pd.DataFrame,
    finder_points: pd.DataFrame,
) -> dict:
    """Build one derived summary row for a complex-cone grouping."""

    bottom_points = pd.DataFrame()
    if not finder_points.empty:
        bottom_points = finder_points[
            finder_points["cone_id_norm"].isin(members)
            & finder_points["type_norm"].str.contains("bottom", na=False)
        ].copy()

    geom_metrics = _compute_shared_base_geometry(bottom_points)
    crater_spacing = _compute_crater_spacing(member_df)

    shared_top = _safe_numeric_stat(member_df.get("top_elev"), "max")
    shared_bottom = _safe_numeric_stat(bottom_points.get("elevation"), "mean")
    if shared_bottom is None:
        shared_bottom = _safe_numeric_stat(member_df.get("bottom_elev"), "mean")

    shared_height = None
    if shared_top is not None and shared_bottom is not None:
        shared_height = shared_top - shared_bottom

    # Extract depth values from member dataframe (e.g., for max and mean calculations)
    member_depths = member_df["depth"] if "depth" in member_df.columns else pd.Series()

    return {
        "complex_id": pair_row["complex_id"],
        "topology_type": pair_row["topology_type"],
        "member_ids": ", ".join(members),
        "member_count": len(members),
        "shared_Wco": geom_metrics["major_diameter"],
        "shared_minor_diameter": geom_metrics["minor_diameter"],
        "shared_base_area": geom_metrics["area"],
        "shared_center_x": geom_metrics["center_x"],
        "shared_center_y": geom_metrics["center_y"],
        "shared_top_elev": shared_top,
        "shared_bottom_elev": shared_bottom,
        "shared_height": shared_height,
        "max_member_depth": _safe_numeric_stat(member_depths, "max"),
        "mean_member_depth": _safe_numeric_stat(member_depths, "mean"),
        "crater_spacing": crater_spacing,
        "notes": pair_row["notes"],
    }


def _compute_shared_base_geometry(bottom_points: pd.DataFrame) -> dict[str, float | None]:
    """Estimate shared base geometry for a cone group from bottom-point clouds."""

    unique_coords = _extract_unique_coords(bottom_points)
    if len(unique_coords) == 0:
        return _empty_geometry()

    shape = MultiPoint(unique_coords).convex_hull
    if shape.is_empty:
        return _empty_geometry()

    centroid = shape.centroid
    hull_area = float(shape.area) if not shape.is_empty else None
    center_x = float(centroid.x)
    center_y = float(centroid.y)

    # Prefer ellipse fit to keep metrics comparable with Analyzer outputs.
    ellipse_geometry = _estimate_ellipse_geometry(unique_coords)
    if ellipse_geometry is not None:
        ellipse_geometry["center_x"] = ellipse_geometry.pop("xc")
        ellipse_geometry["center_y"] = ellipse_geometry.pop("yc")
        return ellipse_geometry

    fallback_geometry = _estimate_fallback_geometry(
        unique_coords=unique_coords,
        shape=shape,
        hull_area=hull_area,
        center_x=center_x,
        center_y=center_y,
    )
    return fallback_geometry


def _empty_geometry() -> dict[str, float | None]:
    """Return an empty geometry metrics payload."""

    return {
        "major_diameter": None,
        "minor_diameter": None,
        "area": None,
        "center_x": None,
        "center_y": None,
    }


def _extract_unique_coords(bottom_points: pd.DataFrame) -> np.ndarray:
    """Extract unique finite xy coordinates from a bottom-points table."""

    if bottom_points is None or bottom_points.empty:
        return np.empty((0, 2), dtype=float)

    coords_df = bottom_points[["x_geo", "y_geo"]].apply(pd.to_numeric, errors="coerce").dropna()
    coords = coords_df.to_numpy(dtype=float)
    if len(coords) > 0:
        coords = coords[np.isfinite(coords).all(axis=1)]
    if len(coords) == 0:
        return np.empty((0, 2), dtype=float)
    return np.unique(coords, axis=0)


def _estimate_ellipse_geometry(unique_coords: np.ndarray) -> dict[str, float] | None:
    """Fit an ellipse to bottom points when enough unique coordinates are available."""

    if len(unique_coords) < 5:
        return None

    ellipse_model = sk_measure.EllipseModel()
    success = ellipse_model.estimate(unique_coords)
    if not success or ellipse_model.params is None:
        return None

    xc, yc, a_axis, b_axis, _theta = ellipse_model.params
    if not np.isfinite([xc, yc, a_axis, b_axis]).all() or a_axis <= 0 or b_axis <= 0:
        return None

    return {
        "major_diameter": float(2.0 * a_axis),
        "minor_diameter": float(2.0 * b_axis),
        "area": float(np.pi * a_axis * b_axis),
        "xc": float(xc),
        "yc": float(yc),
    }


def _estimate_fallback_geometry(
    unique_coords: np.ndarray,
    shape,
    hull_area: float | None,
    center_x: float,
    center_y: float,
) -> dict[str, float | None]:
    """Estimate geometry from distances and the rotated hull rectangle."""

    if len(unique_coords) == 1:
        return {
            "major_diameter": 0.0,
            "minor_diameter": 0.0,
            "area": 0.0,
            "center_x": center_x,
            "center_y": center_y,
        }

    major_diameter = _pairwise_major_diameter(unique_coords)
    minor_diameter = 0.0
    area = hull_area
    rectangle_axes = _rotated_rectangle_axes(shape)
    if rectangle_axes is not None:
        major_diameter, minor_diameter = rectangle_axes

    return {
        "major_diameter": major_diameter,
        "minor_diameter": minor_diameter,
        "area": area,
        "center_x": center_x,
        "center_y": center_y,
    }


def _pairwise_major_diameter(unique_coords: np.ndarray) -> float:
    """Return the maximum pairwise xy distance for a coordinate set."""

    deltas = unique_coords[:, np.newaxis, :] - unique_coords[np.newaxis, :, :]
    distances = np.hypot(deltas[:, :, 0], deltas[:, :, 1])
    return float(np.max(distances)) if distances.size else 0.0


def _rotated_rectangle_axes(shape) -> tuple[float, float] | None:
    """Estimate major and minor axes from the minimum rotated rectangle."""

    if shape.geom_type != "Polygon" or shape.area <= 0:
        return None

    rect = None
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "error",
            message="invalid value encountered in oriented_envelope",
            category=RuntimeWarning,
        )
        try:
            rect = shape.minimum_rotated_rectangle
        except RuntimeWarning:
            rect = None

    if rect is None or not hasattr(rect, "exterior"):
        return None

    rect_coords = np.asarray(rect.exterior.coords[:-1], dtype=float)
    if len(rect_coords) < 2 or not np.isfinite(rect_coords).all():
        return None

    edge_lengths = []
    for idx, start in enumerate(rect_coords):
        end = rect_coords[(idx + 1) % len(rect_coords)]
        edge_lengths.append(float(np.hypot(*(end - start))))
    edge_lengths = [value for value in edge_lengths if np.isfinite(value)]
    if not edge_lengths:
        return None

    ordered = sorted(edge_lengths, reverse=True)
    return ordered[0], ordered[1] if len(ordered) > 1 else 0.0

def _compute_crater_spacing(member_df: pd.DataFrame) -> float | None:
    """Compute the maximum spacing between crater centers in a member group."""

    if member_df is None or member_df.empty:
        return None

    center_x = pd.to_numeric(member_df.get("hybrid_x"), errors="coerce")
    center_y = pd.to_numeric(member_df.get("hybrid_y"), errors="coerce")
    fallback_x = pd.to_numeric(member_df.get("center_x"), errors="coerce")
    fallback_y = pd.to_numeric(member_df.get("center_y"), errors="coerce")
    x_vals = center_x.fillna(fallback_x)
    y_vals = center_y.fillna(fallback_y)

    coords = np.column_stack([x_vals.to_numpy(dtype=float), y_vals.to_numpy(dtype=float)])
    coords = coords[~np.isnan(coords).any(axis=1)]
    if len(coords) < 2:
        return 0.0 if len(coords) == 1 else None

    max_dist = 0.0
    for idx, coord in enumerate(coords[:-1]):
        deltas = coords[idx + 1 :] - coord
        if len(deltas) == 0:
            continue
        distances = np.hypot(deltas[:, 0], deltas[:, 1])
        if len(distances) > 0:
            max_dist = max(max_dist, float(np.max(distances)))
    return max_dist


def _build_topology_dataframe(
    cone_summary: pd.DataFrame,
    active_pairs: pd.DataFrame,
) -> pd.DataFrame:
    """Build a per-cone topology table from active complex-pair definitions."""

    if cone_summary.empty or "cone_id_norm" not in cone_summary.columns:
        return pd.DataFrame(
            columns=["cone_id", "complex_id", "topology_type", "member_ids"]
        )

    topology = pd.DataFrame(
        {
            "cone_id": cone_summary["cone_id_norm"].dropna().astype(str).unique(),
        }
    ).sort_values("cone_id", kind="mergesort").reset_index(drop=True)
    topology["complex_id"] = ""
    topology["topology_type"] = "simple"
    topology["member_ids"] = ""

    for _, pair in active_pairs.iterrows():
        members = parse_member_ids(pair["member_ids"])
        if not members:
            continue
        mask = topology["cone_id"].isin(members)
        topology.loc[mask, "complex_id"] = str(pair["complex_id"])
        topology.loc[mask, "topology_type"] = str(pair["topology_type"])
        topology.loc[mask, "member_ids"] = ", ".join(members)

    return topology


def _apply_breach_singles_to_topology(
    topology_df: pd.DataFrame,
    breach_df: pd.DataFrame,
) -> pd.DataFrame:
    """Override topology assignments for individually breached cones."""

    if topology_df.empty or breach_df.empty:
        return topology_df
    out = topology_df.copy()
    active_breaches = breach_df[breach_df["active"]].copy()
    if active_breaches.empty:
        return out
    for _, breach_row in active_breaches.iterrows():
        cone_id = str(breach_row["cone_id"])
        mask = out["cone_id"] == cone_id
        if mask.any():
            out.loc[mask, "topology_type"] = str(breach_row["topology_type"])
            out.loc[mask, "complex_id"] = ""
            out.loc[mask, "member_ids"] = ""
    return out


def _build_topology_stats(topology_df: pd.DataFrame, cone_summary: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-topology summary metrics from the merged cone table."""

    if topology_df.empty or cone_summary.empty:
        return pd.DataFrame()

    metrics = cone_summary.copy()
    metrics["cone_id"] = metrics["cone_id_norm"]
    merged = topology_df.merge(metrics, on="cone_id", how="left")

    rows = []
    for topology_type, group in merged.groupby("topology_type", sort=True):
        rows.append(
            {
                "topology_type": topology_type,
                "count": int(group["cone_id"].nunique()),
                "mean_H": _safe_numeric_stat(group.get("height"), "mean"),
                "mean_Wco": _safe_numeric_stat(
                    group.get("base_major_diameter (WCO)"), "mean"
                ),
                "mean_Wcr": _safe_numeric_stat(
                    group.get("top_major_diameter (WCR)"), "mean"
                ),
                "mean_D": _safe_numeric_stat(group.get("depth"), "mean"),
                "max_D": _safe_numeric_stat(group.get("depth"), "max"),
            }
        )
    return pd.DataFrame(rows)


def _safe_numeric_stat(series, stat: str) -> float | None:
    """Safely compute a numeric summary statistic from a possibly dirty series."""

    if series is None:
        return None
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return None
    if stat == "max":
        return float(numeric.max())
    if stat == "min":
        return float(numeric.min())
    return float(numeric.mean())


def _to_bool(value) -> bool:
    """Interpret common CSV truthy and falsy values as a boolean."""

    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text not in {"", "0", "false", "no", "n", "none"}
