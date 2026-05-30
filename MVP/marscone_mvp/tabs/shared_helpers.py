"""Mixin for the SharedHelpersMixin section of MainWindow."""
# pylint: disable=too-many-lines,too-many-instance-attributes,too-many-locals,too-many-statements,too-many-branches,too-many-arguments,too-many-positional-arguments,too-many-nested-blocks,too-many-return-statements,unused-import

from __future__ import annotations

import json
import re
import warnings
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from shapely.geometry import MultiPoint
from rasterio.enums import Resampling
from rasterio.merge import merge as rio_merge
from rasterio.windows import from_bounds as rio_from_bounds
from rasterio.windows import transform as rio_window_transform
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.lines import Line2D
from PySide6.QtCore import QProcess, QProcessEnvironment, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDial,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSizePolicy,
    QSpinBox,
    QSlider,
    QDoubleSpinBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from marscone_mvp.app_state import load_state, save_state
from marscone_mvp.complex_cones import (
    build_complex_outputs,
    complex_output_dir,
    complex_pairs_path,
    ensure_breach_columns,
    ensure_pair_columns,
    get_complex_finder_points,
    load_breach_singles,
    load_complex_pairs,
    parse_member_ids,
    save_breach_singles,
    save_complex_outputs,
    save_complex_pairs,
)
from marscone_mvp.cross_section import (
    attach_distance_to_finder_points,
    parse_deg,
)
from marscone_mvp.crs import describe_resolved_crs
from marscone_mvp.dataset_compare import (
    METRIC_CANDIDATES,
    build_xy_points,
    compute_dataset_embedding,
    compute_scaled_centroid_distance_matrix,
    compute_similarity_report,
    resolve_metrics_csv_path,
)
from marscone_mvp.pipeline import PipelineRunner
from marscone_mvp.table_model import DataFrameTableModel

SUMMARY_COLUMNS = [
    "cone_id",
    "quality_flag",
    "quality_reasons",
    "height",
    "rmse_height",
    "base_major_diameter (WCO)",
    "top_major_diameter (WCR)",
    "top_elev",
    "bottom_elev",
    "shape",
    "H_WCO_ratio",
    "WCR_WCO_ratio",
    "center_lowest_elev",
    "depth",
    "n_transects",
    "rmse_center_to_top_diff",
]

MANUAL_FIX_SLOTS = [
    ("left_far_bottom", "Left far bottom", "green"),
    ("left_near_bottom", "Left near bottom", "yellow"),
    ("left_top", "Left top", "blue"),
    ("center", "Center", "red"),
    ("right_top", "Right top", "blue"),
    ("right_near_bottom", "Right near bottom", "yellow"),
    ("right_far_bottom", "Right far bottom", "green"),
]

_QA_PRESETS: dict[str, dict] = {
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




class SharedHelpersMixin:
    """Mixin — mixed into MainWindow via multiple inheritance."""

    def _browse_button(self, target: QLineEdit, directory: bool) -> QPushButton:
        button = QPushButton("Browse")

        def browse() -> None:
            if directory:
                chosen = QFileDialog.getExistingDirectory(self, "Select directory", target.text())
            else:
                chosen, _ = QFileDialog.getOpenFileName(self, "Select file", target.text())
            if chosen:
                target.setText(chosen)

        button.clicked.connect(browse)
        return button

    def _load_analyzer_metrics_csv(
        self,
        filename: str,
        title: str,
        use_manual_fix: bool = False,
        show_error: bool = True,
    ) -> pd.DataFrame | None:
        base_path = Path(self.base_path_edit.text().strip())
        target_name = f"fix_{filename}" if use_manual_fix else filename
        csv_path = base_path / "output" / "analyzer" / target_name
        if not csv_path.exists():
            if show_error:
                QMessageBox.information(self, title, f"Metrics file not found:\n{csv_path}")
            return None
        return pd.read_csv(csv_path, sep=";")

    def _extract_cone_metric_plot_columns(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame()
        mappings = [
            ("Wco", ["Wco", "base_major_diameter (WCO)"]),
            ("Wcr", ["Wcr", "top_major_diameter (WCR)"]),
            ("H", ["H", "height"]),
            ("D", ["D", "depth"]),
            ("avg_slope_deg", ["avg_slope_deg"]),
            ("H_WCO_ratio", ["H_WCO_ratio"]),
            ("WCR_WCO_ratio", ["WCR_WCO_ratio"]),
            ("volume", ["volume"]),
        ]
        for target_name, candidates in mappings:
            for source_name in candidates:
                if source_name in dataframe.columns:
                    out[target_name] = pd.to_numeric(dataframe[source_name], errors="coerce")
                    break
        return out

    def _safe_numeric_series(
        self,
        dataframe: pd.DataFrame,
        column_name: str,
        fallback_index: pd.Index | None = None,
    ) -> pd.Series:
        if column_name in dataframe.columns:
            return pd.to_numeric(dataframe[column_name], errors="coerce")
        if fallback_index is None:
            fallback_index = dataframe.index
        return pd.Series(np.nan, index=fallback_index, dtype=float)

    def _build_stats_dataframe_from_metrics(self, metrics_df: pd.DataFrame) -> pd.DataFrame:
        if metrics_df.empty:
            return pd.DataFrame()

        rows = []
        for column in metrics_df.columns:
            series = pd.to_numeric(metrics_df[column], errors="coerce").dropna()
            if series.empty:
                continue
            metric_name = column
            if column == "volume":
                series = series / 1_000_000_000.0
                metric_name = "volume (km^3)"
            rows.append(
                {
                    "metric": metric_name,
                    "count": int(series.count()),
                    "min": float(series.min()),
                    "p05": float(series.quantile(0.05)),
                    "p25": float(series.quantile(0.25)),
                    "p50 (median)": float(series.quantile(0.50)),
                    "mean": float(series.mean()),
                    "p75": float(series.quantile(0.75)),
                    "p95": float(series.quantile(0.95)),
                    "max": float(series.max()),
                }
            )
        return pd.DataFrame(rows)

