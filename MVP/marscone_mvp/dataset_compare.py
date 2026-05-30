"""Helpers for multi-dataset metric comparison and embedding workflows."""

from __future__ import annotations

from pathlib import Path
import importlib

import numpy as np
import pandas as pd


METRIC_CANDIDATES: dict[str, list[str]] = {
    "Wco": ["Wco", "base_major_diameter (WCO)"],
    "Wcr": ["Wcr", "top_major_diameter (WCR)"],
    "H": ["H", "height"],
    "D": ["D", "depth"],
    "avg_slope_deg": ["avg_slope_deg"],
    "H_WCO_ratio": ["H_WCO_ratio"],
    "WCR_WCO_ratio": ["WCR_WCO_ratio"],
    "volume": ["volume"],
}


def resolve_metrics_csv_path(raw_path: str, use_manual_fix: bool) -> Path:
    """Resolve either a direct CSV path or a dataset base directory to analyzer metrics CSV."""
    path = Path(raw_path).expanduser()
    if path.suffix.lower() == ".csv":
        return path

    preferred_name = "fix_cone_summary.csv" if use_manual_fix else "cone_summary.csv"
    fallback_name = "cone_summary.csv" if use_manual_fix else "fix_cone_summary.csv"

    preferred_path = path / "output" / "analyzer" / preferred_name
    if preferred_path.exists():
        return preferred_path

    fallback_path = path / "output" / "analyzer" / fallback_name
    if fallback_path.exists():
        return fallback_path

    return preferred_path


def extract_metrics_table(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Extract normalized metric columns from a raw analyzer DataFrame."""
    out = pd.DataFrame(index=dataframe.index)
    for target_name, candidates in METRIC_CANDIDATES.items():
        for source_name in candidates:
            if source_name in dataframe.columns:
                out[target_name] = pd.to_numeric(dataframe[source_name], errors="coerce")
                break
    return out


def build_xy_points(
    dataframe: pd.DataFrame,
    dataset_label: str,
    x_metric: str,
    y_metric: str,
) -> pd.DataFrame:
    """Build a point table for selected X/Y metrics for one dataset."""
    metrics_df = extract_metrics_table(dataframe)
    if x_metric not in metrics_df.columns or y_metric not in metrics_df.columns:
        return pd.DataFrame(columns=["dataset", "cone_id", "x", "y"])

    out = pd.DataFrame(
        {
            "dataset": dataset_label,
            "cone_id": pd.to_numeric(dataframe.get("cone_id"), errors="coerce"),
            "x": pd.to_numeric(metrics_df[x_metric], errors="coerce"),
            "y": pd.to_numeric(metrics_df[y_metric], errors="coerce"),
        }
    )
    return out.dropna(subset=["x", "y"]).reset_index(drop=True)


def compute_centroid_distance_matrix(points_df: pd.DataFrame) -> tuple[list[str], np.ndarray]:
    """Compute pairwise Euclidean distances between dataset centroids."""
    if points_df.empty or "dataset" not in points_df.columns:
        return [], np.empty((0, 0), dtype=float)

    centroids = points_df.groupby("dataset")[["x", "y"]].mean(numeric_only=True)
    if centroids.empty:
        return [], np.empty((0, 0), dtype=float)

    coords = centroids.to_numpy(dtype=float)
    labels = [str(label) for label in centroids.index.tolist()]
    diff = coords[:, None, :] - coords[None, :, :]
    dist = np.sqrt(np.sum(diff * diff, axis=2))
    return labels, dist


def compute_scaled_centroid_distance_matrix(
    points_df: pd.DataFrame,
) -> tuple[list[str], np.ndarray]:
    """Compute centroid distances in z-scored x/y space (unitless)."""
    if points_df.empty or "dataset" not in points_df.columns:
        return [], np.empty((0, 0), dtype=float)

    scaled = points_df.copy()
    for col in ["x", "y"]:
        values = pd.to_numeric(scaled[col], errors="coerce")
        mean = float(values.mean()) if values.notna().any() else 0.0
        std = float(values.std(ddof=0)) if values.notna().any() else 0.0
        denom = std if std > 1e-12 else 1.0
        scaled[col] = (values - mean) / denom

    return compute_centroid_distance_matrix(scaled)


def _iqr(series: pd.Series) -> float:
    q75 = float(series.quantile(0.75))
    q25 = float(series.quantile(0.25))
    return q75 - q25


def build_dataset_feature_matrix(
    frames_by_label: dict[str, pd.DataFrame],
    metrics: list[str] | None = None,
    min_points_per_metric: int = 3,
) -> pd.DataFrame:
    """Build per-dataset feature matrix from metric medians and IQRs."""
    if not frames_by_label:
        return pd.DataFrame()

    if metrics is None:
        metrics = list(METRIC_CANDIDATES.keys())

    by_label_metrics: dict[str, pd.DataFrame] = {
        label: extract_metrics_table(frame) for label, frame in frames_by_label.items()
    }

    usable_metrics: list[str] = []
    for metric in metrics:
        datasets_with_metric = 0
        for mdf in by_label_metrics.values():
            if metric in mdf.columns and mdf[metric].dropna().shape[0] >= min_points_per_metric:
                datasets_with_metric += 1
        if datasets_with_metric >= 2:
            usable_metrics.append(metric)

    if not usable_metrics:
        return pd.DataFrame()

    feature_rows: dict[str, dict[str, float]] = {}
    for label, mdf in by_label_metrics.items():
        row: dict[str, float] = {}
        for metric in usable_metrics:
            if metric not in mdf.columns:
                row[f"{metric}__median"] = np.nan
                row[f"{metric}__iqr"] = np.nan
                continue

            series = pd.to_numeric(mdf[metric], errors="coerce").dropna()
            if len(series) < min_points_per_metric:
                row[f"{metric}__median"] = np.nan
                row[f"{metric}__iqr"] = np.nan
                continue

            row[f"{metric}__median"] = float(series.median())
            row[f"{metric}__iqr"] = float(_iqr(series))

        feature_rows[label] = row

    feature_df = pd.DataFrame.from_dict(feature_rows, orient="index")
    return feature_df


# pylint: disable=too-many-locals,too-many-branches
def build_cone_feature_matrix(
    frames_by_label: dict[str, pd.DataFrame],
    metrics: list[str] | None = None,
    min_datasets_per_metric: int = 2,
    min_features_per_cone: int = 2,
) -> pd.DataFrame:
    """Build per-cone feature matrix across datasets."""
    if not frames_by_label:
        return pd.DataFrame()

    if metrics is None:
        metrics = list(METRIC_CANDIDATES.keys())

    by_label_metrics: dict[str, pd.DataFrame] = {
        label: extract_metrics_table(frame) for label, frame in frames_by_label.items()
    }

    usable_metrics: list[str] = []
    for metric in metrics:
        datasets_with_metric = 0
        for mdf in by_label_metrics.values():
            if metric in mdf.columns and mdf[metric].notna().any():
                datasets_with_metric += 1
        if datasets_with_metric >= min_datasets_per_metric:
            usable_metrics.append(metric)

    if not usable_metrics:
        return pd.DataFrame()

    blocks: list[pd.DataFrame] = []
    for label, frame in frames_by_label.items():
        mdf = by_label_metrics[label].copy()
        if mdf.empty:
            continue

        feature_block = pd.DataFrame(index=mdf.index)
        feature_block["dataset"] = label
        feature_block["cone_id"] = pd.to_numeric(frame.get("cone_id"), errors="coerce")
        for metric in usable_metrics:
            if metric in mdf.columns:
                feature_block[metric] = pd.to_numeric(mdf[metric], errors="coerce")
            else:
                feature_block[metric] = np.nan

        valid_counts = feature_block[usable_metrics].notna().sum(axis=1)
        feature_block = feature_block.loc[valid_counts >= min_features_per_cone].copy()
        if feature_block.empty:
            continue

        missing_cone_ids = feature_block["cone_id"].isna()
        if missing_cone_ids.any():
            fallback_ids = pd.Series(
                np.arange(1, int(missing_cone_ids.sum()) + 1, dtype=int),
                index=feature_block.index[missing_cone_ids],
                dtype=float,
            )
            feature_block.loc[missing_cone_ids, "cone_id"] = fallback_ids

        feature_block.index = [
            f"{label}::cone_{str(cone_id).replace('.0', '')}"
            for cone_id in feature_block["cone_id"].tolist()
        ]
        blocks.append(feature_block)

    if not blocks:
        return pd.DataFrame()

    return pd.concat(blocks, axis=0)


def _zscore_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    zdf = dataframe.copy()
    for col in zdf.columns:
        col_values = pd.to_numeric(zdf[col], errors="coerce")
        mean = float(col_values.mean()) if col_values.notna().any() else 0.0
        std = float(col_values.std(ddof=0)) if col_values.notna().any() else 0.0
        denom = std if std > 1e-12 else 1.0
        zdf[col] = (col_values - mean) / denom
    return zdf


def compute_similarity_report(
    frames_by_label: dict[str, pd.DataFrame],
    metrics: list[str] | None = None,
    min_points_per_metric: int = 3,
) -> pd.DataFrame:  # pylint: disable=too-many-locals
    """Return pairwise dataset similarity ranked by multi-metric standardized distance."""
    feature_df = build_dataset_feature_matrix(
        frames_by_label,
        metrics=metrics,
        min_points_per_metric=min_points_per_metric,
    )
    if feature_df.empty:
        return pd.DataFrame()

    # Z-score feature normalization across datasets to remove unit effects.
    zdf = _zscore_dataframe(feature_df)
    usable_metrics = sorted(
        {
            col.replace("__median", "")
            for col in zdf.columns
            if str(col).endswith("__median")
        }
    )

    labels = list(zdf.index)
    rows: list[dict[str, object]] = []
    for i, a in enumerate(labels):
        for b in labels[i + 1 :]:
            diff = zdf.loc[a] - zdf.loc[b]
            valid = diff.notna()
            if valid.sum() < 2:
                continue

            d = float(np.sqrt(np.sum(np.square(diff[valid].to_numpy(dtype=float)))))
            similarity = float(np.exp(-d))

            metric_gaps: list[tuple[float, str]] = []
            for metric in usable_metrics:
                med_col = f"{metric}__median"
                if med_col in zdf.columns and pd.notna(diff.get(med_col, np.nan)):
                    metric_gaps.append((abs(float(diff[med_col])), metric))
            metric_gaps.sort(reverse=True)
            top_metrics = ", ".join(name for _, name in metric_gaps[:3])

            rows.append(
                {
                    "dataset_a": a,
                    "dataset_b": b,
                    "n_shared_features": int(valid.sum()),
                    "distance_z": d,
                    "similarity_0_1": similarity,
                    "top_diff_metrics": top_metrics,
                }
            )

    if not rows:
        return pd.DataFrame()

    report = pd.DataFrame(rows).sort_values(
        ["distance_z", "dataset_a", "dataset_b"], ascending=[True, True, True]
    )
    report.insert(0, "rank", np.arange(1, len(report) + 1))
    return report.reset_index(drop=True)


# pylint: disable=too-many-locals,too-many-branches,too-many-statements
def compute_dataset_embedding(
    frames_by_label: dict[str, pd.DataFrame],
    method: str = "PCA",
    level: str = "dataset",
    metrics: list[str] | None = None,
    min_points_per_metric: int = 3,
) -> pd.DataFrame:
    """Compute 2D embedding of datasets from multi-metric feature vectors.

    Returns columns appropriate for requested level plus emb_x, emb_y.
    """
    level_key = str(level).strip().lower()
    if level_key == "cone":
        feature_source = build_cone_feature_matrix(
            frames_by_label,
            metrics=metrics,
            min_datasets_per_metric=2,
            min_features_per_cone=2,
        )
        if feature_source.empty:
            return pd.DataFrame()

        row_meta = feature_source[["dataset", "cone_id"]].copy()
        row_meta["entity_label"] = feature_source.index.astype(str)
        feature_df = feature_source.drop(columns=["dataset", "cone_id"], errors="ignore")
    else:
        feature_df = build_dataset_feature_matrix(
            frames_by_label,
            metrics=metrics,
            min_points_per_metric=min_points_per_metric,
        )
        row_meta = pd.DataFrame(
            {
                "dataset": [str(idx) for idx in feature_df.index.tolist()],
                "entity_label": [str(idx) for idx in feature_df.index.tolist()],
            },
            index=feature_df.index,
        )

    if feature_df.empty or len(feature_df.index) < 2:
        return pd.DataFrame()

    zdf = _zscore_dataframe(feature_df)
    # Fill any residual NaNs with 0 after z-scoring.
    matrix = zdf.fillna(0.0).to_numpy(dtype=float)
    if matrix.shape[1] == 0:
        return pd.DataFrame()

    method_upper = str(method).upper().strip()
    coords = None
    metadata: dict[str, object] = {
        "requested_method": method_upper,
        "method_used": method_upper,
        "level": level_key,
        "feature_columns": list(zdf.columns),
    }

    if method_upper == "UMAP":
        try:
            umap_module = importlib.import_module("umap")

            n_samples = matrix.shape[0]
            n_neighbors = max(2, min(10, n_samples - 1))
            reducer = umap_module.UMAP(
                n_components=2,
                n_neighbors=n_neighbors,
                min_dist=0.2,
                metric="euclidean",
                random_state=42,
            )
            coords = reducer.fit_transform(matrix)
        except (ImportError, AttributeError, TypeError, ValueError):
            coords = None

    if coords is None:
        # PCA fallback (always available via numpy SVD)
        metadata["method_used"] = "PCA"
        centered = matrix - np.mean(matrix, axis=0, keepdims=True)
        _, singular_values, vt = np.linalg.svd(centered, full_matrices=False)
        if singular_values.size:
            denom = max(centered.shape[0] - 1, 1)
            explained = np.square(singular_values) / denom
            explained_sum = float(np.sum(explained))
            if explained_sum > 0.0:
                explained_ratio = explained / explained_sum
                metadata["explained_variance_ratio"] = explained_ratio[:2].tolist()

        if vt.shape[0] >= 1:
            pc1_order = np.argsort(np.abs(vt[0]))[::-1]
            metadata["top_loadings_pc1"] = [
                str(zdf.columns[idx]) for idx in pc1_order[: min(5, len(pc1_order))]
            ]
        if vt.shape[0] >= 2:
            pc2_order = np.argsort(np.abs(vt[1]))[::-1]
            metadata["top_loadings_pc2"] = [
                str(zdf.columns[idx]) for idx in pc2_order[: min(5, len(pc2_order))]
            ]

        if vt.shape[0] < 2:
            comp1 = centered[:, 0] if centered.shape[1] else np.zeros(centered.shape[0])
            comp2 = np.zeros(centered.shape[0])
            coords = np.column_stack([comp1, comp2])
        else:
            components = vt[:2, :].T
            coords = centered @ components

        loadings_rows: list[dict[str, object]] = []
        component_count = min(2, vt.shape[0])
        for component_idx in range(component_count):
            order = np.argsort(np.abs(vt[component_idx]))[::-1]
            for rank, feature_idx in enumerate(order[: min(8, len(order))], start=1):
                loadings_rows.append(
                    {
                        "component": f"PC{component_idx + 1}",
                        "rank": rank,
                        "feature": str(zdf.columns[feature_idx]),
                        "loading": float(vt[component_idx, feature_idx]),
                        "abs_loading": float(abs(vt[component_idx, feature_idx])),
                    }
                )
        metadata["loadings_table"] = pd.DataFrame(loadings_rows)

    embedding_df = row_meta.reset_index(drop=True).copy()
    embedding_df["emb_x"] = coords[:, 0]
    embedding_df["emb_y"] = coords[:, 1]
    embedding_df.attrs["metadata"] = metadata
    return embedding_df
