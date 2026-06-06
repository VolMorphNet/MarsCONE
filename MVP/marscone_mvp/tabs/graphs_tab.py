"""Mixin for the GraphsMixin section of MainWindow."""
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

try:
    from scipy.stats import pearsonr as SCIPY_PEARSONR, spearmanr as SCIPY_SPEARMANR
except Exception:  # pylint: disable=broad-exception-caught
    SCIPY_PEARSONR = None
    SCIPY_SPEARMANR = None

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





# pylint: disable=too-few-public-methods
class GraphsMixin:
    """Mixin — mixed into MainWindow via multiple inheritance."""

    def _build_graphs_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        graphs_tabs = QTabWidget(page)
        graphs_tabs.addTab(self._build_graphs_cone_trends_tab(), "Cone trends")
        graphs_tabs.addTab(self._build_graphs_metrics_corr_tab(), "Correlation")
        graphs_tabs.addTab(self._build_graphs_scatter_tab(), "Scatter")
        graphs_tabs.addTab(self._build_graphs_histogram_tab(), "Histogram")
        graphs_tabs.addTab(self._build_graphs_distribution2d_tab(), "2D Distribution")
        graphs_tabs.addTab(self._build_graphs_boxplot_tab(), "Boxplot")
        graphs_tabs.addTab(self._build_graphs_scatters_tab2(), "Custom multi")

        layout.addWidget(graphs_tabs)
        return page

    def _build_graphs_cone_trends_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        controls_row = QHBoxLayout()
        self.graphs_use_manual_fix_check = QCheckBox("Use manual fix")
        self.graphs_use_manual_fix_check.setChecked(self.use_manual_fix_check.isChecked())
        self.graphs_refresh_button = QPushButton("Refresh")
        self.graphs_source_label = QLabel("Source: -")
        self.graphs_source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        controls_row.addWidget(self.graphs_use_manual_fix_check)
        controls_row.addWidget(self.graphs_refresh_button)
        controls_row.addWidget(self.graphs_source_label)
        controls_row.addStretch(1)

        self.graphs_figure = plt.figure(figsize=(13.0, 8.2))
        self.graphs_canvas = FigureCanvas(self.graphs_figure)

        self.graphs_refresh_button.clicked.connect(self._refresh_graphs_cone_trends)
        self.graphs_use_manual_fix_check.toggled.connect(
            lambda _checked: self._refresh_graphs_cone_trends()
        )

        layout.addLayout(controls_row)
        layout.addWidget(self.graphs_canvas)

        self._refresh_graphs_cone_trends()
        return tab

    def _refresh_graphs_cone_trends(self) -> None:
        source_df = self._load_analyzer_metrics_csv(
            "cone_summary.csv",
            "Graphs",
            use_manual_fix=self.graphs_use_manual_fix_check.isChecked(),
            show_error=False,
        )
        if source_df is None:
            source_df = pd.DataFrame()

        self.graphs_figure.clear()
        axes = self.graphs_figure.subplots(4, 2, sharex=True)
        axes_flat = list(axes.flatten())

        output_dir = Path(self.base_path_edit.text().strip()) / "output" / "analyzer"
        source_name = (
            "fix_cone_summary.csv"
            if self.graphs_use_manual_fix_check.isChecked()
            else "cone_summary.csv"
        )
        self.graphs_source_label.setText(f"Source: {output_dir / source_name}")

        if source_df.empty or "cone_id" not in source_df.columns:
            for ax in axes_flat:
                ax.text(0.5, 0.5, "No cone data", ha="center", va="center")
                ax.set_axis_off()
            self.graphs_figure.tight_layout()
            self.graphs_canvas.draw()
            return

        ids = pd.to_numeric(source_df["cone_id"], errors="coerce")
        work = source_df.copy()
        work["cone_id_num"] = ids
        work = work.dropna(subset=["cone_id_num"]).sort_values("cone_id_num")

        if work.empty:
            for ax in axes_flat:
                ax.text(0.5, 0.5, "No cone IDs", ha="center", va="center")
                ax.set_axis_off()
            self.graphs_figure.tight_layout()
            self.graphs_canvas.draw()
            return

        metric_specs = [
            ("height", "H", "m"),
            ("depth", "D", "m"),
            ("base_major_diameter (WCO)", "WCO", "m"),
            ("top_major_diameter (WCR)", "WCR", "m"),
            ("H_WCO_ratio", "H/WCO", "-"),
            ("WCR_WCO_ratio", "WCR/WCO", "-"),
            ("volume", "Volume", "km^3"),
        ]

        x_vals = work["cone_id_num"].to_numpy(dtype=float)
        for idx, (column_name, label, unit) in enumerate(metric_specs):
            ax = axes_flat[idx]
            if column_name not in work.columns:
                ax.text(0.5, 0.5, "No data", ha="center", va="center")
                ax.set_title(f"{label} [{unit}]")
                ax.set_axis_off()
                continue

            series = pd.to_numeric(work[column_name], errors="coerce")
            if column_name == "volume":
                series = series / 1_000_000_000.0

            valid = series.notna()
            if valid.sum() < 2:
                ax.text(0.5, 0.5, "Insufficient data", ha="center", va="center")
                ax.set_title(f"{label} [{unit}]")
                ax.set_axis_off()
                continue

            x = work.loc[valid, "cone_id_num"].to_numpy(dtype=float)
            y = series[valid].to_numpy(dtype=float)
            order = np.argsort(x)
            x = x[order]
            y = y[order]

            ax.plot(x, y, color="#4C78A8", linewidth=1.2, alpha=0.8)
            ax.scatter(x, y, color="#4C78A8", s=24, alpha=0.9)

            median_val = float(np.nanmedian(y))
            ax.axhline(median_val, color="#F58518", linestyle=":", linewidth=1.2)

            if np.unique(x).size > 1:
                slope, intercept = np.polyfit(x, y, 1)
                ax.plot(x, slope * x + intercept, color="#54A24B", linestyle="--", linewidth=1.4)

            ax.set_title(f"{label} [{unit}]")
            ax.grid(True, alpha=0.25)

        for idx in range(len(metric_specs), len(axes_flat)):
            axes_flat[idx].set_axis_off()

        for idx in range(len(axes_flat) - 2, len(axes_flat)):
            if not axes_flat[idx].axison:
                continue
            axes_flat[idx].set_xlabel("Cone ID")

        legend_handles = [
            Line2D(
                [0], [0], color="#4C78A8", marker="o", linestyle="-", linewidth=1.2, label="Data"
            ),
            Line2D([0], [0], color="#F58518", linestyle=":", linewidth=1.2, label="Median"),
            Line2D([0], [0], color="#54A24B", linestyle="--", linewidth=1.4, label="Linear trend"),
        ]
        self.graphs_figure.legend(
            handles=legend_handles, loc="upper right", fontsize=8, frameon=True
        )

        if x_vals.size:
            xmin = float(np.nanmin(x_vals))
            xmax = float(np.nanmax(x_vals))
            if np.isfinite(xmin) and np.isfinite(xmax) and xmin != xmax:
                for ax in axes_flat:
                    if ax.axison:
                        ax.set_xlim(xmin - 0.5, xmax + 0.5)

        self.graphs_figure.suptitle("Cone metrics by cone ID", fontsize=12)
        self.graphs_figure.tight_layout(rect=[0.0, 0.0, 1.0, 0.95])

        self.graphs_canvas.draw()

    def _build_graphs_metrics_graphs_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        top_row = QHBoxLayout()
        self.graphs_metrics_use_manual_fix_check = QCheckBox("Use manual fix")
        self.graphs_metrics_use_manual_fix_check.setChecked(self.use_manual_fix_check.isChecked())
        self.graphs_metrics_refresh_button = QPushButton("Refresh")
        self.graphs_metrics_source_label = QLabel("Source: -")
        self.graphs_metrics_source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        top_row.addWidget(self.graphs_metrics_use_manual_fix_check)
        top_row.addWidget(self.graphs_metrics_refresh_button)
        top_row.addWidget(self.graphs_metrics_source_label)
        top_row.addStretch(1)

        self.graphs_metrics_figure, self.graphs_metrics_axes = plt.subplots(1, 2, figsize=(12, 4.8))
        self.graphs_metrics_canvas = FigureCanvas(self.graphs_metrics_figure)

        self.graphs_metrics_refresh_button.clicked.connect(self._refresh_graphs_metrics_graphs)
        self.graphs_metrics_use_manual_fix_check.toggled.connect(
            lambda _checked: self._refresh_graphs_metrics_graphs()
        )

        layout.addLayout(top_row)
        layout.addWidget(self.graphs_metrics_canvas)

        self._refresh_graphs_metrics_graphs()
        return tab

    def _refresh_graphs_metrics_graphs(self) -> None:
        excluded_graph_metrics = {"volume", "H_WCO_ratio", "WCR_WCO_ratio"}

        source_df = self._load_analyzer_metrics_csv(
            "cone_summary.csv",
            "Metrics graphs",
            use_manual_fix=self.graphs_metrics_use_manual_fix_check.isChecked(),
            show_error=False,
        )
        if source_df is None:
            source_df = pd.DataFrame()

        ax_left, ax_right = self.graphs_metrics_axes
        ax_left.clear()
        ax_right.clear()

        metrics_df = self._extract_cone_metric_plot_columns(source_df)
        numeric_df = metrics_df.drop(columns=list(excluded_graph_metrics), errors="ignore")
        numeric_columns = [
            column for column in numeric_df.columns if numeric_df[column].notna().any()
        ]

        volume_df = pd.DataFrame()
        if "cone_id" in source_df.columns and "volume" in metrics_df.columns:
            volume_df = pd.DataFrame(
                {
                    "cone_id": pd.to_numeric(source_df["cone_id"], errors="coerce"),
                    "volume_km3": pd.to_numeric(metrics_df["volume"], errors="coerce")
                    / 1_000_000_000.0,
                }
            ).dropna()

        output_dir = Path(self.base_path_edit.text().strip()) / "output" / "analyzer"
        output_dir.mkdir(parents=True, exist_ok=True)
        graph_name = (
            "fix_cross_metrics_graphs.png"
            if self.graphs_metrics_use_manual_fix_check.isChecked()
            else "cross_metrics_graphs.png"
        )
        graphs_path = output_dir / graph_name

        if numeric_df.dropna(how="all").empty or not numeric_columns:
            ax_left.text(0.5, 0.5, "No numeric values", ha="center", va="center")
            ax_left.set_axis_off()
        else:
            numeric_df = numeric_df[numeric_columns]
            numeric_df.boxplot(ax=ax_left)
            ax_left.set_title("Metric distributions (boxplot)")
            ax_left.set_ylabel("Value")
            ax_left.tick_params(axis="x", rotation=30)

        if volume_df.empty:
            ax_right.text(0.5, 0.5, "No volume values", ha="center", va="center")
            ax_right.set_axis_off()
        else:
            ax_right.scatter(
                volume_df["cone_id"], volume_df["volume_km3"], alpha=0.75, color="#4C78A8"
            )
            ax_right.set_title("Volume by cone (scatter, km^3)")
            ax_right.set_xlabel("Cone ID")
            ax_right.set_ylabel("Volume (km^3)")

            if len(volume_df) >= 2:
                trend_coeff = np.polyfit(volume_df["cone_id"], volume_df["volume_km3"], deg=1)
                trend = np.poly1d(trend_coeff)
                x_sorted = np.sort(volume_df["cone_id"].to_numpy())
                ax_right.plot(
                    x_sorted, trend(x_sorted), color="#E45756", linewidth=2, label="Trend line"
                )
                ax_right.legend(loc="best")

            top_n = volume_df.nlargest(min(3, len(volume_df)), "volume_km3")
            for _, row in top_n.iterrows():
                ax_right.annotate(
                    f"{int(row['cone_id'])}",
                    (row["cone_id"], row["volume_km3"]),
                    textcoords="offset points",
                    xytext=(4, 4),
                    fontsize=8,
                )

        self.graphs_metrics_figure.tight_layout()
        self.graphs_metrics_figure.savefig(graphs_path, dpi=200)

        source_name = (
            "fix_cone_summary.csv"
            if self.graphs_metrics_use_manual_fix_check.isChecked()
            else "cone_summary.csv"
        )
        self.graphs_metrics_source_label.setText(
            f"Source: {output_dir / source_name} | Saved graph: {graphs_path}"
        )
        self.graphs_metrics_canvas.draw_idle()

    def _build_graphs_metrics_corr_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        top_row = QHBoxLayout()
        self.graphs_corr_use_manual_fix_check = QCheckBox("Use manual fix")
        self.graphs_corr_use_manual_fix_check.setChecked(self.use_manual_fix_check.isChecked())
        self.graphs_corr_refresh_button = QPushButton("Refresh")
        self.graphs_corr_source_label = QLabel("Source: -")
        self.graphs_corr_source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        top_row.addWidget(self.graphs_corr_use_manual_fix_check)
        top_row.addWidget(self.graphs_corr_refresh_button)
        top_row.addWidget(self.graphs_corr_source_label)
        top_row.addStretch(1)

        metrics_row = QHBoxLayout()
        self.graphs_corr_metric_checks: dict[str, QCheckBox] = {}
        metric_order = [
            "Wco",
            "Wcr",
            "H",
            "D",
            "avg_slope_deg",
            "H_WCO_ratio",
            "WCR_WCO_ratio",
            "volume",
        ]
        metrics_row.addWidget(QLabel("Metrics:"))
        for metric_name in metric_order:
            check = QCheckBox(metric_name)
            check.setChecked(True)
            self.graphs_corr_metric_checks[metric_name] = check
            metrics_row.addWidget(check)
        self.graphs_corr_metrics_select_all_button = QPushButton("Select all")
        self.graphs_corr_metrics_clear_all_button = QPushButton("Clear all")
        metrics_row.addWidget(self.graphs_corr_metrics_select_all_button)
        metrics_row.addWidget(self.graphs_corr_metrics_clear_all_button)
        metrics_row.addStretch(1)

        controls_row = QHBoxLayout()
        self.graphs_corr_method_combo = QComboBox()
        self.graphs_corr_method_combo.addItems(["Pearson", "Spearman"])
        self.graphs_corr_annotate_check = QCheckBox("Annotate values")
        self.graphs_corr_annotate_check.setChecked(True)
        self.graphs_corr_half_matrix_check = QCheckBox("Half matrix (lower triangle)")
        self.graphs_corr_half_matrix_check.setChecked(False)
        self.graphs_corr_cmap_combo = QComboBox()
        self.graphs_corr_cmap_combo.addItems(["RdBu_r", "coolwarm", "BrBG", "PiYG"])
        controls_row.addWidget(QLabel("Method:"))
        controls_row.addWidget(self.graphs_corr_method_combo)
        controls_row.addWidget(self.graphs_corr_annotate_check)
        controls_row.addWidget(self.graphs_corr_half_matrix_check)
        controls_row.addWidget(QLabel("Cmap:"))
        controls_row.addWidget(self.graphs_corr_cmap_combo)
        controls_row.addStretch(1)

        self.graphs_corr_figure, self.graphs_corr_ax = plt.subplots(1, 1, figsize=(9.8, 6.0))
        self.graphs_corr_canvas = FigureCanvas(self.graphs_corr_figure)
        self.graphs_corr_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.graphs_corr_summary_label = QLabel("Correlation summary: refresh to compute")
        self.graphs_corr_summary_label.setWordWrap(True)
        self.graphs_corr_summary_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.graphs_corr_summary_label.setTextFormat(Qt.RichText)
        self.graphs_corr_summary_label.setFixedWidth(340)
        self.graphs_corr_export_pairs_button = QPushButton("Export pairs table (CSV)")
        self.graphs_corr_export_pairs_button.setEnabled(False)
        self.graphs_corr_pairs_export_df = pd.DataFrame()
        self.graphs_corr_colorbar = None

        self.graphs_corr_refresh_button.clicked.connect(self._refresh_graphs_metrics_corr)
        self.graphs_corr_use_manual_fix_check.toggled.connect(
            lambda _checked: self._refresh_graphs_metrics_corr()
        )
        self.graphs_corr_method_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_metrics_corr()
        )
        for check in self.graphs_corr_metric_checks.values():
            check.toggled.connect(lambda _checked: self._refresh_graphs_metrics_corr())
        self.graphs_corr_metrics_select_all_button.clicked.connect(
            lambda: self._set_graphs_corr_metric_checks(True)
        )
        self.graphs_corr_metrics_clear_all_button.clicked.connect(
            lambda: self._set_graphs_corr_metric_checks(False)
        )
        self.graphs_corr_annotate_check.toggled.connect(
            lambda _checked: self._refresh_graphs_metrics_corr()
        )
        self.graphs_corr_half_matrix_check.toggled.connect(
            lambda _checked: self._refresh_graphs_metrics_corr()
        )
        self.graphs_corr_cmap_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_metrics_corr()
        )
        self.graphs_corr_export_pairs_button.clicked.connect(
            self._save_graphs_corr_pairs_table
        )

        layout.addLayout(top_row)
        layout.addLayout(metrics_row)
        layout.addLayout(controls_row)
        body_row = QHBoxLayout()
        summary_panel = QVBoxLayout()
        summary_panel.addWidget(self.graphs_corr_summary_label)
        summary_panel.addWidget(self.graphs_corr_export_pairs_button)
        summary_panel.addStretch(1)
        body_row.addLayout(summary_panel)
        body_row.addWidget(self.graphs_corr_canvas, 1)
        layout.addLayout(body_row, 1)

        self._refresh_graphs_metrics_corr()
        return tab

    def _selected_graphs_corr_metrics(self, available_columns: list[str]) -> list[str]:
        selected_metrics: list[str] = []
        for metric_name, check in self.graphs_corr_metric_checks.items():
            if check.isChecked() and metric_name in available_columns:
                selected_metrics.append(metric_name)
        return selected_metrics

    def _set_graphs_corr_metric_checks(self, checked: bool) -> None:
        for check in self.graphs_corr_metric_checks.values():
            if not check.isEnabled():
                continue
            check.blockSignals(True)
            check.setChecked(checked)
            check.blockSignals(False)
        self._refresh_graphs_metrics_corr()

    def _graphs_corr_fdr_bh(self, p_values: np.ndarray) -> np.ndarray:
        if p_values.size == 0:
            return np.array([], dtype=float)
        order = np.argsort(p_values)
        ranked = p_values[order]
        m = float(len(ranked))
        q_ranked = np.zeros(len(ranked), dtype=float)
        running_min = 1.0
        for idx in range(len(ranked) - 1, -1, -1):
            rank = float(idx + 1)
            candidate = ranked[idx] * m / rank
            running_min = min(running_min, candidate)
            q_ranked[idx] = running_min
        out = np.empty(len(ranked), dtype=float)
        out[order] = np.clip(q_ranked, 0.0, 1.0)
        return out

    def _graphs_corr_sig_marker(self, p_value: float, q_value: float) -> str:
        if pd.notna(q_value):
            if q_value < 0.001:
                return "***"
            if q_value < 0.01:
                return "**"
            if q_value < 0.05:
                return "*"
            return ""
        if pd.notna(p_value):
            if p_value < 0.001:
                return "***"
            if p_value < 0.01:
                return "**"
            if p_value < 0.05:
                return "*"
        return ""

    def _save_graphs_corr_pairs_table(self) -> None:
        if self.graphs_corr_pairs_export_df.empty:
            QMessageBox.information(self, "Correlation", "No pair statistics to export yet.")
            return

        output_dir = Path(self.base_path_edit.text().strip()) / "output" / "analyzer"
        output_dir.mkdir(parents=True, exist_ok=True)
        method_text = self.graphs_corr_method_combo.currentText().strip().lower() or "pearson"
        csv_name = (
            f"fix_cross_metrics_correlation_pairs_{method_text}.csv"
            if self.graphs_corr_use_manual_fix_check.isChecked()
            else f"cross_metrics_correlation_pairs_{method_text}.csv"
        )
        csv_path = output_dir / csv_name
        self.graphs_corr_pairs_export_df.to_csv(csv_path, sep=";", index=False)
        self.statusBar().showMessage(f"Saved: {csv_path}", 5000)

    def _refresh_graphs_metrics_corr(self) -> None:
        source_df = self._load_analyzer_metrics_csv(
            "cone_summary.csv",
            "Metrics correlation",
            use_manual_fix=self.graphs_corr_use_manual_fix_check.isChecked(),
            show_error=False,
        )
        if source_df is None:
            source_df = pd.DataFrame()

        ax = self.graphs_corr_ax

        if self.graphs_corr_colorbar is not None:
            self.graphs_corr_colorbar.remove()
            self.graphs_corr_colorbar = None
        ax.clear()

        metrics_df = self._extract_cone_metric_plot_columns(source_df)
        available_columns = [
            column for column in metrics_df.columns if metrics_df[column].notna().any()
        ]
        for metric_name, check in self.graphs_corr_metric_checks.items():
            check.setEnabled(metric_name in available_columns)
        selected_columns = self._selected_graphs_corr_metrics(available_columns)

        output_dir = Path(self.base_path_edit.text().strip()) / "output" / "analyzer"
        output_dir.mkdir(parents=True, exist_ok=True)
        method_text = self.graphs_corr_method_combo.currentText().strip().lower() or "pearson"
        show_half_matrix = self.graphs_corr_half_matrix_check.isChecked()
        graph_name = (
            f"fix_cross_metrics_correlation_{method_text}.png"
            if self.graphs_corr_use_manual_fix_check.isChecked()
            else f"cross_metrics_correlation_{method_text}.png"
        )
        graph_path = output_dir / graph_name

        if len(selected_columns) < 2:
            ax.text(
                0.5,
                0.5,
                "Select at least 2 valid metrics\n(check at least two metric boxes)",
                ha="center",
                va="center",
            )
            ax.set_axis_off()
            self.graphs_corr_summary_label.setText(
                "<b>Correlation summary</b><br>"
                "Select at least 2 valid metrics to compute pair statistics."
            )
            self.graphs_corr_pairs_export_df = pd.DataFrame()
            self.graphs_corr_export_pairs_button.setEnabled(False)
        else:
            corr_input_df = metrics_df[selected_columns].copy()
            corr = corr_input_df.corr(method=method_text, numeric_only=True)
            p_matrix = pd.DataFrame(np.nan, index=corr.index, columns=corr.columns, dtype=float)
            q_matrix = pd.DataFrame(np.nan, index=corr.index, columns=corr.columns, dtype=float)
            for metric_name in corr.columns:
                p_matrix.loc[metric_name, metric_name] = 0.0
                q_matrix.loc[metric_name, metric_name] = 0.0

            pair_stats: list[dict[str, float | str]] = []
            valid_p_positions: list[int] = []
            valid_p_values: list[float] = []
            for i, metric_a in enumerate(corr.columns):
                for j in range(i + 1, len(corr.columns)):
                    metric_b = str(corr.columns[j])
                    pair_df = corr_input_df[[metric_a, metric_b]].dropna()
                    n_obs = int(len(pair_df))
                    if n_obs < 2:
                        continue

                    x_vals = pair_df[metric_a].to_numpy(dtype=float)
                    y_vals = pair_df[metric_b].to_numpy(dtype=float)
                    if method_text == "spearman" and SCIPY_SPEARMANR is not None:
                        r_val, p_val = SCIPY_SPEARMANR(x_vals, y_vals)
                    elif method_text == "pearson" and SCIPY_PEARSONR is not None:
                        r_val, p_val = SCIPY_PEARSONR(x_vals, y_vals)
                    else:
                        r_val = float(pair_df[metric_a].corr(pair_df[metric_b], method=method_text))
                        p_val = np.nan

                    r_val = float(r_val) if pd.notna(r_val) else np.nan
                    p_val = float(p_val) if pd.notna(p_val) else np.nan
                    p_matrix.loc[metric_a, metric_b] = p_val
                    p_matrix.loc[metric_b, metric_a] = p_val

                    pair_stats.append(
                        {
                            "a": str(metric_a),
                            "b": str(metric_b),
                            "r": r_val,
                            "p": p_val,
                            "q": np.nan,
                            "n": float(n_obs),
                        }
                    )
                    if pd.notna(p_val):
                        valid_p_positions.append(len(pair_stats) - 1)
                        valid_p_values.append(p_val)

            if valid_p_values:
                q_values = self._graphs_corr_fdr_bh(np.asarray(valid_p_values, dtype=float))
                for pos, q_val in zip(valid_p_positions, q_values):
                    pair_stats[pos]["q"] = float(q_val)

            for item in pair_stats:
                metric_a = str(item["a"])
                metric_b = str(item["b"])
                q_val = float(item["q"])
                q_matrix.loc[metric_a, metric_b] = q_val
                q_matrix.loc[metric_b, metric_a] = q_val

            pairs_export_df = pd.DataFrame(
                [
                    {
                        "method": method_text,
                        "metric_a": str(row["a"]),
                        "metric_b": str(row["b"]),
                        "r": float(row["r"]),
                        "abs_r": abs(float(row["r"])),
                        "p_value": float(row["p"]),
                        "q_value_fdr_bh": float(row["q"]),
                        "n_pairwise": int(float(row["n"])),
                        "significance": self._graphs_corr_sig_marker(
                            float(row["p"]), float(row["q"])
                        ),
                    }
                    for row in pair_stats
                ]
            )
            if not pairs_export_df.empty:
                pairs_export_df = pairs_export_df.sort_values("abs_r", ascending=False)
            self.graphs_corr_pairs_export_df = pairs_export_df
            self.graphs_corr_export_pairs_button.setEnabled(not pairs_export_df.empty)

            cmap_name = self.graphs_corr_cmap_combo.currentText().strip() or "RdBu_r"
            corr_for_plot = corr.values
            if show_half_matrix:
                mask = np.triu(np.ones_like(corr_for_plot, dtype=bool), k=1)
                corr_for_plot = np.ma.array(corr_for_plot, mask=mask)

            image = ax.imshow(corr_for_plot, vmin=-1.0, vmax=1.0, cmap=cmap_name)
            ax.set_xticks(range(len(corr.columns)))
            ax.set_xticklabels(corr.columns, rotation=35, ha="right")
            ax.set_yticks(range(len(corr.index)))
            ax.set_yticklabels(corr.index)
            ax.set_title(f"Correlation matrix ({method_text.title()})")

            if self.graphs_corr_annotate_check.isChecked():
                for i in range(len(corr.index)):
                    for j in range(len(corr.columns)):
                        if show_half_matrix and j > i:
                            continue
                        val = float(corr.iloc[i, j])
                        p_val = float(p_matrix.iloc[i, j])
                        q_val = float(q_matrix.iloc[i, j])
                        marker = "" if i == j else self._graphs_corr_sig_marker(p_val, q_val)
                        text_color = "white" if abs(val) >= 0.55 else "black"
                        ax.text(
                            j,
                            i,
                            f"{val:.2f}{marker}",
                            ha="center",
                            va="center",
                            fontsize=8,
                            color=text_color,
                        )

            self.graphs_corr_colorbar = self.graphs_corr_figure.colorbar(
                image,
                ax=ax,
                fraction=0.046,
                pad=0.04,
            )
            self.graphs_corr_colorbar.set_label(f"{method_text.title()} r")

            finite_pairs = [row for row in pair_stats if pd.notna(float(row["r"]))]
            strong_threshold = 0.6
            strong_pairs = [
                row for row in finite_pairs if abs(float(row["r"])) >= strong_threshold
            ]
            sig_p_pairs = [
                row
                for row in finite_pairs
                if pd.notna(float(row["p"])) and float(row["p"]) < 0.05
            ]
            sig_q_pairs = [
                row
                for row in finite_pairs
                if pd.notna(float(row["q"])) and float(row["q"]) < 0.05
            ]
            n_values = [int(float(row["n"])) for row in finite_pairs]
            n_range = "-"
            if n_values:
                n_range = f"{min(n_values)}-{max(n_values)}"

            top_positive = sorted(
                finite_pairs,
                key=lambda row: float(row["r"]),
                reverse=True,
            )[:3]
            top_negative = sorted(finite_pairs, key=lambda row: float(row["r"]))[:3]

            def _format_row(row: dict[str, float | str]) -> str:
                q_val = float(row["q"])
                q_text = f", q={q_val:.3g}" if pd.notna(q_val) else ""
                p_val = float(row["p"])
                p_text = f", p={p_val:.3g}" if pd.notna(p_val) else ""
                return (
                    f"{row['a']} ~ {row['b']}: r={float(row['r']):.2f}{p_text}{q_text}, "
                    f"N={int(float(row['n']))}"
                )

            top_pos_html = (
                "<br>".join(_format_row(row) for row in top_positive)
                if top_positive
                else "-"
            )
            top_neg_html = (
                "<br>".join(_format_row(row) for row in top_negative)
                if top_negative
                else "-"
            )
            stats_backend = (
                "scipy"
                if (SCIPY_PEARSONR is not None and SCIPY_SPEARMANR is not None)
                else "p-values unavailable"
            )

            self.graphs_corr_summary_label.setText(
                "<b>Correlation summary</b><br>"
                f"Method: <b>{method_text.title()}</b><br>"
                f"Metrics: <b>{len(selected_columns)}</b><br>"
                f"Pairs tested: <b>{len(finite_pairs)}</b><br>"
                f"N range (pairwise): <b>{n_range}</b><br>"
                f"Strong pairs (|r| &ge; {strong_threshold:.1f}): <b>{len(strong_pairs)}</b><br>"
                f"Significant p&lt;0.05: <b>{len(sig_p_pairs)}</b><br>"
                f"Significant q&lt;0.05 (FDR-BH): <b>{len(sig_q_pairs)}</b><br>"
                f"Stats backend: <b>{stats_backend}</b><br><br>"
                "<b>Top positive</b><br>"
                f"{top_pos_html}<br><br>"
                "<b>Top negative</b><br>"
                f"{top_neg_html}<br><br>"
                "<b>Strength scale (|r|)</b><br>"
                "0.0-0.2 very weak<br>"
                "0.2-0.4 weak<br>"
                "0.4-0.6 moderate<br>"
                "0.6-0.8 strong<br>"
                "0.8-1.0 very strong<br><br>"
                "<small>* q&lt;0.05, ** q&lt;0.01, *** q&lt;0.001 "
                "(fallback to p when q unavailable)</small>"
            )

        self.graphs_corr_figure.tight_layout()
        self.graphs_corr_figure.savefig(graph_path, dpi=200)

        source_name = (
            "fix_cone_summary.csv"
            if self.graphs_corr_use_manual_fix_check.isChecked()
            else "cone_summary.csv"
        )
        shown_metrics = selected_columns if selected_columns else available_columns
        metrics_preview = ", ".join(shown_metrics[:6])
        if len(shown_metrics) > 6:
            metrics_preview += ", ..."
        self.graphs_corr_source_label.setText(
            f"Source: {output_dir / source_name} | Method: {method_text.title()}"
            f" | Metrics: {metrics_preview} | Saved: {graph_path.name}"
        )
        self.graphs_corr_canvas.draw_idle()

    def _build_graphs_wco_wcr_scatter_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        top_row = QHBoxLayout()
        self.graphs_wco_use_manual_fix_check = QCheckBox("Use manual fix")
        self.graphs_wco_use_manual_fix_check.setChecked(self.use_manual_fix_check.isChecked())
        self.graphs_wco_refresh_button = QPushButton("Refresh")
        self.graphs_wco_source_label = QLabel("Source: -")
        self.graphs_wco_source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        top_row.addWidget(self.graphs_wco_use_manual_fix_check)
        top_row.addWidget(self.graphs_wco_refresh_button)
        top_row.addWidget(self.graphs_wco_source_label)
        top_row.addStretch(1)

        self.graphs_wco_figure, self.graphs_wco_axes = plt.subplots(1, 2, figsize=(13.6, 5.0))
        self.graphs_wco_canvas = FigureCanvas(self.graphs_wco_figure)
        self.graphs_wco_colorbar1 = None
        self.graphs_wco_colorbar2 = None

        self.graphs_wco_refresh_button.clicked.connect(self._refresh_graphs_wco_wcr_scatter)
        self.graphs_wco_use_manual_fix_check.toggled.connect(
            lambda _checked: self._refresh_graphs_wco_wcr_scatter()
        )

        layout.addLayout(top_row)
        layout.addWidget(self.graphs_wco_canvas)

        self._refresh_graphs_wco_wcr_scatter()
        return tab

    def _refresh_graphs_wco_wcr_scatter(self) -> None:
        source_df = self._load_analyzer_metrics_csv(
            "cone_summary.csv",
            "Wco scatter",
            use_manual_fix=self.graphs_wco_use_manual_fix_check.isChecked(),
            show_error=False,
        )
        if source_df is None:
            source_df = pd.DataFrame()

        ax_left, ax_right = self.graphs_wco_axes

        if self.graphs_wco_colorbar1 is not None:
            self.graphs_wco_colorbar1.remove()
            self.graphs_wco_colorbar1 = None
        if self.graphs_wco_colorbar2 is not None:
            self.graphs_wco_colorbar2.remove()
            self.graphs_wco_colorbar2 = None

        ax_left.clear()
        ax_right.clear()

        metrics_df = self._extract_cone_metric_plot_columns(source_df)
        scatter_df = pd.DataFrame(
            {
                "cone_id": self._safe_numeric_series(source_df, "cone_id"),
                "Wco": self._safe_numeric_series(metrics_df, "Wco", source_df.index),
                "Wcr": self._safe_numeric_series(metrics_df, "Wcr", source_df.index),
                "D": self._safe_numeric_series(metrics_df, "D", source_df.index),
                "H_WCO_ratio": self._safe_numeric_series(
                    metrics_df, "H_WCO_ratio", source_df.index
                ),
            }
        ).dropna(subset=["Wco", "Wcr", "D", "H_WCO_ratio"])

        output_dir = Path(self.base_path_edit.text().strip()) / "output" / "analyzer"
        output_dir.mkdir(parents=True, exist_ok=True)
        graph_name = (
            "fix_cross_wco_wcr_depth_scatter.png"
            if self.graphs_wco_use_manual_fix_check.isChecked()
            else "cross_wco_wcr_depth_scatter.png"
        )
        graph_path = output_dir / graph_name

        if scatter_df.empty:
            ax_left.text(0.5, 0.5, "No data", ha="center", va="center")
            ax_left.set_axis_off()
            ax_right.text(0.5, 0.5, "No data", ha="center", va="center")
            ax_right.set_axis_off()
        else:
            points1 = ax_left.scatter(
                scatter_df["Wco"],
                scatter_df["Wcr"],
                c=scatter_df["D"],
                cmap="viridis",
                alpha=0.8,
                edgecolors="k",
                linewidths=0.3,
            )
            ax_left.set_title("Wco vs Wcr (colored by depth)")
            ax_left.set_xlabel("Wco")
            ax_left.set_ylabel("Wcr")
            self.graphs_wco_colorbar1 = self.graphs_wco_figure.colorbar(
                points1, ax=ax_left, fraction=0.046, pad=0.04
            )
            self.graphs_wco_colorbar1.set_label("Depth")

            if len(scatter_df) >= 2:
                coeff = np.polyfit(scatter_df["Wco"], scatter_df["Wcr"], deg=1)
                trend = np.poly1d(coeff)
                x_sorted = np.sort(scatter_df["Wco"].to_numpy())
                ax_left.plot(x_sorted, trend(x_sorted), color="#E45756", linewidth=2, label="Trend")
                ax_left.legend(loc="best")

            deepest = scatter_df.nlargest(min(3, len(scatter_df)), "D")
            for _, row in deepest.iterrows():
                cone_id = int(row["cone_id"]) if pd.notna(row["cone_id"]) else "?"
                ax_left.annotate(
                    str(cone_id),
                    (row["Wco"], row["Wcr"]),
                    textcoords="offset points",
                    xytext=(4, 4),
                    fontsize=8,
                )

            points2 = ax_right.scatter(
                scatter_df["Wcr"],
                scatter_df["H_WCO_ratio"],
                c=scatter_df["D"],
                cmap="viridis",
                alpha=0.8,
                edgecolors="k",
                linewidths=0.3,
            )
            ax_right.set_title("Wcr vs H/Wco ratio (colored by depth)")
            ax_right.set_xlabel("Wcr")
            ax_right.set_ylabel("H/Wco ratio")
            self.graphs_wco_colorbar2 = self.graphs_wco_figure.colorbar(
                points2, ax=ax_right, fraction=0.046, pad=0.04
            )
            self.graphs_wco_colorbar2.set_label("Depth")

            if len(scatter_df) >= 2:
                coeff2 = np.polyfit(scatter_df["Wcr"], scatter_df["H_WCO_ratio"], deg=1)
                trend2 = np.poly1d(coeff2)
                x_sorted2 = np.sort(scatter_df["Wcr"].to_numpy())
                ax_right.plot(
                    x_sorted2, trend2(x_sorted2), color="#E45756", linewidth=2, label="Trend"
                )
                ax_right.legend(loc="best")

        self.graphs_wco_figure.tight_layout()
        self.graphs_wco_figure.savefig(graph_path, dpi=200)

        source_name = (
            "fix_cone_summary.csv"
            if self.graphs_wco_use_manual_fix_check.isChecked()
            else "cone_summary.csv"
        )
        self.graphs_wco_source_label.setText(
            f"Source: {output_dir / source_name} | Saved: {graph_path}"
        )
        self.graphs_wco_canvas.draw_idle()

    def _build_graphs_scatters_tab1(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        top_row = QHBoxLayout()
        self.graphs_scatters1_use_manual_fix_check = QCheckBox("Use manual fix")
        self.graphs_scatters1_use_manual_fix_check.setChecked(self.use_manual_fix_check.isChecked())
        self.graphs_scatters1_refresh_button = QPushButton("Refresh")
        self.graphs_scatters1_source_label = QLabel("Source: -")
        self.graphs_scatters1_source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        top_row.addWidget(self.graphs_scatters1_use_manual_fix_check)
        top_row.addWidget(self.graphs_scatters1_refresh_button)
        top_row.addWidget(self.graphs_scatters1_source_label)
        top_row.addStretch(1)
        layout.addLayout(top_row)

        tab1_widget = QWidget()
        tab1_layout = QVBoxLayout(tab1_widget)
        self.graphs_scatters_fig1, self.graphs_scatters_axes1 = plt.subplots(
            1, 2, figsize=(11.6, 5.2)
        )
        self.graphs_scatters_canvas1 = FigureCanvas(self.graphs_scatters_fig1)
        self.graphs_scatters_hist_colorbar1 = None
        tab1_layout.addWidget(self.graphs_scatters_canvas1)
        layout.addWidget(tab1_widget)

        self.graphs_scatters1_refresh_button.clicked.connect(self._refresh_graphs_scatters_tab1)
        self.graphs_scatters1_use_manual_fix_check.toggled.connect(
            lambda _checked: self._refresh_graphs_scatters_tab1()
        )

        self._refresh_graphs_scatters_tab1()
        return tab

    def _build_graphs_boxplot_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        self.graphs_box_use_manual_fix_check = QCheckBox("Use manual fix")
        self.graphs_box_use_manual_fix_check.setChecked(self.use_manual_fix_check.isChecked())
        self.graphs_box_refresh_button = QPushButton("Refresh")
        self.graphs_box_source_label = QLabel("Source: -")
        self.graphs_box_source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        top_row.addWidget(self.graphs_box_use_manual_fix_check)
        top_row.addWidget(self.graphs_box_refresh_button)
        top_row.addWidget(self.graphs_box_source_label)
        top_row.addStretch(1)

        metrics_row = QHBoxLayout()
        self.graphs_box_metric_checks: dict[str, QCheckBox] = {}
        metric_order = [
            "Wco",
            "Wcr",
            "H",
            "D",
            "avg_slope_deg",
            "H_WCO_ratio",
            "WCR_WCO_ratio",
            "volume",
        ]
        metrics_row.addWidget(QLabel("Metrics:"))
        for metric_name in metric_order:
            check = QCheckBox(metric_name)
            check.setChecked(metric_name != "volume")
            self.graphs_box_metric_checks[metric_name] = check
            metrics_row.addWidget(check)
        self.graphs_box_metrics_select_all_button = QPushButton("Select all")
        self.graphs_box_metrics_clear_all_button = QPushButton("Clear all")
        metrics_row.addWidget(self.graphs_box_metrics_select_all_button)
        metrics_row.addWidget(self.graphs_box_metrics_clear_all_button)

        self.graphs_box_preset_combo = QComboBox()
        self.graphs_box_preset_combo.addItems(
            ["Custom", "Classic blue", "Earth tones", "High contrast", "Pastel"]
        )
        self.graphs_box_kind_combo = QComboBox()
        self.graphs_box_kind_combo.addItems(["Boxplot", "Violin"])
        self.graphs_box_orientation_combo = QComboBox()
        self.graphs_box_orientation_combo.addItems(["Vertical", "Horizontal"])
        metrics_row.addSpacing(8)
        metrics_row.addWidget(QLabel("Type:"))
        metrics_row.addWidget(self.graphs_box_kind_combo)
        metrics_row.addWidget(QLabel("Orientation:"))
        metrics_row.addWidget(self.graphs_box_orientation_combo)
        metrics_row.addStretch(1)

        controls_row = QHBoxLayout()
        self.graphs_box_fill_check = QCheckBox("Fill")
        self.graphs_box_fill_check.setChecked(True)
        self.graphs_box_palette_combo = QComboBox()
        self.graphs_box_palette_combo.addItems(["tab20", "Set2", "Accent", "viridis", "plasma"])
        self.graphs_box_color_mode_combo = QComboBox()
        self.graphs_box_color_mode_combo.addItems(["Per metric palette", "Single color"])
        self.graphs_box_color_edit = QLineEdit("#4C78A8")
        self.graphs_box_color_edit.setMaximumWidth(95)
        self.graphs_box_edge_style_combo = QComboBox()
        self.graphs_box_edge_style_combo.addItems(["solid", "dashed", "dashdot", "dotted"])
        self.graphs_box_edge_width_spin = QDoubleSpinBox()
        self.graphs_box_edge_width_spin.setRange(0.4, 4.0)
        self.graphs_box_edge_width_spin.setSingleStep(0.2)
        self.graphs_box_edge_width_spin.setValue(1.1)
        self.graphs_box_show_means_check = QCheckBox("Show means")
        self.graphs_box_show_means_check.setChecked(False)
        self.graphs_box_log_value_axis_check = QCheckBox("Log value axis")
        self.graphs_box_log_value_axis_check.setChecked(False)

        self.graphs_box_format_combo = QComboBox()
        self.graphs_box_format_combo.addItems(["PNG", "SVG", "PDF"])
        self.graphs_box_dpi_spin = QSpinBox()
        self.graphs_box_dpi_spin.setRange(72, 600)
        self.graphs_box_dpi_spin.setValue(200)
        self.graphs_box_dpi_spin.setSuffix(" dpi")
        self.graphs_box_save_button = QPushButton("Save plot")
        self.graphs_box_open_folder_button = QPushButton("Open output folder")

        controls_row.addWidget(QLabel("Preset:"))
        controls_row.addWidget(self.graphs_box_preset_combo)
        controls_row.addWidget(QLabel("FillColors:"))
        controls_row.addWidget(self.graphs_box_fill_check)
        controls_row.addWidget(self.graphs_box_palette_combo)
        controls_row.addWidget(self.graphs_box_color_mode_combo)
        controls_row.addWidget(self.graphs_box_color_edit)
        controls_row.addWidget(QLabel("Edge:"))
        controls_row.addWidget(self.graphs_box_edge_style_combo)
        controls_row.addWidget(self.graphs_box_edge_width_spin)
        controls_row.addWidget(self.graphs_box_show_means_check)
        controls_row.addWidget(self.graphs_box_log_value_axis_check)
        controls_row.addSpacing(12)
        controls_row.addWidget(QLabel("Format:"))
        controls_row.addWidget(self.graphs_box_format_combo)
        controls_row.addWidget(self.graphs_box_dpi_spin)
        controls_row.addWidget(self.graphs_box_save_button)
        controls_row.addWidget(self.graphs_box_open_folder_button)
        controls_row.addStretch(1)

        title_row = QHBoxLayout()
        self.graphs_box_title_edit = QLineEdit()
        self.graphs_box_title_edit.setPlaceholderText("Title (auto)")
        title_row.addWidget(QLabel("Title:"))
        title_row.addWidget(self.graphs_box_title_edit)

        self.graphs_box_figure, self.graphs_box_ax = plt.subplots(1, 1, figsize=(10.2, 6.0))
        self.graphs_box_canvas = FigureCanvas(self.graphs_box_figure)
        self.graphs_box_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.graphs_box_refresh_button.clicked.connect(self._refresh_graphs_boxplot)
        self.graphs_box_use_manual_fix_check.toggled.connect(
            lambda _checked: self._refresh_graphs_boxplot()
        )
        for check in self.graphs_box_metric_checks.values():
            check.toggled.connect(lambda _checked: self._refresh_graphs_boxplot())
        self.graphs_box_metrics_select_all_button.clicked.connect(
            lambda: self._set_graphs_box_metric_checks(True)
        )
        self.graphs_box_metrics_clear_all_button.clicked.connect(
            lambda: self._set_graphs_box_metric_checks(False)
        )
        self.graphs_box_preset_combo.currentTextChanged.connect(self._apply_graphs_boxplot_preset)
        self.graphs_box_kind_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_boxplot()
        )
        self.graphs_box_orientation_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_boxplot()
        )
        self.graphs_box_fill_check.toggled.connect(
            lambda _checked: self._refresh_graphs_boxplot()
        )
        self.graphs_box_palette_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_boxplot()
        )
        self.graphs_box_color_mode_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_boxplot()
        )
        self.graphs_box_color_edit.editingFinished.connect(self._refresh_graphs_boxplot)
        self.graphs_box_edge_style_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_boxplot()
        )
        self.graphs_box_edge_width_spin.valueChanged.connect(
            lambda _value: self._refresh_graphs_boxplot()
        )
        self.graphs_box_show_means_check.toggled.connect(
            lambda _checked: self._refresh_graphs_boxplot()
        )
        self.graphs_box_log_value_axis_check.toggled.connect(
            lambda _checked: self._refresh_graphs_boxplot()
        )
        self.graphs_box_title_edit.editingFinished.connect(self._refresh_graphs_boxplot)
        self.graphs_box_save_button.clicked.connect(self._save_graphs_boxplot)
        self.graphs_box_open_folder_button.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(
                    str(Path(self.base_path_edit.text().strip()) / "output" / "analyzer")
                )
            )
        )

        layout.addLayout(top_row)
        layout.addLayout(metrics_row)
        layout.addLayout(controls_row)
        layout.addLayout(title_row)
        layout.addWidget(self.graphs_box_canvas, 1)

        self._refresh_graphs_boxplot()
        return tab

    def _build_graphs_histogram_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        self.graphs_hist_use_manual_fix_check = QCheckBox("Use manual fix")
        self.graphs_hist_use_manual_fix_check.setChecked(self.use_manual_fix_check.isChecked())
        self.graphs_hist_refresh_button = QPushButton("Refresh")
        self.graphs_hist_source_label = QLabel("Source: -")
        self.graphs_hist_source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        top_row.addWidget(self.graphs_hist_use_manual_fix_check)
        top_row.addWidget(self.graphs_hist_refresh_button)
        top_row.addWidget(self.graphs_hist_source_label)
        top_row.addStretch(1)

        metrics_row = QHBoxLayout()
        self.graphs_hist_metric_checks: dict[str, QCheckBox] = {}
        metric_order = [
            "Wco",
            "Wcr",
            "H",
            "D",
            "avg_slope_deg",
            "H_WCO_ratio",
            "WCR_WCO_ratio",
            "volume",
        ]
        metrics_row.addWidget(QLabel("Metrics:"))
        for metric_name in metric_order:
            check = QCheckBox(metric_name)
            check.setChecked(metric_name != "volume")
            self.graphs_hist_metric_checks[metric_name] = check
            metrics_row.addWidget(check)
        self.graphs_hist_metrics_select_all_button = QPushButton("Select all")
        self.graphs_hist_metrics_clear_all_button = QPushButton("Clear all")
        metrics_row.addWidget(self.graphs_hist_metrics_select_all_button)
        metrics_row.addWidget(self.graphs_hist_metrics_clear_all_button)
        metrics_row.addStretch(1)

        controls_row = QHBoxLayout()
        self.graphs_hist_mode_combo = QComboBox()
        self.graphs_hist_mode_combo.addItems(["Overlay", "Stacked"])
        self.graphs_hist_bins_spin = QSpinBox()
        self.graphs_hist_bins_spin.setRange(5, 200)
        self.graphs_hist_bins_spin.setValue(24)
        self.graphs_hist_alpha_spin = QDoubleSpinBox()
        self.graphs_hist_alpha_spin.setRange(0.1, 1.0)
        self.graphs_hist_alpha_spin.setSingleStep(0.05)
        self.graphs_hist_alpha_spin.setValue(0.75)
        self.graphs_hist_density_check = QCheckBox("Density")
        self.graphs_hist_density_check.setChecked(False)
        self.graphs_hist_cumulative_check = QCheckBox("Cumulative")
        self.graphs_hist_cumulative_check.setChecked(False)
        self.graphs_hist_log_y_check = QCheckBox("Log Y")
        self.graphs_hist_log_y_check.setChecked(False)
        self.graphs_hist_color_mode_combo = QComboBox()
        self.graphs_hist_color_mode_combo.addItems(["Per metric palette", "Single color"])
        self.graphs_hist_palette_combo = QComboBox()
        self.graphs_hist_palette_combo.addItems(["tab20", "Set2", "Accent", "viridis", "plasma"])
        self.graphs_hist_color_edit = QLineEdit("#4C78A8")
        self.graphs_hist_color_edit.setMaximumWidth(95)
        controls_row.addWidget(QLabel("Mode:"))
        controls_row.addWidget(self.graphs_hist_mode_combo)
        controls_row.addWidget(QLabel("Bins:"))
        controls_row.addWidget(self.graphs_hist_bins_spin)
        controls_row.addWidget(QLabel("Alpha:"))
        controls_row.addWidget(self.graphs_hist_alpha_spin)
        controls_row.addWidget(self.graphs_hist_density_check)
        controls_row.addWidget(self.graphs_hist_cumulative_check)
        controls_row.addWidget(self.graphs_hist_log_y_check)
        controls_row.addWidget(QLabel("Colors:"))
        controls_row.addWidget(self.graphs_hist_palette_combo)
        controls_row.addWidget(self.graphs_hist_color_mode_combo)
        controls_row.addWidget(self.graphs_hist_color_edit)
        controls_row.addStretch(1)

        export_row = QHBoxLayout()
        self.graphs_hist_title_edit = QLineEdit()
        self.graphs_hist_title_edit.setPlaceholderText("Title (auto)")
        self.graphs_hist_format_combo = QComboBox()
        self.graphs_hist_format_combo.addItems(["PNG", "SVG", "PDF"])
        self.graphs_hist_dpi_spin = QSpinBox()
        self.graphs_hist_dpi_spin.setRange(72, 600)
        self.graphs_hist_dpi_spin.setValue(200)
        self.graphs_hist_dpi_spin.setSuffix(" dpi")
        self.graphs_hist_save_button = QPushButton("Save plot")
        self.graphs_hist_open_folder_button = QPushButton("Open output folder")
        export_row.addWidget(QLabel("Title:"))
        export_row.addWidget(self.graphs_hist_title_edit, 1)
        export_row.addWidget(QLabel("Format:"))
        export_row.addWidget(self.graphs_hist_format_combo)
        export_row.addWidget(self.graphs_hist_dpi_spin)
        export_row.addWidget(self.graphs_hist_save_button)
        export_row.addWidget(self.graphs_hist_open_folder_button)

        self.graphs_hist_figure, self.graphs_hist_ax = plt.subplots(1, 1, figsize=(10.0, 6.0))
        self.graphs_hist_canvas = FigureCanvas(self.graphs_hist_figure)
        self.graphs_hist_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.graphs_hist_refresh_button.clicked.connect(self._refresh_graphs_histogram)
        self.graphs_hist_use_manual_fix_check.toggled.connect(
            lambda _checked: self._refresh_graphs_histogram()
        )
        for check in self.graphs_hist_metric_checks.values():
            check.toggled.connect(lambda _checked: self._refresh_graphs_histogram())
        self.graphs_hist_metrics_select_all_button.clicked.connect(
            lambda: self._set_graphs_hist_metric_checks(True)
        )
        self.graphs_hist_metrics_clear_all_button.clicked.connect(
            lambda: self._set_graphs_hist_metric_checks(False)
        )
        self.graphs_hist_mode_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_histogram()
        )
        self.graphs_hist_bins_spin.valueChanged.connect(
            lambda _value: self._refresh_graphs_histogram()
        )
        self.graphs_hist_alpha_spin.valueChanged.connect(
            lambda _value: self._refresh_graphs_histogram()
        )
        self.graphs_hist_density_check.toggled.connect(
            lambda _checked: self._refresh_graphs_histogram()
        )
        self.graphs_hist_cumulative_check.toggled.connect(
            lambda _checked: self._refresh_graphs_histogram()
        )
        self.graphs_hist_log_y_check.toggled.connect(
            lambda _checked: self._refresh_graphs_histogram()
        )
        self.graphs_hist_color_mode_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_histogram()
        )
        self.graphs_hist_palette_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_histogram()
        )
        self.graphs_hist_color_edit.editingFinished.connect(self._refresh_graphs_histogram)
        self.graphs_hist_title_edit.editingFinished.connect(self._refresh_graphs_histogram)
        self.graphs_hist_save_button.clicked.connect(self._save_graphs_histogram)
        self.graphs_hist_open_folder_button.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(
                    str(Path(self.base_path_edit.text().strip()) / "output" / "analyzer")
                )
            )
        )

        layout.addLayout(top_row)
        layout.addLayout(metrics_row)
        layout.addLayout(controls_row)
        layout.addLayout(export_row)
        layout.addWidget(self.graphs_hist_canvas, 1)

        self._refresh_graphs_histogram()
        return tab

    def _selected_graphs_hist_metrics(self, available_columns: list[str]) -> list[str]:
        return [
            metric_name
            for metric_name, check in self.graphs_hist_metric_checks.items()
            if check.isChecked() and metric_name in available_columns
        ]

    def _set_graphs_hist_metric_checks(self, checked: bool) -> None:
        for _metric_name, check in self.graphs_hist_metric_checks.items():
            if not check.isEnabled():
                continue
            check.blockSignals(True)
            check.setChecked(checked)
            check.blockSignals(False)
        self._refresh_graphs_histogram()

    def _save_graphs_histogram(self) -> None:
        output_dir = Path(self.base_path_edit.text().strip()) / "output" / "analyzer"
        output_dir.mkdir(parents=True, exist_ok=True)
        mode_text = self.graphs_hist_mode_combo.currentText().strip().lower() or "overlay"
        fmt = self.graphs_hist_format_combo.currentText().strip().lower() or "png"
        mode_prefix = "fix_" if self.graphs_hist_use_manual_fix_check.isChecked() else ""
        out_path = output_dir / f"{mode_prefix}cross_histogram_{mode_text}.{fmt}"
        save_kwargs = {"dpi": int(self.graphs_hist_dpi_spin.value())} if fmt == "png" else {}
        self.graphs_hist_figure.savefig(out_path, **save_kwargs)
        self.statusBar().showMessage(f"Saved: {out_path}", 5000)

    def _refresh_graphs_histogram(self) -> None:
        source_df = self._load_analyzer_metrics_csv(
            "cone_summary.csv",
            "Histogram",
            use_manual_fix=self.graphs_hist_use_manual_fix_check.isChecked(),
            show_error=False,
        )
        if source_df is None:
            source_df = pd.DataFrame()

        ax = self.graphs_hist_ax
        ax.clear()

        metrics_df = self._extract_cone_metric_plot_columns(source_df)
        available_columns = [
            column for column in metrics_df.columns if metrics_df[column].notna().any()
        ]
        for metric_name, check in self.graphs_hist_metric_checks.items():
            check.setEnabled(metric_name in available_columns)
        selected_columns = self._selected_graphs_hist_metrics(available_columns)

        output_dir = Path(self.base_path_edit.text().strip()) / "output" / "analyzer"
        output_dir.mkdir(parents=True, exist_ok=True)
        mode_text = self.graphs_hist_mode_combo.currentText().strip().lower() or "overlay"
        graph_name = (
            f"fix_cross_histogram_{mode_text}.png"
            if self.graphs_hist_use_manual_fix_check.isChecked()
            else f"cross_histogram_{mode_text}.png"
        )
        graph_path = output_dir / graph_name

        if len(selected_columns) < 1:
            ax.text(
                0.5,
                0.5,
                "Select at least one metric",
                ha="center",
                va="center",
            )
            ax.set_axis_off()
        else:
            data_arrays: list[np.ndarray] = []
            labels: list[str] = []
            for column_name in selected_columns:
                vals = (
                    pd.to_numeric(metrics_df[column_name], errors="coerce")
                    .dropna()
                    .to_numpy(dtype=float)
                )
                if vals.size > 0:
                    data_arrays.append(vals)
                    labels.append(column_name)

            if not data_arrays:
                ax.text(
                    0.5,
                    0.5,
                    "No numeric values for selected metrics",
                    ha="center",
                    va="center",
                )
                ax.set_axis_off()
            else:
                bins = int(self.graphs_hist_bins_spin.value())
                alpha = float(self.graphs_hist_alpha_spin.value())
                density = self.graphs_hist_density_check.isChecked()
                cumulative = self.graphs_hist_cumulative_check.isChecked()
                mode_is_stacked = mode_text.startswith("stack")
                color_mode = self.graphs_hist_color_mode_combo.currentText().strip().lower()
                base_color = self.graphs_hist_color_edit.text().strip() or "#4C78A8"
                palette_name = self.graphs_hist_palette_combo.currentText().strip() or "tab20"
                palette = plt.cm.get_cmap(palette_name, len(data_arrays))
                colors = [
                    palette(i) if color_mode.startswith("per") else base_color
                    for i in range(len(data_arrays))
                ]

                if mode_is_stacked and len(data_arrays) > 1:
                    ax.hist(
                        data_arrays,
                        bins=bins,
                        alpha=alpha,
                        stacked=True,
                        density=density,
                        cumulative=cumulative,
                        color=colors,
                        label=labels,
                        edgecolor="black",
                        linewidth=0.4,
                    )
                else:
                    for idx, vals in enumerate(data_arrays):
                        ax.hist(
                            vals,
                            bins=bins,
                            alpha=alpha,
                            density=density,
                            cumulative=cumulative,
                            color=colors[idx],
                            label=labels[idx],
                            edgecolor="black",
                            linewidth=0.4,
                        )

                if self.graphs_hist_log_y_check.isChecked():
                    try:
                        ax.set_yscale("log")
                    except Exception:  # pylint: disable=broad-exception-caught
                        pass

                custom_title = self.graphs_hist_title_edit.text().strip()
                if custom_title:
                    ax.set_title(custom_title)
                else:
                    default_title = "Histogram"
                    if mode_is_stacked:
                        default_title += " (stacked)"
                    if cumulative:
                        default_title += " cumulative"
                    ax.set_title(default_title)
                ax.set_xlabel("Value")
                ax.set_ylabel("Density" if density else "Count")
                ax.grid(True, alpha=0.22)
                if labels:
                    ax.legend(loc="best", fontsize=8)

        self.graphs_hist_figure.tight_layout()
        self.graphs_hist_figure.savefig(graph_path, dpi=int(self.graphs_hist_dpi_spin.value()))

        source_name = (
            "fix_cone_summary.csv"
            if self.graphs_hist_use_manual_fix_check.isChecked()
            else "cone_summary.csv"
        )
        shown_metrics = selected_columns if selected_columns else available_columns
        metrics_preview = ", ".join(shown_metrics[:5])
        if len(shown_metrics) > 5:
            metrics_preview += ", ..."
        self.graphs_hist_source_label.setText(
            f"Source: {output_dir / source_name} "
            f"| Mode: {self.graphs_hist_mode_combo.currentText()}"
            f" | Metrics: {metrics_preview} | Saved: {graph_path.name}"
        )
        self.graphs_hist_canvas.draw_idle()

    def _build_graphs_distribution2d_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        self.graphs_dist2d_use_manual_fix_check = QCheckBox("Use manual fix")
        self.graphs_dist2d_use_manual_fix_check.setChecked(self.use_manual_fix_check.isChecked())
        self.graphs_dist2d_refresh_button = QPushButton("Refresh")
        self.graphs_dist2d_source_label = QLabel("Source: -")
        self.graphs_dist2d_source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        top_row.addWidget(self.graphs_dist2d_use_manual_fix_check)
        top_row.addWidget(self.graphs_dist2d_refresh_button)
        top_row.addWidget(self.graphs_dist2d_source_label)
        top_row.addStretch(1)

        controls_row = QHBoxLayout()
        self.graphs_dist2d_x_combo = QComboBox()
        self.graphs_dist2d_x_combo.addItems(
            [
                "Wco",
                "Wcr",
                "H",
                "D",
                "avg_slope_deg",
                "H_WCO_ratio",
                "WCR_WCO_ratio",
                "volume",
            ]
        )
        self.graphs_dist2d_y_combo = QComboBox()
        self.graphs_dist2d_y_combo.addItems(
            [
                "D",
                "H",
                "Wcr",
                "Wco",
                "avg_slope_deg",
                "H_WCO_ratio",
                "WCR_WCO_ratio",
                "volume",
            ]
        )
        self.graphs_dist2d_bins_x_spin = QSpinBox()
        self.graphs_dist2d_bins_x_spin.setRange(5, 250)
        self.graphs_dist2d_bins_x_spin.setValue(30)
        self.graphs_dist2d_bins_y_spin = QSpinBox()
        self.graphs_dist2d_bins_y_spin.setRange(5, 250)
        self.graphs_dist2d_bins_y_spin.setValue(30)
        self.graphs_dist2d_cmap_combo = QComboBox()
        self.graphs_dist2d_cmap_combo.addItems(["viridis", "plasma", "magma", "cividis", "YlOrRd"])
        self.graphs_dist2d_log_density_check = QCheckBox("Log density")
        self.graphs_dist2d_log_density_check.setChecked(False)
        self.graphs_dist2d_show_points_check = QCheckBox("Show points")
        self.graphs_dist2d_show_points_check.setChecked(True)
        self.graphs_dist2d_alpha_spin = QDoubleSpinBox()
        self.graphs_dist2d_alpha_spin.setRange(0.05, 1.0)
        self.graphs_dist2d_alpha_spin.setSingleStep(0.05)
        self.graphs_dist2d_alpha_spin.setValue(0.25)
        controls_row.addWidget(QLabel("X:"))
        controls_row.addWidget(self.graphs_dist2d_x_combo)
        controls_row.addWidget(QLabel("Y:"))
        controls_row.addWidget(self.graphs_dist2d_y_combo)
        controls_row.addWidget(QLabel("Bins X:"))
        controls_row.addWidget(self.graphs_dist2d_bins_x_spin)
        controls_row.addWidget(QLabel("Bins Y:"))
        controls_row.addWidget(self.graphs_dist2d_bins_y_spin)
        controls_row.addWidget(QLabel("Cmap:"))
        controls_row.addWidget(self.graphs_dist2d_cmap_combo)
        controls_row.addWidget(self.graphs_dist2d_log_density_check)
        controls_row.addWidget(self.graphs_dist2d_show_points_check)
        controls_row.addWidget(QLabel("Point alpha:"))
        controls_row.addWidget(self.graphs_dist2d_alpha_spin)
        controls_row.addStretch(1)

        export_row = QHBoxLayout()
        self.graphs_dist2d_title_edit = QLineEdit()
        self.graphs_dist2d_title_edit.setPlaceholderText("Title (auto)")
        self.graphs_dist2d_format_combo = QComboBox()
        self.graphs_dist2d_format_combo.addItems(["PNG", "SVG", "PDF"])
        self.graphs_dist2d_dpi_spin = QSpinBox()
        self.graphs_dist2d_dpi_spin.setRange(72, 600)
        self.graphs_dist2d_dpi_spin.setValue(200)
        self.graphs_dist2d_dpi_spin.setSuffix(" dpi")
        self.graphs_dist2d_save_button = QPushButton("Save plot")
        self.graphs_dist2d_open_folder_button = QPushButton("Open output folder")
        export_row.addWidget(QLabel("Title:"))
        export_row.addWidget(self.graphs_dist2d_title_edit, 1)
        export_row.addWidget(QLabel("Format:"))
        export_row.addWidget(self.graphs_dist2d_format_combo)
        export_row.addWidget(self.graphs_dist2d_dpi_spin)
        export_row.addWidget(self.graphs_dist2d_save_button)
        export_row.addWidget(self.graphs_dist2d_open_folder_button)

        self.graphs_dist2d_figure, self.graphs_dist2d_ax = plt.subplots(1, 1, figsize=(10.0, 6.0))
        self.graphs_dist2d_canvas = FigureCanvas(self.graphs_dist2d_figure)
        self.graphs_dist2d_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.graphs_dist2d_colorbar = None

        self.graphs_dist2d_refresh_button.clicked.connect(self._refresh_graphs_distribution2d)
        self.graphs_dist2d_use_manual_fix_check.toggled.connect(
            lambda _checked: self._refresh_graphs_distribution2d()
        )
        self.graphs_dist2d_x_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_distribution2d()
        )
        self.graphs_dist2d_y_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_distribution2d()
        )
        self.graphs_dist2d_bins_x_spin.valueChanged.connect(
            lambda _value: self._refresh_graphs_distribution2d()
        )
        self.graphs_dist2d_bins_y_spin.valueChanged.connect(
            lambda _value: self._refresh_graphs_distribution2d()
        )
        self.graphs_dist2d_cmap_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_distribution2d()
        )
        self.graphs_dist2d_log_density_check.toggled.connect(
            lambda _checked: self._refresh_graphs_distribution2d()
        )
        self.graphs_dist2d_show_points_check.toggled.connect(
            lambda _checked: self._refresh_graphs_distribution2d()
        )
        self.graphs_dist2d_alpha_spin.valueChanged.connect(
            lambda _value: self._refresh_graphs_distribution2d()
        )
        self.graphs_dist2d_title_edit.editingFinished.connect(self._refresh_graphs_distribution2d)
        self.graphs_dist2d_save_button.clicked.connect(self._save_graphs_distribution2d)
        self.graphs_dist2d_open_folder_button.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(
                    str(Path(self.base_path_edit.text().strip()) / "output" / "analyzer")
                )
            )
        )

        layout.addLayout(top_row)
        layout.addLayout(controls_row)
        layout.addLayout(export_row)
        layout.addWidget(self.graphs_dist2d_canvas, 1)

        self._refresh_graphs_distribution2d()
        return tab

    def _save_graphs_distribution2d(self) -> None:
        output_dir = Path(self.base_path_edit.text().strip()) / "output" / "analyzer"
        output_dir.mkdir(parents=True, exist_ok=True)
        x_metric = self.graphs_dist2d_x_combo.currentText().strip() or "x"
        y_metric = self.graphs_dist2d_y_combo.currentText().strip() or "y"
        safe_x = re.sub(r"[^0-9A-Za-z_-]+", "_", x_metric).strip("_") or "x"
        safe_y = re.sub(r"[^0-9A-Za-z_-]+", "_", y_metric).strip("_") or "y"
        fmt = self.graphs_dist2d_format_combo.currentText().strip().lower() or "png"
        mode_prefix = "fix_" if self.graphs_dist2d_use_manual_fix_check.isChecked() else ""
        out_path = output_dir / f"{mode_prefix}cross_distribution2d_{safe_x}_vs_{safe_y}.{fmt}"
        save_kwargs = {"dpi": int(self.graphs_dist2d_dpi_spin.value())} if fmt == "png" else {}
        self.graphs_dist2d_figure.savefig(out_path, **save_kwargs)
        self.statusBar().showMessage(f"Saved: {out_path}", 5000)

    def _refresh_graphs_distribution2d(self) -> None:
        source_df = self._load_analyzer_metrics_csv(
            "cone_summary.csv",
            "2D Distribution",
            use_manual_fix=self.graphs_dist2d_use_manual_fix_check.isChecked(),
            show_error=False,
        )
        if source_df is None:
            source_df = pd.DataFrame()

        ax = self.graphs_dist2d_ax
        if self.graphs_dist2d_colorbar is not None:
            try:
                self.graphs_dist2d_colorbar.remove()
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            self.graphs_dist2d_colorbar = None
        ax.clear()

        metrics_df = self._extract_cone_metric_plot_columns(source_df)
        available_columns = [
            column for column in metrics_df.columns if metrics_df[column].notna().any()
        ]

        x_metric = self.graphs_dist2d_x_combo.currentText().strip()
        y_metric = self.graphs_dist2d_y_combo.currentText().strip()
        if x_metric not in available_columns and available_columns:
            x_metric = available_columns[0]
            self.graphs_dist2d_x_combo.blockSignals(True)
            self.graphs_dist2d_x_combo.setCurrentText(x_metric)
            self.graphs_dist2d_x_combo.blockSignals(False)
        if y_metric not in available_columns and available_columns:
            y_metric = available_columns[min(1, len(available_columns) - 1)]
            self.graphs_dist2d_y_combo.blockSignals(True)
            self.graphs_dist2d_y_combo.setCurrentText(y_metric)
            self.graphs_dist2d_y_combo.blockSignals(False)

        output_dir = Path(self.base_path_edit.text().strip()) / "output" / "analyzer"
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_x = re.sub(r"[^0-9A-Za-z_-]+", "_", x_metric).strip("_") or "x"
        safe_y = re.sub(r"[^0-9A-Za-z_-]+", "_", y_metric).strip("_") or "y"
        graph_name = (
            f"fix_cross_distribution2d_{safe_x}_vs_{safe_y}.png"
            if self.graphs_dist2d_use_manual_fix_check.isChecked()
            else f"cross_distribution2d_{safe_x}_vs_{safe_y}.png"
        )
        graph_path = output_dir / graph_name

        if (
            (not available_columns)
            or (x_metric not in metrics_df.columns)
            or (y_metric not in metrics_df.columns)
        ):
            ax.text(
                0.5,
                0.5,
                "No valid metrics for 2D distribution",
                ha="center",
                va="center",
            )
            ax.set_axis_off()
        else:
            work = pd.DataFrame(
                {
                    "x": pd.to_numeric(metrics_df[x_metric], errors="coerce"),
                    "y": pd.to_numeric(metrics_df[y_metric], errors="coerce"),
                }
            ).dropna()

            if work.empty:
                ax.text(0.5, 0.5, "No numeric X/Y values", ha="center", va="center")
                ax.set_axis_off()
            else:
                bins_x = int(self.graphs_dist2d_bins_x_spin.value())
                bins_y = int(self.graphs_dist2d_bins_y_spin.value())
                cmap_name = self.graphs_dist2d_cmap_combo.currentText().strip() or "viridis"
                log_density = self.graphs_dist2d_log_density_check.isChecked()
                h_vals, xedges, yedges = np.histogram2d(
                    work["x"].to_numpy(dtype=float),
                    work["y"].to_numpy(dtype=float),
                    bins=(bins_x, bins_y),
                )
                h_plot = h_vals.T
                if log_density:
                    h_plot = np.log1p(h_plot)

                image = ax.imshow(
                    h_plot,
                    origin="lower",
                    aspect="auto",
                    extent=[xedges[0], xedges[-1], yedges[0], yedges[-1]],
                    cmap=cmap_name,
                )
                self.graphs_dist2d_colorbar = self.graphs_dist2d_figure.colorbar(
                    image,
                    ax=ax,
                    fraction=0.046,
                    pad=0.04,
                )
                self.graphs_dist2d_colorbar.set_label("log1p(count)" if log_density else "count")

                if self.graphs_dist2d_show_points_check.isChecked():
                    ax.scatter(
                        work["x"],
                        work["y"],
                        s=12,
                        alpha=float(self.graphs_dist2d_alpha_spin.value()),
                        color="white",
                        edgecolors="none",
                    )

                custom_title = self.graphs_dist2d_title_edit.text().strip()
                ax.set_title(
                    custom_title
                    if custom_title
                    else f"2D distribution: {x_metric} vs {y_metric}"
                )
                ax.set_xlabel(x_metric)
                ax.set_ylabel(y_metric)
                ax.grid(True, alpha=0.18)

        self.graphs_dist2d_figure.tight_layout()
        self.graphs_dist2d_figure.savefig(graph_path, dpi=int(self.graphs_dist2d_dpi_spin.value()))

        source_name = (
            "fix_cone_summary.csv"
            if self.graphs_dist2d_use_manual_fix_check.isChecked()
            else "cone_summary.csv"
        )
        self.graphs_dist2d_source_label.setText(
            f"Source: {output_dir / source_name} "
            f"| X: {x_metric} | Y: {y_metric} | Saved: {graph_path.name}"
        )
        self.graphs_dist2d_canvas.draw_idle()

    def _apply_graphs_boxplot_preset(self, preset_name: str) -> None:
        if preset_name == "Custom":
            self._refresh_graphs_boxplot()
            return

        updates = {
            "Classic blue": {
                "palette": "tab20",
                "mode": "Single color",
                "color": "#4C78A8",
                "edge": "solid",
                "fill": True,
            },
            "Earth tones": {
                "palette": "Accent",
                "mode": "Per metric palette",
                "color": "#8C6D31",
                "edge": "solid",
                "fill": True,
            },
            "High contrast": {
                "palette": "plasma",
                "mode": "Per metric palette",
                "color": "#1F1F1F",
                "edge": "dashed",
                "fill": True,
            },
            "Pastel": {
                "palette": "Set2",
                "mode": "Per metric palette",
                "color": "#76B7B2",
                "edge": "dotted",
                "fill": True,
            },
        }
        config = updates.get(preset_name)
        if not config:
            self._refresh_graphs_boxplot()
            return

        for widget in [
            self.graphs_box_palette_combo,
            self.graphs_box_color_mode_combo,
            self.graphs_box_edge_style_combo,
            self.graphs_box_fill_check,
        ]:
            widget.blockSignals(True)

        self.graphs_box_palette_combo.setCurrentText(str(config["palette"]))
        self.graphs_box_color_mode_combo.setCurrentText(str(config["mode"]))
        self.graphs_box_color_edit.setText(str(config["color"]))
        self.graphs_box_edge_style_combo.setCurrentText(str(config["edge"]))
        self.graphs_box_fill_check.setChecked(bool(config["fill"]))

        for widget in [
            self.graphs_box_palette_combo,
            self.graphs_box_color_mode_combo,
            self.graphs_box_edge_style_combo,
            self.graphs_box_fill_check,
        ]:
            widget.blockSignals(False)

        self._refresh_graphs_boxplot()

    def _save_graphs_boxplot(self) -> None:
        output_dir = Path(self.base_path_edit.text().strip()) / "output" / "analyzer"
        output_dir.mkdir(parents=True, exist_ok=True)

        kind_text = self.graphs_box_kind_combo.currentText().strip().lower() or "boxplot"
        orient_text = (
            "h"
            if self.graphs_box_orientation_combo.currentText().strip().lower().startswith("h")
            else "v"
        )
        fmt = self.graphs_box_format_combo.currentText().strip().lower() or "png"
        mode_prefix = "fix_" if self.graphs_box_use_manual_fix_check.isChecked() else ""
        out_path = output_dir / f"{mode_prefix}cross_boxplot_{kind_text}_{orient_text}.{fmt}"

        save_kwargs = {"dpi": int(self.graphs_box_dpi_spin.value())} if fmt == "png" else {}
        self.graphs_box_figure.savefig(out_path, **save_kwargs)
        self.statusBar().showMessage(f"Saved: {out_path}", 5000)

    def _selected_graphs_boxplot_metrics(self, available_columns: list[str]) -> list[str]:
        selected_metrics: list[str] = []
        for metric_name, check in self.graphs_box_metric_checks.items():
            if check.isChecked() and metric_name in available_columns:
                selected_metrics.append(metric_name)
        return selected_metrics

    def _set_graphs_box_metric_checks(self, checked: bool) -> None:
        for check in self.graphs_box_metric_checks.values():
            if not check.isEnabled():
                continue
            check.blockSignals(True)
            check.setChecked(checked)
            check.blockSignals(False)
        self._refresh_graphs_boxplot()

    def _refresh_graphs_boxplot(self) -> None:
        source_df = self._load_analyzer_metrics_csv(
            "cone_summary.csv",
            "Boxplot",
            use_manual_fix=self.graphs_box_use_manual_fix_check.isChecked(),
            show_error=False,
        )
        if source_df is None:
            source_df = pd.DataFrame()

        ax = self.graphs_box_ax
        ax.clear()

        metrics_df = self._extract_cone_metric_plot_columns(source_df)
        available_columns = [
            column for column in metrics_df.columns if metrics_df[column].notna().any()
        ]
        for metric_name, check in self.graphs_box_metric_checks.items():
            check.setEnabled(metric_name in available_columns)
        selected_columns = self._selected_graphs_boxplot_metrics(available_columns)

        output_dir = Path(self.base_path_edit.text().strip()) / "output" / "analyzer"
        output_dir.mkdir(parents=True, exist_ok=True)
        kind_text = self.graphs_box_kind_combo.currentText().strip().lower() or "boxplot"
        orient_text = (
            "h"
            if self.graphs_box_orientation_combo.currentText().strip().lower().startswith("h")
            else "v"
        )
        graph_name = (
            f"fix_cross_boxplot_{kind_text}_{orient_text}.png"
            if self.graphs_box_use_manual_fix_check.isChecked()
            else f"cross_boxplot_{kind_text}_{orient_text}.png"
        )
        graph_path = output_dir / graph_name
        log_requested = self.graphs_box_log_value_axis_check.isChecked()
        log_applied = False
        log_warning = ""

        if not selected_columns:
            ax.text(
                0.5,
                0.5,
                "No valid metrics selected\n(check at least one available metric)",
                ha="center",
                va="center",
            )
            ax.set_axis_off()
        else:
            data_arrays: list[np.ndarray] = []
            labels: list[str] = []
            for column_name in selected_columns:
                vals = (
                    pd.to_numeric(metrics_df[column_name], errors="coerce")
                    .dropna()
                    .to_numpy(dtype=float)
                )
                if vals.size > 0:
                    data_arrays.append(vals)
                    labels.append(column_name)

            if not data_arrays:
                ax.text(
                    0.5,
                    0.5,
                    "No numeric values for selected metrics",
                    ha="center",
                    va="center",
                )
                ax.set_axis_off()
            else:
                is_vertical = orient_text == "v"
                fill_enabled = self.graphs_box_fill_check.isChecked()
                color_mode = self.graphs_box_color_mode_combo.currentText().strip().lower()
                base_color = self.graphs_box_color_edit.text().strip() or "#4C78A8"
                edge_style = self.graphs_box_edge_style_combo.currentText().strip() or "solid"
                edge_width = float(self.graphs_box_edge_width_spin.value())
                show_means = self.graphs_box_show_means_check.isChecked()
                palette_name = self.graphs_box_palette_combo.currentText().strip() or "tab20"
                palette = plt.cm.get_cmap(palette_name, len(data_arrays))

                if kind_text.startswith("violin"):
                    violin = ax.violinplot(
                        data_arrays,
                        vert=is_vertical,
                        showmeans=show_means,
                        showmedians=True,
                    )
                    for idx, body in enumerate(violin.get("bodies", [])):
                        color = palette(idx) if color_mode.startswith("per") else base_color
                        body.set_facecolor(color)
                        body.set_alpha(0.7 if fill_enabled else 0.06)
                        body.set_edgecolor("black")
                        body.set_linewidth(edge_width)
                        body.set_linestyle(edge_style)

                    for artist_name in ["cbars", "cmins", "cmaxes", "cmedians", "cmeans"]:
                        artist = violin.get(artist_name)
                        if artist is None:
                            continue
                        artist.set_color("black")
                        artist.set_linewidth(edge_width)
                        artist.set_linestyle(edge_style)
                    default_title = "Metric distribution (violin)"
                else:
                    box = ax.boxplot(
                        data_arrays,
                        vert=is_vertical,
                        patch_artist=fill_enabled,
                        labels=labels,
                        showmeans=show_means,
                    )
                    for idx, patch in enumerate(box.get("boxes", [])):
                        color = palette(idx) if color_mode.startswith("per") else base_color
                        if fill_enabled:
                            patch.set_facecolor(color)
                            patch.set_alpha(0.72)
                        patch.set_edgecolor("black")
                        patch.set_linewidth(edge_width)
                        patch.set_linestyle(edge_style)

                    for line_group in ["whiskers", "caps", "medians", "means"]:
                        for line in box.get(line_group, []):
                            line.set_color("black")
                            line.set_linewidth(edge_width)
                            line.set_linestyle(edge_style if line_group != "medians" else "solid")
                    default_title = "Metric distribution (boxplot)"

                custom_title = self.graphs_box_title_edit.text().strip()
                ax.set_title(custom_title if custom_title else default_title)

                all_values = np.concatenate(data_arrays) if data_arrays else np.asarray([])
                has_non_positive = bool(np.any(all_values <= 0.0)) if all_values.size else False
                if log_requested and (not has_non_positive):
                    if is_vertical:
                        ax.set_yscale("log")
                    else:
                        ax.set_xscale("log")
                    log_applied = True
                elif log_requested and has_non_positive:
                    log_warning = " (log unavailable: non-positive values)"

                positions = np.arange(1, len(labels) + 1)
                if is_vertical:
                    ax.set_xticks(positions)
                    ax.set_xticklabels(labels, rotation=30, ha="right")
                    ax.set_xlabel("Metric")
                    ax.set_ylabel("Value")
                    ax.yaxis.grid(True, alpha=0.25)
                else:
                    ax.set_yticks(positions)
                    ax.set_yticklabels(labels)
                    ax.set_ylabel("Metric")
                    ax.set_xlabel("Value")
                    ax.xaxis.grid(True, alpha=0.25)

        self.graphs_box_figure.tight_layout()
        self.graphs_box_figure.savefig(graph_path, dpi=int(self.graphs_box_dpi_spin.value()))

        source_name = (
            "fix_cone_summary.csv"
            if self.graphs_box_use_manual_fix_check.isChecked()
            else "cone_summary.csv"
        )
        shown_metrics = selected_columns if selected_columns else available_columns
        metrics_preview = ", ".join(shown_metrics[:5])
        if len(shown_metrics) > 5:
            metrics_preview += ", ..."
        scale_text = "log" if log_applied else "linear"
        if log_requested and not log_applied:
            scale_text += log_warning
        self.graphs_box_source_label.setText(
            f"Source: {output_dir / source_name} | Type: {self.graphs_box_kind_combo.currentText()}"
            f" | Scale: {scale_text} | Metrics: {metrics_preview} | Saved: {graph_path.name}"
        )
        self.graphs_box_canvas.draw_idle()

    def _build_graphs_scatters_tab2(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        self.graphs_custom_multi_use_manual_fix_check = QCheckBox("Use manual fix")
        self.graphs_custom_multi_use_manual_fix_check.setChecked(
            self.use_manual_fix_check.isChecked()
        )
        self.graphs_custom_multi_refresh_button = QPushButton("Refresh")
        self.graphs_custom_multi_source_label = QLabel("Source: -")
        self.graphs_custom_multi_source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        top_row.addWidget(self.graphs_custom_multi_use_manual_fix_check)
        top_row.addWidget(self.graphs_custom_multi_refresh_button)
        top_row.addWidget(self.graphs_custom_multi_source_label)
        top_row.addStretch(1)

        controls_row = QHBoxLayout()
        self.graphs_custom_multi_a_combo = QComboBox()
        self.graphs_custom_multi_a_combo.addItems(
            ["Scatter", "Correlation", "Histogram", "2D Distribution", "Boxplot"]
        )
        self.graphs_custom_multi_b_combo = QComboBox()
        self.graphs_custom_multi_b_combo.addItems(
            ["Histogram", "Scatter", "Correlation", "2D Distribution", "Boxplot"]
        )
        self.graphs_custom_multi_layout_combo = QComboBox()
        self.graphs_custom_multi_layout_combo.addItems(["Horizontal", "Vertical"])
        self.graphs_custom_multi_show_titles_check = QCheckBox("Show panel titles")
        self.graphs_custom_multi_show_titles_check.setChecked(True)
        controls_row.addWidget(QLabel("Plot A:"))
        controls_row.addWidget(self.graphs_custom_multi_a_combo)
        controls_row.addWidget(QLabel("Plot B:"))
        controls_row.addWidget(self.graphs_custom_multi_b_combo)
        controls_row.addWidget(QLabel("Layout:"))
        controls_row.addWidget(self.graphs_custom_multi_layout_combo)
        controls_row.addWidget(self.graphs_custom_multi_show_titles_check)
        controls_row.addStretch(1)

        export_row = QHBoxLayout()
        self.graphs_custom_multi_format_combo = QComboBox()
        self.graphs_custom_multi_format_combo.addItems(["PNG", "SVG", "PDF"])
        self.graphs_custom_multi_dpi_spin = QSpinBox()
        self.graphs_custom_multi_dpi_spin.setRange(72, 600)
        self.graphs_custom_multi_dpi_spin.setValue(200)
        self.graphs_custom_multi_dpi_spin.setSuffix(" dpi")
        self.graphs_custom_multi_save_button = QPushButton("Save plot")
        self.graphs_custom_multi_open_folder_button = QPushButton("Open output folder")
        export_row.addWidget(QLabel("Format:"))
        export_row.addWidget(self.graphs_custom_multi_format_combo)
        export_row.addWidget(self.graphs_custom_multi_dpi_spin)
        export_row.addWidget(self.graphs_custom_multi_save_button)
        export_row.addWidget(self.graphs_custom_multi_open_folder_button)
        export_row.addStretch(1)

        self.graphs_custom_multi_figure = plt.figure(figsize=(11.8, 6.4))
        self.graphs_custom_multi_canvas = FigureCanvas(self.graphs_custom_multi_figure)
        self.graphs_custom_multi_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.graphs_custom_multi_refresh_button.clicked.connect(
            self._refresh_graphs_scatters_tab2
        )
        self.graphs_custom_multi_use_manual_fix_check.toggled.connect(
            lambda _checked: self._refresh_graphs_scatters_tab2()
        )
        self.graphs_custom_multi_a_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_scatters_tab2()
        )
        self.graphs_custom_multi_b_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_scatters_tab2()
        )
        self.graphs_custom_multi_layout_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_scatters_tab2()
        )
        self.graphs_custom_multi_show_titles_check.toggled.connect(
            lambda _checked: self._refresh_graphs_scatters_tab2()
        )
        self.graphs_custom_multi_save_button.clicked.connect(self._save_graphs_custom_multi)
        self.graphs_custom_multi_open_folder_button.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(
                    str(Path(self.base_path_edit.text().strip()) / "output" / "analyzer")
                )
            )
        )

        layout.addLayout(top_row)
        layout.addLayout(controls_row)
        layout.addLayout(export_row)
        layout.addWidget(self.graphs_custom_multi_canvas, 1)

        self._refresh_graphs_scatters_tab2()
        return tab

    def _latest_graphs_output_for_kind(self, kind_name: str, use_manual_fix: bool) -> Path | None:
        output_dir = Path(self.base_path_edit.text().strip()) / "output" / "analyzer"
        mode_prefix = "fix_" if use_manual_fix else ""
        kind_patterns = {
            "Scatter": [
                f"{mode_prefix}scatter_*.png",
                f"{mode_prefix}cross_scatters_tab1.png",
            ],
            "Correlation": [f"{mode_prefix}cross_metrics_correlation_*.png"],
            "Histogram": [f"{mode_prefix}cross_histogram_*.png"],
            "2D Distribution": [f"{mode_prefix}cross_distribution2d_*.png"],
            "Boxplot": [f"{mode_prefix}cross_boxplot_*.png"],
        }
        patterns = kind_patterns.get(kind_name)
        if not patterns:
            return None
        matches: list[Path] = []
        for pattern in patterns:
            matches.extend(output_dir.glob(pattern))
        matches = sorted(matches, key=lambda path: path.stat().st_mtime)
        return matches[-1] if matches else None

    def _save_graphs_custom_multi(self) -> None:
        output_dir = Path(self.base_path_edit.text().strip()) / "output" / "analyzer"
        output_dir.mkdir(parents=True, exist_ok=True)
        layout_text = (
            self.graphs_custom_multi_layout_combo.currentText().strip().lower()
            or "horizontal"
        )
        fmt = self.graphs_custom_multi_format_combo.currentText().strip().lower() or "png"
        mode_prefix = "fix_" if self.graphs_custom_multi_use_manual_fix_check.isChecked() else ""
        out_path = output_dir / f"{mode_prefix}cross_custom_multi_{layout_text}.{fmt}"
        save_kwargs = (
            {"dpi": int(self.graphs_custom_multi_dpi_spin.value())}
            if fmt == "png"
            else {}
        )
        self.graphs_custom_multi_figure.savefig(out_path, **save_kwargs)
        self.statusBar().showMessage(f"Saved: {out_path}", 5000)

    def _refresh_graphs_scatters_tab1(self) -> None:
        if not hasattr(self, "graphs_scatters_axes1"):
            return
        source_df = self._load_analyzer_metrics_csv(
            "cone_summary.csv",
            "Scatters",
            use_manual_fix=self.graphs_scatters1_use_manual_fix_check.isChecked(),
            show_error=False,
        )
        if source_df is None:
            source_df = pd.DataFrame()

        ax1a, ax1b = self.graphs_scatters_axes1

        if self.graphs_scatters_hist_colorbar1 is not None:
            self.graphs_scatters_hist_colorbar1.remove()
            self.graphs_scatters_hist_colorbar1 = None

        ax1a.clear()
        ax1b.clear()

        metrics_df = self._extract_cone_metric_plot_columns(source_df)

        plot_df = pd.DataFrame(
            {
                "H": self._safe_numeric_series(metrics_df, "H", source_df.index),
                "D": self._safe_numeric_series(metrics_df, "D", source_df.index),
            }
        ).dropna()

        if plot_df.empty:
            ax1a.text(0.5, 0.5, "No data", ha="center", va="center")
            ax1a.set_axis_off()
            ax1b.text(0.5, 0.5, "No data", ha="center", va="center")
            ax1b.set_axis_off()
        else:
            h, xedges, yedges = np.histogram2d(
                plot_df["H"],
                plot_df["D"],
                bins=15,
                range=[
                    [plot_df["H"].min(), plot_df["H"].max()],
                    [plot_df["D"].min(), plot_df["D"].max()],
                ],
            )
            extent = [xedges[0], xedges[-1], yedges[0], yedges[-1]]
            image = ax1a.imshow(
                h.T,
                origin="lower",
                extent=extent,
                aspect="auto",
                cmap="YlOrRd",
                interpolation="bilinear",
            )
            ax1a.set_xlabel("Height (H)")
            ax1a.set_ylabel("Depth (D)")
            ax1a.set_title("2D Distribution: H vs Depth")
            self.graphs_scatters_hist_colorbar1 = self.graphs_scatters_fig1.colorbar(image, ax=ax1a)
            self.graphs_scatters_hist_colorbar1.set_label("Count")

            ax1b.scatter(plot_df["H"], plot_df["D"], alpha=0.7, edgecolors="k", linewidths=0.5)
            if len(plot_df) >= 2:
                coeff = np.polyfit(plot_df["H"], plot_df["D"], deg=1)
                trend = np.poly1d(coeff)
                h_sorted = np.sort(plot_df["H"].to_numpy())
                ax1b.plot(h_sorted, trend(h_sorted), color="red", linewidth=2, label="Trend")
                ax1b.legend(loc="best")
            ax1b.set_xlabel("Height (H)")
            ax1b.set_ylabel("Depth (D)")
            ax1b.set_title("H vs Depth scatter")
            ax1b.grid(True, alpha=0.3)

        self.graphs_scatters_fig1.tight_layout()

        output_dir = Path(self.base_path_edit.text().strip()) / "output" / "analyzer"
        output_dir.mkdir(parents=True, exist_ok=True)
        tab1_name = (
            "fix_cross_scatters_tab1.png"
            if self.graphs_scatters1_use_manual_fix_check.isChecked()
            else "cross_scatters_tab1.png"
        )
        tab1_path = output_dir / tab1_name
        self.graphs_scatters_fig1.savefig(tab1_path, dpi=200)

        source_name = (
            "fix_cone_summary.csv"
            if self.graphs_scatters1_use_manual_fix_check.isChecked()
            else "cone_summary.csv"
        )
        self.graphs_scatters1_source_label.setText(
            f"Source: {output_dir / source_name} | Saved: {tab1_path.name}"
        )

        self.graphs_scatters_canvas1.draw_idle()

    def _refresh_graphs_scatters_tab2(self) -> None:
        if not hasattr(self, "graphs_custom_multi_figure"):
            return
        use_manual_fix = self.graphs_custom_multi_use_manual_fix_check.isChecked()
        kind_a = self.graphs_custom_multi_a_combo.currentText().strip()
        kind_b = self.graphs_custom_multi_b_combo.currentText().strip()
        layout_mode = self.graphs_custom_multi_layout_combo.currentText().strip().lower()
        is_vertical = layout_mode.startswith("v")
        show_titles = self.graphs_custom_multi_show_titles_check.isChecked()

        path_a = self._latest_graphs_output_for_kind(kind_a, use_manual_fix)
        path_b = self._latest_graphs_output_for_kind(kind_b, use_manual_fix)

        self.graphs_custom_multi_figure.clear()
        if is_vertical:
            axes = self.graphs_custom_multi_figure.subplots(2, 1)
        else:
            axes = self.graphs_custom_multi_figure.subplots(1, 2)
        if isinstance(axes, np.ndarray):
            flat_axes = list(axes.flatten())
        else:
            flat_axes = [axes]
            flat_axes.append(
                self.graphs_custom_multi_figure.add_subplot(
                    122 if not is_vertical else 212
                )
            )

        for ax, kind_name, image_path in [
            (flat_axes[0], kind_a, path_a),
            (flat_axes[1], kind_b, path_b),
        ]:
            ax.clear()
            if image_path is None or (not image_path.exists()):
                ax.text(
                    0.5,
                    0.5,
                    f"No saved plot found for {kind_name}\nGenerate it in its tab first",
                    ha="center",
                    va="center",
                )
                ax.set_axis_off()
                continue

            image = plt.imread(str(image_path))
            ax.imshow(image)
            ax.set_axis_off()
            if show_titles:
                ax.set_title(f"{kind_name} | {image_path.name}", fontsize=9)

        output_dir = Path(self.base_path_edit.text().strip()) / "output" / "analyzer"
        output_dir.mkdir(parents=True, exist_ok=True)
        layout_text = "vertical" if is_vertical else "horizontal"
        mode_prefix = "fix_" if use_manual_fix else ""
        auto_path = output_dir / f"{mode_prefix}cross_custom_multi_{layout_text}.png"
        self.graphs_custom_multi_figure.tight_layout()
        self.graphs_custom_multi_figure.savefig(
            auto_path,
            dpi=int(self.graphs_custom_multi_dpi_spin.value()),
        )

        source_name = "fix_cone_summary.csv" if use_manual_fix else "cone_summary.csv"
        a_name = path_a.name if path_a is not None else "missing"
        b_name = path_b.name if path_b is not None else "missing"
        self.graphs_custom_multi_source_label.setText(
            f"Source: {output_dir / source_name} "
            f"| A: {a_name} | B: {b_name} | Saved: {auto_path.name}"
        )
        self.graphs_custom_multi_canvas.draw_idle()

    # ------------------------------------------------------------------ #
    #  SCATTER — fully configurable scatter plot                          #
    # ------------------------------------------------------------------ #

    _SCATTER_METRIC_COLS: list[str] = [
        "height",
        "depth",
        "base_major_diameter (WCO)",
        "top_major_diameter (WCR)",
        "avg_slope_deg",
        "H_WCO_ratio",
        "WCR_WCO_ratio",
        "volume",
        "cone_id",
        "top_elev",
        "bottom_elev",
    ]

    def _build_graphs_scatter_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(4)

        # --- row 1: source controls ---
        row1 = QHBoxLayout()
        self.graphs_scatter_use_manual_fix_check = QCheckBox("Use manual fix")
        self.graphs_scatter_use_manual_fix_check.setChecked(
            self.use_manual_fix_check.isChecked()
        )
        self.graphs_scatter_refresh_button = QPushButton("Refresh")
        self.graphs_scatter_source_label = QLabel("Source: -")
        self.graphs_scatter_source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row1.addWidget(self.graphs_scatter_use_manual_fix_check)
        row1.addWidget(self.graphs_scatter_refresh_button)
        row1.addWidget(self.graphs_scatter_source_label)
        row1.addStretch(1)

        # --- row 2: axis + colour + size ---
        row2 = QHBoxLayout()
        self.graphs_scatter_x_combo = QComboBox()
        self.graphs_scatter_x_combo.setMinimumWidth(160)
        self.graphs_scatter_y_combo = QComboBox()
        self.graphs_scatter_y_combo.setMinimumWidth(160)
        self.graphs_scatter_color_combo = QComboBox()
        self.graphs_scatter_color_combo.setMinimumWidth(160)
        self.graphs_scatter_fixed_color_edit = QLineEdit("#4C78A8")
        self.graphs_scatter_fixed_color_edit.setMaximumWidth(76)
        self.graphs_scatter_fixed_color_edit.setPlaceholderText("#hex")
        self.graphs_scatter_cmap_combo = QComboBox()
        self.graphs_scatter_cmap_combo.addItems(
            ["viridis", "plasma", "inferno", "magma", "YlOrRd", "RdYlBu", "coolwarm", "cividis"]
        )
        self.graphs_scatter_size_combo = QComboBox()
        self.graphs_scatter_size_combo.setMinimumWidth(130)
        self.graphs_scatter_point_size_spin = QSpinBox()
        self.graphs_scatter_point_size_spin.setRange(5, 500)
        self.graphs_scatter_point_size_spin.setValue(50)
        self.graphs_scatter_point_size_spin.setSuffix(" pt")

        row2.addWidget(QLabel("X:"))
        row2.addWidget(self.graphs_scatter_x_combo)
        row2.addWidget(QLabel("Y:"))
        row2.addWidget(self.graphs_scatter_y_combo)
        row2.addWidget(QLabel("Color by:"))
        row2.addWidget(self.graphs_scatter_color_combo)
        row2.addWidget(QLabel("Hex:"))
        row2.addWidget(self.graphs_scatter_fixed_color_edit)
        row2.addWidget(QLabel("Cmap:"))
        row2.addWidget(self.graphs_scatter_cmap_combo)
        row2.addWidget(QLabel("Size by:"))
        row2.addWidget(self.graphs_scatter_size_combo)
        row2.addWidget(QLabel("Pt:"))
        row2.addWidget(self.graphs_scatter_point_size_spin)
        row2.addStretch(1)

        # --- row 3: style options ---
        row3 = QHBoxLayout()
        self.graphs_scatter_trend_check = QCheckBox("Trend line")
        self.graphs_scatter_trend_check.setChecked(True)
        self.graphs_scatter_log_x_check = QCheckBox("Log X")
        self.graphs_scatter_log_y_check = QCheckBox("Log Y")
        self.graphs_scatter_annotate_check = QCheckBox("Annotate top")
        self.graphs_scatter_annotate_n_spin = QSpinBox()
        self.graphs_scatter_annotate_n_spin.setRange(1, 20)
        self.graphs_scatter_annotate_n_spin.setValue(3)
        self.graphs_scatter_marker_combo = QComboBox()
        self.graphs_scatter_marker_combo.addItems(["o", "s", "^", "D", "P", "X", "+", "x"])
        self.graphs_scatter_alpha_spin = QDoubleSpinBox()
        self.graphs_scatter_alpha_spin.setRange(0.05, 1.0)
        self.graphs_scatter_alpha_spin.setSingleStep(0.05)
        self.graphs_scatter_alpha_spin.setValue(0.75)
        self.graphs_scatter_alpha_spin.setDecimals(2)

        row3.addWidget(self.graphs_scatter_trend_check)
        row3.addWidget(self.graphs_scatter_log_x_check)
        row3.addWidget(self.graphs_scatter_log_y_check)
        row3.addWidget(self.graphs_scatter_annotate_check)
        row3.addWidget(self.graphs_scatter_annotate_n_spin)
        row3.addWidget(QLabel("Marker:"))
        row3.addWidget(self.graphs_scatter_marker_combo)
        row3.addWidget(QLabel("Alpha:"))
        row3.addWidget(self.graphs_scatter_alpha_spin)
        row3.addStretch(1)

        # --- row 4: labels + export ---
        row4 = QHBoxLayout()
        self.graphs_scatter_title_edit = QLineEdit()
        self.graphs_scatter_title_edit.setPlaceholderText("Title (auto)")
        self.graphs_scatter_xlabel_edit = QLineEdit()
        self.graphs_scatter_xlabel_edit.setPlaceholderText("X label (auto)")
        self.graphs_scatter_ylabel_edit = QLineEdit()
        self.graphs_scatter_ylabel_edit.setPlaceholderText("Y label (auto)")
        self.graphs_scatter_format_combo = QComboBox()
        self.graphs_scatter_format_combo.addItems(["PNG", "SVG", "PDF"])
        self.graphs_scatter_dpi_spin = QSpinBox()
        self.graphs_scatter_dpi_spin.setRange(72, 600)
        self.graphs_scatter_dpi_spin.setValue(200)
        self.graphs_scatter_dpi_spin.setSuffix(" dpi")
        self.graphs_scatter_save_button = QPushButton("Save plot")

        self.graphs_scatter_open_folder_button = QPushButton("Open output folder")

        row4.addWidget(QLabel("Title:"))
        row4.addWidget(self.graphs_scatter_title_edit)
        row4.addWidget(QLabel("X label:"))
        row4.addWidget(self.graphs_scatter_xlabel_edit)
        row4.addWidget(QLabel("Y label:"))
        row4.addWidget(self.graphs_scatter_ylabel_edit)
        row4.addSpacing(8)
        row4.addWidget(QLabel("Format:"))
        row4.addWidget(self.graphs_scatter_format_combo)
        row4.addWidget(self.graphs_scatter_dpi_spin)
        row4.addWidget(self.graphs_scatter_save_button)
        row4.addWidget(self.graphs_scatter_open_folder_button)
        row4.addStretch(1)

        # --- figure ---
        self.graphs_scatter_figure, self.graphs_scatter_ax = plt.subplots(
            1, 1, figsize=(9.0, 5.5)
        )
        self.graphs_scatter_figure.subplots_adjust(left=0.10, right=0.96, top=0.93, bottom=0.12)
        self.graphs_scatter_colorbar = None
        self.graphs_scatter_canvas = FigureCanvas(self.graphs_scatter_figure)
        self.graphs_scatter_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # --- connections ---
        self.graphs_scatter_refresh_button.clicked.connect(self._refresh_graphs_scatter)
        self.graphs_scatter_use_manual_fix_check.toggled.connect(
            lambda _: self._refresh_graphs_scatter()
        )
        for _combo in [
            self.graphs_scatter_x_combo,
            self.graphs_scatter_y_combo,
            self.graphs_scatter_color_combo,
            self.graphs_scatter_cmap_combo,
            self.graphs_scatter_size_combo,
            self.graphs_scatter_marker_combo,
        ]:
            _combo.currentTextChanged.connect(lambda _: self._refresh_graphs_scatter())
        self.graphs_scatter_fixed_color_edit.editingFinished.connect(
            self._refresh_graphs_scatter
        )
        for _check in [
            self.graphs_scatter_trend_check,
            self.graphs_scatter_log_x_check,
            self.graphs_scatter_log_y_check,
            self.graphs_scatter_annotate_check,
        ]:
            _check.toggled.connect(lambda _: self._refresh_graphs_scatter())
        self.graphs_scatter_point_size_spin.valueChanged.connect(
            lambda _: self._refresh_graphs_scatter()
        )
        self.graphs_scatter_annotate_n_spin.valueChanged.connect(
            lambda _: self._refresh_graphs_scatter()
        )
        self.graphs_scatter_alpha_spin.valueChanged.connect(
            lambda _: self._refresh_graphs_scatter()
        )
        for _edit in [
            self.graphs_scatter_title_edit,
            self.graphs_scatter_xlabel_edit,
            self.graphs_scatter_ylabel_edit,
        ]:
            _edit.editingFinished.connect(self._refresh_graphs_scatter)
        self.graphs_scatter_save_button.clicked.connect(self._save_graphs_scatter)
        self.graphs_scatter_open_folder_button.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(
                    str(Path(self.base_path_edit.text().strip()) / "output" / "analyzer")
                )
            )
        )

        layout.addLayout(row1)
        layout.addLayout(row2)
        layout.addLayout(row3)
        layout.addLayout(row4)
        layout.addWidget(self.graphs_scatter_canvas, 1)

        self._populate_graphs_scatter_combos()
        self._refresh_graphs_scatter()
        return tab

    def _populate_graphs_scatter_combos(self) -> None:
        cols = self._SCATTER_METRIC_COLS
        color_items = ["Fixed color"] + cols
        size_items = ["Fixed size"] + cols

        for combo, items in [
            (self.graphs_scatter_x_combo, cols),
            (self.graphs_scatter_y_combo, cols),
            (self.graphs_scatter_color_combo, color_items),
            (self.graphs_scatter_size_combo, size_items),
        ]:
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(items)
            if current in items:
                combo.setCurrentText(current)
            combo.blockSignals(False)

        # sensible defaults
        if self.graphs_scatter_x_combo.currentText() == cols[0]:
            self.graphs_scatter_x_combo.setCurrentText("avg_slope_deg")
        if self.graphs_scatter_y_combo.currentText() == cols[0]:
            self.graphs_scatter_y_combo.setCurrentText("depth")

    def _refresh_graphs_scatter(self) -> None:
        ax = self.graphs_scatter_ax
        if self.graphs_scatter_colorbar is not None:
            try:
                self.graphs_scatter_colorbar.remove()
            except Exception:  # pylint: disable=broad-exception-caught
                pass
            self.graphs_scatter_colorbar = None
        ax.clear()

        source_df = self._load_analyzer_metrics_csv(
            "cone_summary.csv",
            "Scatter",
            use_manual_fix=self.graphs_scatter_use_manual_fix_check.isChecked(),
            show_error=False,
        )
        output_dir = Path(self.base_path_edit.text().strip()) / "output" / "analyzer"
        src_name = (
            "fix_cone_summary.csv"
            if self.graphs_scatter_use_manual_fix_check.isChecked()
            else "cone_summary.csv"
        )
        self.graphs_scatter_source_label.setText(f"Source: {output_dir / src_name}")

        if source_df is None or source_df.empty:
            ax.text(0.5, 0.5, "No data — run Analyzer first", ha="center", va="center")
            ax.set_axis_off()
            self.graphs_scatter_canvas.draw_idle()
            return

        x_col = self.graphs_scatter_x_combo.currentText().strip()
        y_col = self.graphs_scatter_y_combo.currentText().strip()
        color_by = self.graphs_scatter_color_combo.currentText().strip()
        size_by = self.graphs_scatter_size_combo.currentText().strip()
        point_size = self.graphs_scatter_point_size_spin.value()
        marker = self.graphs_scatter_marker_combo.currentText().strip() or "o"
        alpha = float(self.graphs_scatter_alpha_spin.value())
        show_trend = self.graphs_scatter_trend_check.isChecked()
        log_x = self.graphs_scatter_log_x_check.isChecked()
        log_y = self.graphs_scatter_log_y_check.isChecked()
        annotate = self.graphs_scatter_annotate_check.isChecked()
        annotate_n = self.graphs_scatter_annotate_n_spin.value()
        fixed_color = self.graphs_scatter_fixed_color_edit.text().strip() or "#4C78A8"
        cmap = self.graphs_scatter_cmap_combo.currentText().strip()

        if x_col not in source_df.columns or y_col not in source_df.columns:
            ax.text(
                0.5, 0.5,
                f"Column not found:\n{x_col!r}  or  {y_col!r}",
                ha="center", va="center",
            )
            ax.set_axis_off()
            self.graphs_scatter_canvas.draw_idle()
            return

        x_data = pd.to_numeric(source_df[x_col], errors="coerce")
        y_data = pd.to_numeric(source_df[y_col], errors="coerce")
        valid = x_data.notna() & y_data.notna()
        x_vals = x_data[valid].to_numpy(dtype=float)
        y_vals = y_data[valid].to_numpy(dtype=float)

        if len(x_vals) == 0:
            ax.text(0.5, 0.5, "No valid data points", ha="center", va="center")
            ax.set_axis_off()
            self.graphs_scatter_canvas.draw_idle()
            return

        # --- size ---
        if size_by != "Fixed size" and size_by in source_df.columns:
            s_raw = pd.to_numeric(source_df[size_by], errors="coerce")[valid]
            s_min, s_max = s_raw.min(), s_raw.max()
            if pd.notna(s_min) and pd.notna(s_max) and s_max > s_min:
                s_vals = (
                    (s_raw - s_min) / (s_max - s_min) * point_size * 3 + point_size * 0.4
                ).to_numpy(dtype=float)
            else:
                s_vals = point_size
        else:
            s_vals = point_size

        # --- color + scatter ---
        if color_by != "Fixed color" and color_by in source_df.columns:
            c_vals = (
                pd.to_numeric(source_df[color_by], errors="coerce")[valid]
                .fillna(0)
                .to_numpy(dtype=float)
            )
            sc = ax.scatter(
                x_vals, y_vals, c=c_vals, cmap=cmap, s=s_vals, alpha=alpha, marker=marker
            )
            self.graphs_scatter_colorbar = self.graphs_scatter_figure.colorbar(
                sc, ax=ax, shrink=0.85, pad=0.02
            )
            self.graphs_scatter_colorbar.set_label(color_by, fontsize=9)
        else:
            ax.scatter(x_vals, y_vals, color=fixed_color, s=s_vals, alpha=alpha, marker=marker)

        # --- trend line ---
        if show_trend and len(x_vals) >= 2:
            try:
                coeff = np.polyfit(x_vals, y_vals, 1)
                x_sorted = np.sort(x_vals)
                r_val = float(np.corrcoef(x_vals, y_vals)[0, 1])
                ax.plot(
                    x_sorted,
                    np.poly1d(coeff)(x_sorted),
                    color="#E45756",
                    linewidth=2,
                    label=f"r = {r_val:.2f}",
                )
                ax.legend(loc="best", fontsize=9)
            except (np.linalg.LinAlgError, ValueError):
                pass

        # --- annotate ---
        if annotate:
            cone_ids = (
                source_df["cone_id"][valid].reset_index(drop=True)
                if "cone_id" in source_df.columns
                else pd.Series(range(len(x_vals)))
            )
            top_idx = pd.Series(y_vals).nlargest(min(annotate_n, len(y_vals))).index
            for idx in top_idx:
                if idx < len(cone_ids):
                    ax.annotate(
                        str(cone_ids.iloc[idx]),
                        (x_vals[idx], y_vals[idx]),
                        textcoords="offset points",
                        xytext=(4, 4),
                        fontsize=8,
                    )

        # --- scales + labels ---
        if log_x:
            ax.set_xscale("log")
        if log_y:
            ax.set_yscale("log")

        title = self.graphs_scatter_title_edit.text().strip() or f"{y_col} vs {x_col}"
        xlabel = self.graphs_scatter_xlabel_edit.text().strip() or (
            x_col + (" [log]" if log_x else "")
        )
        ylabel = self.graphs_scatter_ylabel_edit.text().strip() or (
            y_col + (" [log]" if log_y else "")
        )
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.25, which="both" if (log_x or log_y) else "major")

        self.graphs_scatter_figure.tight_layout()
        self.graphs_scatter_canvas.draw_idle()

    def _save_graphs_scatter(self) -> None:
        output_dir = Path(self.base_path_edit.text().strip()) / "output" / "analyzer"
        output_dir.mkdir(parents=True, exist_ok=True)

        fmt = self.graphs_scatter_format_combo.currentText().lower()
        dpi = self.graphs_scatter_dpi_spin.value()
        use_fix = self.graphs_scatter_use_manual_fix_check.isChecked()
        prefix = "fix_" if use_fix else ""
        x_col = self.graphs_scatter_x_combo.currentText().strip()
        y_col = self.graphs_scatter_y_combo.currentText().strip()
        safe_x = re.sub(r"[^0-9A-Za-z_-]+", "_", x_col).strip("_") or "x"
        safe_y = re.sub(r"[^0-9A-Za-z_-]+", "_", y_col).strip("_") or "y"

        out_path = output_dir / f"{prefix}scatter_{safe_y}_vs_{safe_x}.{fmt}"
        save_kw: dict = {"bbox_inches": "tight", "format": fmt}
        if fmt == "png":
            save_kw["dpi"] = dpi

        try:
            self.graphs_scatter_figure.savefig(out_path, **save_kw)
            self.graphs_scatter_source_label.setText(f"Saved: {out_path}")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            self.graphs_scatter_source_label.setText(f"Save failed: {exc}")
