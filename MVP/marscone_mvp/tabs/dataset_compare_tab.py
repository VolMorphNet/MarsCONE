"""Mixin for the DatasetCompareMixin section of MainWindow."""
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

from marscone_mvp.app_state import save_state
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
class DatasetCompareMixin:
    """Mixin — mixed into MainWindow via multiple inheritance."""

    def _build_graphs_dataset_compare_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        controls_row = QHBoxLayout()
        self.graphs_compare_use_manual_fix_check = QCheckBox("Prefer manual-fix metrics")
        self.graphs_compare_use_manual_fix_check.setChecked(
            self.use_manual_fix_check.isChecked()
        )
        self.graphs_compare_x_combo = QComboBox()
        self.graphs_compare_x_combo.addItems(list(METRIC_CANDIDATES.keys()))
        self.graphs_compare_x_combo.setCurrentText("Wco")
        self.graphs_compare_y_combo = QComboBox()
        self.graphs_compare_y_combo.addItems(list(METRIC_CANDIDATES.keys()))
        self.graphs_compare_y_combo.setCurrentText("WCR_WCO_ratio")
        self.graphs_compare_refresh_button = QPushButton("Refresh")
        self.graphs_compare_add_current_button = QPushButton("Add current dataset")
        self.graphs_compare_open_folder_button = QPushButton("Open compare folder")

        controls_row.addWidget(self.graphs_compare_use_manual_fix_check)
        controls_row.addWidget(QLabel("X:"))
        controls_row.addWidget(self.graphs_compare_x_combo)
        controls_row.addWidget(QLabel("Y:"))
        controls_row.addWidget(self.graphs_compare_y_combo)
        controls_row.addWidget(self.graphs_compare_add_current_button)
        controls_row.addWidget(self.graphs_compare_refresh_button)
        controls_row.addWidget(self.graphs_compare_open_folder_button)
        controls_row.addStretch(1)

        self.graphs_compare_sources_edit = QPlainTextEdit()
        self.graphs_compare_sources_edit.setPlaceholderText(
            "One dataset per line: label;/path/to/base_or_csv\n"
            "Example: Arizona;/path/to/arizona\n"
            "Example: Mars;/path/to/mars"
        )
        self.graphs_compare_sources_edit.setMaximumHeight(100)
        default_base = self.base_path_edit.text().strip()
        if default_base:
            self.graphs_compare_sources_edit.setPlainText(f"Current;{default_base}")

        self.graphs_compare_source_label = QLabel("Source: -")
        self.graphs_compare_source_label.setWordWrap(True)
        self.graphs_compare_source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.graphs_compare_figure, self.graphs_compare_scatter_ax = plt.subplots(
            1, 1, figsize=(9.0, 5.2)
        )
        self.graphs_compare_figure.subplots_adjust(bottom=0.15)
        self.graphs_compare_canvas = FigureCanvas(self.graphs_compare_figure)
        self.graphs_compare_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.graphs_compare_heatmap_figure, self.graphs_compare_heatmap_ax = plt.subplots(
            1, 1, figsize=(7.0, 5.2)
        )
        self.graphs_compare_heatmap_figure.subplots_adjust(bottom=0.20)
        self.graphs_compare_heatmap_canvas = FigureCanvas(self.graphs_compare_heatmap_figure)
        self.graphs_compare_heatmap_canvas.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )
        self.graphs_compare_heatmap_info_label = QLabel(
            "Distance matrix guide: refresh to compute."
        )
        self.graphs_compare_heatmap_info_label.setWordWrap(True)
        self.graphs_compare_heatmap_info_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.graphs_compare_heatmap_info_label.setFixedWidth(210)
        self.graphs_compare_heatmap_info_label.setTextFormat(Qt.RichText)
        self.graphs_compare_colorbar = None
        self.graphs_compare_similarity_model = DataFrameTableModel(float_precision=4)
        self.graphs_compare_similarity_table = QTableView()
        self.graphs_compare_similarity_table.setModel(self.graphs_compare_similarity_model)
        self.graphs_compare_similarity_table.setSortingEnabled(True)
        self.graphs_compare_similarity_table.setMinimumHeight(170)
        self.graphs_compare_stats_info_label = QLabel(
            "Per-dataset stats (same metric definitions as Cross-section > Metrics stats)."
        )
        self.graphs_compare_stats_info_label.setWordWrap(True)
        self.graphs_compare_stats_model = DataFrameTableModel(float_precision=2)
        self.graphs_compare_stats_table = QTableView()
        self.graphs_compare_stats_table.setModel(self.graphs_compare_stats_model)
        self.graphs_compare_stats_table.setSortingEnabled(True)
        self.graphs_compare_stats_table.setMinimumHeight(220)
        self.graphs_compare_embedding_method_combo = QComboBox()
        self.graphs_compare_embedding_method_combo.addItems(["PCA", "UMAP"])
        self.graphs_compare_embedding_method_combo.setCurrentText("PCA")
        self.graphs_compare_embedding_level_combo = QComboBox()
        self.graphs_compare_embedding_level_combo.addItems(["Dataset level", "Cone level"])
        self.graphs_compare_embedding_level_combo.setCurrentText("Dataset level")
        self.graphs_compare_embedding_info_label = QLabel("Embedding summary: -")
        self.graphs_compare_embedding_info_label.setWordWrap(True)
        self.graphs_compare_loadings_model = DataFrameTableModel(float_precision=4)
        self.graphs_compare_loadings_table = QTableView()
        self.graphs_compare_loadings_table.setModel(self.graphs_compare_loadings_model)
        self.graphs_compare_loadings_table.setSortingEnabled(False)
        self.graphs_compare_loadings_table.setMinimumHeight(180)
        self.graphs_compare_loadings_figure, self.graphs_compare_loadings_axes = plt.subplots(
            1, 2, figsize=(5.5, 3.2)
        )
        self.graphs_compare_loadings_figure.subplots_adjust(wspace=0.55)
        self.graphs_compare_loadings_canvas = FigureCanvas(self.graphs_compare_loadings_figure)
        self.graphs_compare_loadings_canvas.setMinimumHeight(180)
        self.graphs_compare_embedding_figure, self.graphs_compare_embedding_ax = plt.subplots(
            1, 1, figsize=(8.0, 4.2)
        )
        self.graphs_compare_embedding_canvas = FigureCanvas(self.graphs_compare_embedding_figure)
        self.graphs_compare_colors_edit = QPlainTextEdit()
        self.graphs_compare_colors_edit.setPlaceholderText(
            "Optional per-dataset colors, one per line:\n"
            "Arizona;#2ca02c\n"
            "Ulyses;#ff7f0e"
        )
        self.graphs_compare_colors_edit.setMaximumHeight(120)
        self.graphs_compare_scatter_point_size_spin = QSpinBox()
        self.graphs_compare_scatter_point_size_spin.setRange(8, 300)
        self.graphs_compare_scatter_point_size_spin.setValue(28)
        self.graphs_compare_scatter_marker_combo = QComboBox()
        self.graphs_compare_scatter_marker_combo.addItems(["o", "s", "^", "D", "P", "X"])
        self.graphs_compare_scatter_marker_combo.setCurrentText("o")
        self.graphs_compare_show_hulls_check = QCheckBox("Show enclosing polygons (convex hull)")
        self.graphs_compare_show_hulls_check.setChecked(False)
        self.graphs_compare_hull_style_combo = QComboBox()
        self.graphs_compare_hull_style_combo.addItems(["Fill + outline", "Outline only"])
        self.graphs_compare_hull_style_combo.setCurrentText("Fill + outline")
        self.graphs_compare_hull_alpha_spin = QDoubleSpinBox()
        self.graphs_compare_hull_alpha_spin.setRange(0.02, 0.80)
        self.graphs_compare_hull_alpha_spin.setDecimals(2)
        self.graphs_compare_hull_alpha_spin.setSingleStep(0.02)
        self.graphs_compare_hull_alpha_spin.setValue(0.14)
        self.graphs_compare_log_x_check = QCheckBox("Log X")
        self.graphs_compare_log_x_check.setChecked(False)
        self.graphs_compare_log_y_check = QCheckBox("Log Y")
        self.graphs_compare_log_y_check.setChecked(False)
        self.graphs_compare_scatter_title_edit = QLineEdit()
        self.graphs_compare_scatter_title_edit.setPlaceholderText("Title (auto)")
        self.graphs_compare_scatter_xlabel_edit = QLineEdit()
        self.graphs_compare_scatter_xlabel_edit.setPlaceholderText("X label (auto)")
        self.graphs_compare_scatter_ylabel_edit = QLineEdit()
        self.graphs_compare_scatter_ylabel_edit.setPlaceholderText("Y label (auto)")
        self.graphs_compare_heatmap_title_edit = QLineEdit()
        self.graphs_compare_heatmap_title_edit.setPlaceholderText("Heatmap title (auto)")
        self.graphs_compare_heatmap_xlabel_edit = QLineEdit()
        self.graphs_compare_heatmap_xlabel_edit.setPlaceholderText("Heatmap X label (auto)")
        self.graphs_compare_heatmap_ylabel_edit = QLineEdit()
        self.graphs_compare_heatmap_ylabel_edit.setPlaceholderText("Heatmap Y label (auto)")
        self.graphs_compare_heatmap_half_check = QCheckBox("Half matrix (lower triangle)")
        self.graphs_compare_heatmap_half_check.setChecked(False)
        self.graphs_compare_embedding_title_edit = QLineEdit()
        self.graphs_compare_embedding_title_edit.setPlaceholderText("Embedding title (auto)")
        self.graphs_compare_embedding_xlabel_edit = QLineEdit()
        self.graphs_compare_embedding_xlabel_edit.setPlaceholderText("Embedding X label (auto)")
        self.graphs_compare_embedding_ylabel_edit = QLineEdit()
        self.graphs_compare_embedding_ylabel_edit.setPlaceholderText("Embedding Y label (auto)")
        self.graphs_compare_export_format_combo = QComboBox()
        self.graphs_compare_export_format_combo.addItems(["PNG", "SVG", "PDF"])
        self.graphs_compare_embedding_point_size_spin = QSpinBox()
        self.graphs_compare_embedding_point_size_spin.setRange(8, 300)
        self.graphs_compare_embedding_point_size_spin.setValue(90)
        self.graphs_compare_embedding_marker_combo = QComboBox()
        self.graphs_compare_embedding_marker_combo.addItems(["o", "s", "^", "D", "P", "X"])
        self.graphs_compare_embedding_marker_combo.setCurrentText("o")
        self.graphs_compare_autofill_colors_button = QPushButton("Autofill colors")
        self.graphs_compare_open_export_button = QPushButton("Open export folder")
        self.graphs_compare_export_paths_edit = QPlainTextEdit()
        self.graphs_compare_export_paths_edit.setReadOnly(True)
        self.graphs_compare_export_paths_edit.setMaximumHeight(160)

        self.graphs_compare_refresh_button.clicked.connect(self._refresh_graphs_dataset_compare)
        self.graphs_compare_add_current_button.clicked.connect(
            self._on_graphs_compare_add_current_dataset
        )
        self.graphs_compare_autofill_colors_button.clicked.connect(
            self._autofill_graphs_compare_colors
        )
        self.graphs_compare_open_folder_button.clicked.connect(
            self._open_graphs_compare_export_dir
        )
        self.graphs_compare_open_export_button.clicked.connect(
            self._open_graphs_compare_export_dir
        )
        self.graphs_compare_use_manual_fix_check.toggled.connect(
            lambda _checked: self._refresh_graphs_dataset_compare()
        )
        self.graphs_compare_x_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_dataset_compare()
        )
        self.graphs_compare_y_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_dataset_compare()
        )
        self.graphs_compare_embedding_method_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_dataset_compare()
        )
        self.graphs_compare_embedding_level_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_dataset_compare()
        )
        self.graphs_compare_scatter_point_size_spin.valueChanged.connect(
            lambda _value: self._refresh_graphs_dataset_compare()
        )
        self.graphs_compare_embedding_point_size_spin.valueChanged.connect(
            lambda _value: self._refresh_graphs_dataset_compare()
        )
        self.graphs_compare_scatter_marker_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_dataset_compare()
        )
        self.graphs_compare_show_hulls_check.toggled.connect(
            lambda _checked: self._refresh_graphs_dataset_compare()
        )
        self.graphs_compare_hull_style_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_dataset_compare()
        )
        self.graphs_compare_hull_alpha_spin.valueChanged.connect(
            lambda _value: self._refresh_graphs_dataset_compare()
        )
        self.graphs_compare_log_x_check.toggled.connect(
            lambda _checked: self._refresh_graphs_dataset_compare()
        )
        self.graphs_compare_log_y_check.toggled.connect(
            lambda _checked: self._refresh_graphs_dataset_compare()
        )
        self.graphs_compare_export_format_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_dataset_compare()
        )
        for _edit in [
            self.graphs_compare_scatter_title_edit,
            self.graphs_compare_scatter_xlabel_edit,
            self.graphs_compare_scatter_ylabel_edit,
        ]:
            _edit.editingFinished.connect(self._refresh_graphs_dataset_compare)
            _edit.textChanged.connect(lambda _text: self._update_graphs_compare_scatter_labels())
        for _edit in [
            self.graphs_compare_heatmap_title_edit,
            self.graphs_compare_heatmap_xlabel_edit,
            self.graphs_compare_heatmap_ylabel_edit,
        ]:
            _edit.editingFinished.connect(self._refresh_graphs_dataset_compare)
            _edit.textChanged.connect(lambda _text: self._update_graphs_compare_heatmap_labels())
        self.graphs_compare_heatmap_half_check.toggled.connect(
            lambda _checked: self._refresh_graphs_dataset_compare()
        )
        for _edit in [
            self.graphs_compare_embedding_title_edit,
            self.graphs_compare_embedding_xlabel_edit,
            self.graphs_compare_embedding_ylabel_edit,
        ]:
            _edit.editingFinished.connect(self._refresh_graphs_dataset_compare)
            _edit.textChanged.connect(
                lambda _text: self._update_graphs_compare_embedding_labels()
            )
        self.graphs_compare_embedding_marker_combo.currentTextChanged.connect(
            lambda _text: self._refresh_graphs_dataset_compare()
        )

        layout.addLayout(controls_row)
        layout.addWidget(QLabel("Datasets (label;path):"))
        layout.addWidget(self.graphs_compare_sources_edit)
        layout.addWidget(self.graphs_compare_source_label)

        compare_tabs = QTabWidget(tab)

        scatter_sub_tab = QWidget()
        scatter_sub_layout = QVBoxLayout(scatter_sub_tab)
        scatter_controls_row = QHBoxLayout()
        scatter_controls_row.addWidget(self.graphs_compare_show_hulls_check)
        scatter_controls_row.addWidget(QLabel("Hull style:"))
        scatter_controls_row.addWidget(self.graphs_compare_hull_style_combo)
        scatter_controls_row.addWidget(QLabel("Hull alpha:"))
        scatter_controls_row.addWidget(self.graphs_compare_hull_alpha_spin)
        scatter_controls_row.addSpacing(12)
        scatter_controls_row.addWidget(self.graphs_compare_log_x_check)
        scatter_controls_row.addWidget(self.graphs_compare_log_y_check)
        scatter_controls_row.addSpacing(8)
        scatter_controls_row.addWidget(QLabel("Title:"))
        scatter_controls_row.addWidget(self.graphs_compare_scatter_title_edit)
        scatter_controls_row.addWidget(QLabel("X label:"))
        scatter_controls_row.addWidget(self.graphs_compare_scatter_xlabel_edit)
        scatter_controls_row.addWidget(QLabel("Y label:"))
        scatter_controls_row.addWidget(self.graphs_compare_scatter_ylabel_edit)
        scatter_controls_row.addWidget(QLabel("Format:"))
        scatter_controls_row.addWidget(self.graphs_compare_export_format_combo)
        scatter_controls_row.addStretch(1)
        scatter_sub_layout.addLayout(scatter_controls_row)
        scatter_sub_layout.addWidget(self.graphs_compare_canvas, 1)
        compare_tabs.addTab(scatter_sub_tab, "Scatter")

        heatmap_sub_tab = QWidget()
        heatmap_sub_layout = QVBoxLayout(heatmap_sub_tab)
        heatmap_controls_row = QHBoxLayout()
        heatmap_controls_row.addWidget(QLabel("Title:"))
        heatmap_controls_row.addWidget(self.graphs_compare_heatmap_title_edit)
        heatmap_controls_row.addWidget(QLabel("X label:"))
        heatmap_controls_row.addWidget(self.graphs_compare_heatmap_xlabel_edit)
        heatmap_controls_row.addWidget(QLabel("Y label:"))
        heatmap_controls_row.addWidget(self.graphs_compare_heatmap_ylabel_edit)
        heatmap_controls_row.addWidget(self.graphs_compare_heatmap_half_check)
        heatmap_controls_row.addStretch(1)
        heatmap_sub_layout.addLayout(heatmap_controls_row)
        heatmap_body_layout = QHBoxLayout()
        heatmap_body_layout.addWidget(self.graphs_compare_heatmap_info_label)
        heatmap_body_layout.addWidget(self.graphs_compare_heatmap_canvas, 1)
        heatmap_sub_layout.addLayout(heatmap_body_layout, 1)
        compare_tabs.addTab(heatmap_sub_tab, "Heatmap")

        embedding_tab = QWidget()
        embedding_layout = QVBoxLayout(embedding_tab)
        embedding_row = QHBoxLayout()
        embedding_row.addWidget(QLabel("Embedding level:"))
        embedding_row.addWidget(self.graphs_compare_embedding_level_combo)
        embedding_row.addWidget(QLabel("Embedding method:"))
        embedding_row.addWidget(self.graphs_compare_embedding_method_combo)
        embedding_row.addSpacing(8)
        embedding_row.addWidget(QLabel("Title:"))
        embedding_row.addWidget(self.graphs_compare_embedding_title_edit)
        embedding_row.addWidget(QLabel("X label:"))
        embedding_row.addWidget(self.graphs_compare_embedding_xlabel_edit)
        embedding_row.addWidget(QLabel("Y label:"))
        embedding_row.addWidget(self.graphs_compare_embedding_ylabel_edit)
        embedding_row.addStretch(1)
        embedding_layout.addLayout(embedding_row)
        embedding_layout.addWidget(self.graphs_compare_embedding_info_label)
        embedding_layout.addWidget(self.graphs_compare_embedding_canvas)
        embedding_layout.addWidget(
            QLabel(
                "Loadings / importance (PC1 & PC2)  —  units: z-score of metrics"
            )
        )
        loadings_row = QHBoxLayout()
        loadings_row.addWidget(self.graphs_compare_loadings_table, stretch=1)
        loadings_row.addWidget(self.graphs_compare_loadings_canvas, stretch=2)
        embedding_layout.addLayout(loadings_row)
        compare_tabs.addTab(embedding_tab, "Embedding")

        similarity_tab = QWidget()
        similarity_layout = QVBoxLayout(similarity_tab)
        similarity_layout.addWidget(
            QLabel(
                "Similarity report (multi-metric, standardized space; "
                "lower distance = more similar)"
            )
        )
        similarity_layout.addWidget(self.graphs_compare_similarity_table)
        compare_tabs.addTab(similarity_tab, "Similarity report")

        stats_tab = QWidget()
        stats_layout = QVBoxLayout(stats_tab)
        self.graphs_compare_show_reference_rows_check = QCheckBox("Show reference rows")
        self.graphs_compare_show_reference_rows_check.setChecked(False)
        self.graphs_compare_show_reference_rows_check.toggled.connect(
            lambda _checked: self._refresh_graphs_dataset_compare()
        )
        stats_layout.addWidget(self.graphs_compare_show_reference_rows_check)
        stats_layout.addWidget(self.graphs_compare_stats_info_label)
        stats_layout.addWidget(self.graphs_compare_stats_table)
        compare_tabs.addTab(stats_tab, "Stats compare")

        export_tab = QWidget()
        export_layout = QVBoxLayout(export_tab)
        export_actions_row = QHBoxLayout()
        export_actions_row.addWidget(self.graphs_compare_autofill_colors_button)
        export_actions_row.addWidget(self.graphs_compare_open_export_button)
        export_actions_row.addStretch(1)
        export_layout.addLayout(export_actions_row)
        export_layout.addWidget(QLabel("Dataset colors (label;color or label=#hex):"))
        export_layout.addWidget(self.graphs_compare_colors_edit)
        style_grid = QGridLayout()
        style_grid.addWidget(QLabel("Scatter point size"), 0, 0)
        style_grid.addWidget(self.graphs_compare_scatter_point_size_spin, 0, 1)
        style_grid.addWidget(QLabel("Scatter marker"), 0, 2)
        style_grid.addWidget(self.graphs_compare_scatter_marker_combo, 0, 3)
        style_grid.addWidget(QLabel("Embedding point size"), 1, 0)
        style_grid.addWidget(self.graphs_compare_embedding_point_size_spin, 1, 1)
        style_grid.addWidget(QLabel("Embedding marker"), 1, 2)
        style_grid.addWidget(self.graphs_compare_embedding_marker_combo, 1, 3)
        export_layout.addLayout(style_grid)
        export_layout.addWidget(QLabel("Export targets / latest outputs:"))
        export_layout.addWidget(self.graphs_compare_export_paths_edit)
        compare_tabs.addTab(export_tab, "Export + settings")

        layout.addWidget(compare_tabs)

        self._refresh_graphs_dataset_compare()
        return tab

    def _on_graphs_compare_add_current_dataset(self) -> None:
        base_path = self.base_path_edit.text().strip()
        if not base_path:
            return

        existing_text = self.graphs_compare_sources_edit.toPlainText().strip()
        line = f"Current;{base_path}"
        if not existing_text:
            self.graphs_compare_sources_edit.setPlainText(line)
            return

        existing_lines = [ln.strip() for ln in existing_text.splitlines() if ln.strip()]
        if line in existing_lines:
            return
        self.graphs_compare_sources_edit.setPlainText(existing_text + "\n" + line)

    def _render_loadings_barplot(self, loadings_df: "pd.DataFrame") -> None:  # noqa: F821
        """Render horizontal barplot of PC1 and PC2 loadings (long-format table)."""
        ax1, ax2 = self.graphs_compare_loadings_axes
        ax1.clear()
        ax2.clear()
        for ax, pc_label, title in ((ax1, "PC1", "PC1 loadings"), (ax2, "PC2", "PC2 loadings")):
            subset = loadings_df[loadings_df["component"] == pc_label].copy()
            if subset.empty:
                ax.set_axis_off()
                continue
            subset = subset.sort_values("rank")
            features = [
                str(f).replace("__median", " med").replace("__iqr", " IQR")
                for f in subset["feature"].tolist()
            ]
            vals = subset["loading"].tolist()
            colors = ["#2166ac" if v >= 0 else "#d6604d" for v in vals]
            y_pos = range(len(features))
            ax.barh(list(y_pos), vals, color=colors, edgecolor="none", height=0.7)
            ax.set_yticks(list(y_pos))
            ax.set_yticklabels(features, fontsize=7)
            ax.axvline(0, color="k", linewidth=0.6, linestyle="-")
            ax.set_title(title, fontsize=8)
            ax.set_xlabel("loading", fontsize=7)
            ax.tick_params(axis="x", labelsize=6)
            ax.invert_yaxis()
            ax.set_axis_on()
        self.graphs_compare_loadings_figure.tight_layout()
        self.graphs_compare_loadings_canvas.draw()

    def _update_graphs_compare_scatter_labels(self) -> None:
        """Apply scatter title/axis labels immediately in the visible canvas."""
        if not hasattr(self, "graphs_compare_scatter_ax"):
            return

        x_metric = self.graphs_compare_x_combo.currentText().strip()
        y_metric = self.graphs_compare_y_combo.currentText().strip()
        log_x = self.graphs_compare_log_x_check.isChecked()
        log_y = self.graphs_compare_log_y_check.isChecked()
        scatter_title = self.graphs_compare_scatter_title_edit.text().strip()
        scatter_xlabel = self.graphs_compare_scatter_xlabel_edit.text().strip()
        scatter_ylabel = self.graphs_compare_scatter_ylabel_edit.text().strip()

        default_xlabel = x_metric + (" [log]" if log_x else "")
        default_ylabel = y_metric + (" [log]" if log_y else "")
        ax_left = self.graphs_compare_scatter_ax
        ax_left.set_xlabel(scatter_xlabel or default_xlabel)
        ax_left.set_ylabel(scatter_ylabel or default_ylabel)
        ax_left.set_title(scatter_title or "Multi-dataset scatter with centroids")
        self.graphs_compare_canvas.draw_idle()

    def _update_graphs_compare_heatmap_labels(self) -> None:
        """Apply heatmap title/axis labels immediately in the visible canvas."""
        if not hasattr(self, "graphs_compare_heatmap_ax"):
            return

        default_title = getattr(
            self,
            "_graphs_compare_heatmap_default_title",
            "Centroid distance matrix (unitless z-space)",
        )
        default_xlabel = getattr(self, "_graphs_compare_heatmap_default_xlabel", "Dataset")
        default_ylabel = getattr(self, "_graphs_compare_heatmap_default_ylabel", "Dataset")
        heatmap_title = self.graphs_compare_heatmap_title_edit.text().strip()
        heatmap_xlabel = self.graphs_compare_heatmap_xlabel_edit.text().strip()
        heatmap_ylabel = self.graphs_compare_heatmap_ylabel_edit.text().strip()

        ax_right = self.graphs_compare_heatmap_ax
        ax_right.set_title(heatmap_title or default_title)
        ax_right.set_xlabel(heatmap_xlabel or default_xlabel)
        ax_right.set_ylabel(heatmap_ylabel or default_ylabel)
        self.graphs_compare_heatmap_canvas.draw_idle()

    def _update_graphs_compare_embedding_labels(self) -> None:
        """Apply embedding title/axis labels immediately in the visible canvas."""
        if not hasattr(self, "graphs_compare_embedding_ax"):
            return

        default_title = getattr(
            self,
            "_graphs_compare_embedding_default_title",
            "Embedding (multi-metric)",
        )
        default_xlabel = getattr(self, "_graphs_compare_embedding_default_xlabel", "Component 1")
        default_ylabel = getattr(self, "_graphs_compare_embedding_default_ylabel", "Component 2")
        embedding_title = self.graphs_compare_embedding_title_edit.text().strip()
        embedding_xlabel = self.graphs_compare_embedding_xlabel_edit.text().strip()
        embedding_ylabel = self.graphs_compare_embedding_ylabel_edit.text().strip()

        emb_ax = self.graphs_compare_embedding_ax
        emb_ax.set_title(embedding_title or default_title)
        emb_ax.set_xlabel(embedding_xlabel or default_xlabel)
        emb_ax.set_ylabel(embedding_ylabel or default_ylabel)
        self.graphs_compare_embedding_canvas.draw_idle()

    def _dataset_compare_output_dir(self) -> Path:
        base_text = self.base_path_edit.text().strip()
        base_path = Path(base_text) if base_text else self.mvp_root
        compare_dir = base_path / "output" / "analyzer" / "dataset_compare"
        compare_dir.mkdir(parents=True, exist_ok=True)
        return compare_dir

    def _persist_dataset_compare_state(self) -> None:
        self.state.setdefault("dataset_compare", {}).update(
            {
                "sources_text": self.graphs_compare_sources_edit.toPlainText().strip(),
                "colors_text": self.graphs_compare_colors_edit.toPlainText().strip(),
                "x_metric": self.graphs_compare_x_combo.currentText(),
                "y_metric": self.graphs_compare_y_combo.currentText(),
                "use_manual_fix": self.graphs_compare_use_manual_fix_check.isChecked(),
                "embedding_method": self.graphs_compare_embedding_method_combo.currentText(),
                "embedding_level": self.graphs_compare_embedding_level_combo.currentText(),
                "scatter_point_size": self.graphs_compare_scatter_point_size_spin.value(),
                "scatter_marker": self.graphs_compare_scatter_marker_combo.currentText(),
                "embedding_point_size": self.graphs_compare_embedding_point_size_spin.value(),
                "embedding_marker": self.graphs_compare_embedding_marker_combo.currentText(),
                "show_hulls": self.graphs_compare_show_hulls_check.isChecked(),
                "hull_style": self.graphs_compare_hull_style_combo.currentText(),
                "hull_alpha": self.graphs_compare_hull_alpha_spin.value(),
                "show_reference_rows": self.graphs_compare_show_reference_rows_check.isChecked(),
                "scatter_title": self.graphs_compare_scatter_title_edit.text().strip(),
                "scatter_xlabel": self.graphs_compare_scatter_xlabel_edit.text().strip(),
                "scatter_ylabel": self.graphs_compare_scatter_ylabel_edit.text().strip(),
                "heatmap_title": self.graphs_compare_heatmap_title_edit.text().strip(),
                "heatmap_xlabel": self.graphs_compare_heatmap_xlabel_edit.text().strip(),
                "heatmap_ylabel": self.graphs_compare_heatmap_ylabel_edit.text().strip(),
                "heatmap_half_matrix": self.graphs_compare_heatmap_half_check.isChecked(),
                "embedding_title": self.graphs_compare_embedding_title_edit.text().strip(),
                "embedding_xlabel": self.graphs_compare_embedding_xlabel_edit.text().strip(),
                "embedding_ylabel": self.graphs_compare_embedding_ylabel_edit.text().strip(),
                "export_format": self.graphs_compare_export_format_combo.currentText(),
            }
        )
        save_state(self.mvp_root, self.state)

    def _parse_graphs_compare_color_map(self, dataset_labels: list[str]) -> dict[str, str]:
        color_map: dict[str, str] = {}
        valid_labels = {label.strip() for label in dataset_labels if label.strip()}
        for raw_line in self.graphs_compare_colors_edit.toPlainText().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            if ";" in line:
                label, color_text = [part.strip() for part in line.split(";", 1)]
            elif "=" in line:
                label, color_text = [part.strip() for part in line.split("=", 1)]
            else:
                continue

            if label not in valid_labels:
                continue
            if QColor(color_text).isValid():
                color_map[label] = color_text
        return color_map

    def _autofill_graphs_compare_colors(self) -> None:
        dataset_labels: list[str] = []
        for idx, raw_line in enumerate(
            self.graphs_compare_sources_edit.toPlainText().splitlines(),
            start=1,
        ):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if ";" in line:
                label = line.split(";", 1)[0].strip()
            else:
                label = f"Dataset {idx}"
            if label and label not in dataset_labels:
                dataset_labels.append(label)

        palette = plt.cm.get_cmap("tab10", max(10, len(dataset_labels) or 1))
        existing_map = self._parse_graphs_compare_color_map(dataset_labels)
        lines: list[str] = []
        for idx, label in enumerate(dataset_labels):
            color_text = existing_map.get(label)
            if color_text is None:
                rgba = palette(idx % 10)
                color_text = QColor.fromRgbF(rgba[0], rgba[1], rgba[2]).name()
            lines.append(f"{label};{color_text}")

        self.graphs_compare_colors_edit.setPlainText("\n".join(lines))
        self._refresh_graphs_dataset_compare()

    def _open_graphs_compare_export_dir(self) -> None:
        compare_dir = self._dataset_compare_output_dir()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(compare_dir)))

    def _build_dataset_compare_stats_table(
        self,
        frames_by_label: dict[str, pd.DataFrame],
        include_reference_rows: bool = False,
    ) -> pd.DataFrame:
        if not frames_by_label:
            return pd.DataFrame()

        reference_label = next(iter(frames_by_label.keys()))
        blocks: list[pd.DataFrame] = []
        reference_stats_by_metric: pd.DataFrame | None = None

        for label, frame in frames_by_label.items():
            metrics_df = self._extract_cone_metric_plot_columns(frame)
            stats_df = self._build_stats_dataframe_from_metrics(metrics_df)
            if stats_df.empty:
                continue
            stats_df = stats_df.copy()
            stats_df.insert(0, "dataset", label)
            stats_df.insert(1, "reference_dataset", reference_label)
            blocks.append(stats_df)
            if label == reference_label:
                reference_stats_by_metric = stats_df.set_index("metric")

        if not blocks:
            return pd.DataFrame()

        out = pd.concat(blocks, ignore_index=True)
        out["delta_mean_vs_ref"] = np.nan
        out["delta_median_vs_ref"] = np.nan
        out["delta_mean_pct_vs_ref"] = np.nan
        out["delta_median_pct_vs_ref"] = np.nan

        if reference_stats_by_metric is not None and not reference_stats_by_metric.empty:
            for idx, row in out.iterrows():
                metric_name = str(row.get("metric", ""))
                if metric_name not in reference_stats_by_metric.index:
                    continue
                ref_row = reference_stats_by_metric.loc[metric_name]
                if isinstance(ref_row, pd.DataFrame):
                    ref_row = ref_row.iloc[0]

                mean_val = pd.to_numeric(pd.Series([row.get("mean")]), errors="coerce").iloc[0]
                median_val = pd.to_numeric(
                    pd.Series([row.get("p50 (median)")]), errors="coerce"
                ).iloc[0]
                ref_mean = pd.to_numeric(pd.Series([ref_row.get("mean")]), errors="coerce").iloc[0]
                ref_median = pd.to_numeric(
                    pd.Series([ref_row.get("p50 (median)")]), errors="coerce"
                ).iloc[0]

                if pd.notna(mean_val) and pd.notna(ref_mean):
                    out.at[idx, "delta_mean_vs_ref"] = float(mean_val - ref_mean)
                    if float(ref_mean) != 0.0:
                        out.at[idx, "delta_mean_pct_vs_ref"] = (
                            100.0 * float(mean_val - ref_mean) / float(ref_mean)
                        )
                if pd.notna(median_val) and pd.notna(ref_median):
                    out.at[idx, "delta_median_vs_ref"] = float(median_val - ref_median)
                    if float(ref_median) != 0.0:
                        out.at[idx, "delta_median_pct_vs_ref"] = (
                            100.0 * float(median_val - ref_median) / float(ref_median)
                        )

        # For multi-dataset comparisons, optionally hide reference rows
        # to avoid self-vs-self duplicates.
        if out["dataset"].nunique(dropna=True) > 1 and not include_reference_rows:
            out = out[out["dataset"] != out["reference_dataset"]].reset_index(drop=True)

        numeric_columns = [
            "min",
            "p05",
            "p25",
            "p50 (median)",
            "mean",
            "p75",
            "p95",
            "max",
            "delta_mean_vs_ref",
            "delta_median_vs_ref",
            "delta_mean_pct_vs_ref",
            "delta_median_pct_vs_ref",
        ]
        for column in numeric_columns:
            if column in out.columns:
                out[column] = pd.to_numeric(out[column], errors="coerce").round(2)

        return out

    def _refresh_graphs_dataset_compare(self) -> None:
        # Avoid overwriting saved state during initial UI construction.
        if getattr(self, "_state_loaded", False):
            self._persist_dataset_compare_state()
        ax_left = self.graphs_compare_scatter_ax
        ax_right = self.graphs_compare_heatmap_ax
        emb_ax = self.graphs_compare_embedding_ax
        if self.graphs_compare_colorbar is not None:
            self.graphs_compare_colorbar.remove()
            self.graphs_compare_colorbar = None
        self.graphs_compare_similarity_model.set_dataframe(pd.DataFrame())
        self.graphs_compare_stats_model.set_dataframe(pd.DataFrame())
        self.graphs_compare_loadings_model.set_dataframe(pd.DataFrame())
        ax_left.clear()
        ax_right.clear()
        emb_ax.clear()
        for _ax in self.graphs_compare_loadings_axes:
            _ax.clear()

        x_metric = self.graphs_compare_x_combo.currentText().strip()
        y_metric = self.graphs_compare_y_combo.currentText().strip()
        use_manual_fix = self.graphs_compare_use_manual_fix_check.isChecked()
        embedding_method = self.graphs_compare_embedding_method_combo.currentText().strip()
        embedding_level_text = self.graphs_compare_embedding_level_combo.currentText().strip()
        embedding_level = (
            "cone" if embedding_level_text.lower().startswith("cone") else "dataset"
        )
        scatter_point_size = int(self.graphs_compare_scatter_point_size_spin.value())
        scatter_marker = self.graphs_compare_scatter_marker_combo.currentText().strip() or "o"
        show_hulls = self.graphs_compare_show_hulls_check.isChecked()
        hull_style = self.graphs_compare_hull_style_combo.currentText().strip().lower()
        hull_outline_only = hull_style.startswith("outline")
        hull_alpha = float(self.graphs_compare_hull_alpha_spin.value())
        log_x = self.graphs_compare_log_x_check.isChecked()
        log_y = self.graphs_compare_log_y_check.isChecked()
        show_half_heatmap = self.graphs_compare_heatmap_half_check.isChecked()
        export_format = (
            self.graphs_compare_export_format_combo.currentText().strip().lower() or "png"
        )
        embedding_point_size = int(self.graphs_compare_embedding_point_size_spin.value())
        embedding_marker = self.graphs_compare_embedding_marker_combo.currentText().strip() or "o"

        dataset_lines = [
            line.strip()
            for line in self.graphs_compare_sources_edit.toPlainText().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

        compare_dir = self._dataset_compare_output_dir()
        mode_prefix = "fix_" if use_manual_fix else ""
        safe_x = re.sub(r"[^0-9A-Za-z_-]+", "_", x_metric).strip("_") or "x"
        safe_y = re.sub(r"[^0-9A-Za-z_-]+", "_", y_metric).strip("_") or "y"
        safe_emb = re.sub(r"[^0-9A-Za-z_-]+", "_", embedding_method).strip("_") or "emb"
        safe_level = re.sub(r"[^0-9A-Za-z_-]+", "_", embedding_level).strip("_") or "level"

        scatter_plot = (
            compare_dir / f"{mode_prefix}compare_scatter_{safe_x}_vs_{safe_y}.{export_format}"
        )
        heatmap_plot = (
            compare_dir / f"{mode_prefix}compare_heatmap_{safe_x}_vs_{safe_y}.{export_format}"
        )
        embedding_plot = (
            compare_dir / f"{mode_prefix}compare_embedding_{safe_level}_{safe_emb}.{export_format}"
        )
        points_csv = compare_dir / f"{mode_prefix}compare_points_{safe_x}_vs_{safe_y}.csv"
        matrix_csv = (
            compare_dir
            / f"{mode_prefix}compare_centroid_distance_{safe_x}_vs_{safe_y}.csv"
        )
        similarity_csv = compare_dir / f"{mode_prefix}compare_similarity_report.csv"
        stats_compare_csv = compare_dir / f"{mode_prefix}compare_metrics_stats.csv"
        embedding_csv = compare_dir / f"{mode_prefix}compare_embedding_{safe_level}_{safe_emb}.csv"
        loadings_csv = compare_dir / f"{mode_prefix}compare_loadings_{safe_level}_{safe_emb}.csv"
        save_kw: dict = {"bbox_inches": "tight", "format": export_format}
        if export_format == "png":
            save_kw["dpi"] = 200

        export_fmt_upper = export_format.upper()
        self.graphs_compare_export_paths_edit.setPlainText(
            "\n".join(
                [
                    f"Folder: {compare_dir}",
                    f"Scatter {export_fmt_upper}: {scatter_plot.name}",
                    f"Heatmap {export_fmt_upper}: {heatmap_plot.name}",
                    f"Embedding {export_fmt_upper}: {embedding_plot.name}",
                    f"Points CSV: {points_csv.name}",
                    f"Centroid distance CSV: {matrix_csv.name}",
                    f"Similarity CSV: {similarity_csv.name}",
                    f"Stats compare CSV: {stats_compare_csv.name}",
                    f"Embedding CSV: {embedding_csv.name}",
                    f"Loadings CSV: {loadings_csv.name}",
                ]
            )
        )
        self.graphs_compare_embedding_info_label.setText("Embedding summary: waiting for data")

        if not dataset_lines:
            ax_left.text(0.5, 0.5, "Add at least one dataset", ha="center", va="center")
            ax_left.set_axis_off()
            ax_right.text(0.5, 0.5, "No similarity matrix", ha="center", va="center")
            ax_right.set_axis_off()
            self.graphs_compare_source_label.setText("Source: no dataset lines")
            self.graphs_compare_figure.tight_layout()
            self.graphs_compare_figure.savefig(scatter_plot, **save_kw)
            self.graphs_compare_canvas.draw_idle()
            self.graphs_compare_heatmap_figure.tight_layout()
            self.graphs_compare_heatmap_canvas.draw_idle()
            emb_ax.text(0.5, 0.5, "No embedding", ha="center", va="center")
            emb_ax.set_axis_off()
            self.graphs_compare_embedding_figure.tight_layout()
            self.graphs_compare_embedding_figure.savefig(embedding_plot, **save_kw)
            self.graphs_compare_embedding_canvas.draw_idle()
            self.graphs_compare_stats_info_label.setText(
                "Per-dataset stats: add at least one valid dataset."
            )
            pd.DataFrame().to_csv(stats_compare_csv, sep=";", index=False)
            return

        loaded_frames: list[pd.DataFrame] = []
        loaded_labels: list[str] = []
        loaded_paths: list[str] = []
        failed: list[str] = []

        for idx, line in enumerate(dataset_lines, start=1):
            if ";" in line:
                label, raw_path = [part.strip() for part in line.split(";", 1)]
            else:
                label = f"Dataset {idx}"
                raw_path = line

            if not raw_path:
                failed.append(f"{label}: empty path")
                continue

            csv_path = resolve_metrics_csv_path(raw_path, use_manual_fix=use_manual_fix)
            if not csv_path.exists():
                failed.append(f"{label}: missing {csv_path}")
                continue

            try:
                frame = pd.read_csv(csv_path, sep=";")
            except Exception as exc:  # pylint: disable=broad-exception-caught
                failed.append(f"{label}: {exc}")
                continue

            loaded_frames.append(frame)
            loaded_labels.append(label or f"Dataset {idx}")
            loaded_paths.append(str(csv_path))

        if not loaded_frames:
            ax_left.text(0.5, 0.5, "No valid datasets", ha="center", va="center")
            ax_left.set_axis_off()
            ax_right.text(0.5, 0.5, "No similarity matrix", ha="center", va="center")
            ax_right.set_axis_off()
            status = "Source: failed to load datasets"
            if failed:
                status += " | " + " ; ".join(failed[:3])
            self.graphs_compare_source_label.setText(status)
            self.graphs_compare_figure.tight_layout()
            self.graphs_compare_figure.savefig(scatter_plot, **save_kw)
            self.graphs_compare_canvas.draw_idle()
            self.graphs_compare_heatmap_figure.tight_layout()
            self.graphs_compare_heatmap_canvas.draw_idle()
            emb_ax.text(0.5, 0.5, "No embedding", ha="center", va="center")
            emb_ax.set_axis_off()
            self.graphs_compare_embedding_figure.tight_layout()
            self.graphs_compare_embedding_figure.savefig(embedding_plot, **save_kw)
            self.graphs_compare_embedding_canvas.draw_idle()
            self.graphs_compare_stats_info_label.setText(
                "Per-dataset stats: no datasets could be loaded."
            )
            pd.DataFrame().to_csv(stats_compare_csv, sep=";", index=False)
            return

        frames_by_label = dict(zip(loaded_labels, loaded_frames))
        include_reference_rows = self.graphs_compare_show_reference_rows_check.isChecked()
        stats_compare_df = self._build_dataset_compare_stats_table(
            frames_by_label,
            include_reference_rows=include_reference_rows,
        )
        self.graphs_compare_stats_model.set_dataframe(stats_compare_df)
        self.graphs_compare_stats_table.resizeColumnsToContents()
        stats_compare_df.to_csv(stats_compare_csv, sep=";", index=False)
        if loaded_labels:
            refs_mode_text = "visible" if include_reference_rows else "hidden"
            self.graphs_compare_stats_info_label.setText(
                "Per-dataset stats table with deltas vs reference dataset: "
                f"{loaded_labels[0]} (reference rows: {refs_mode_text})"
            )
        else:
            self.graphs_compare_stats_info_label.setText(
                "Per-dataset stats: no reference dataset available."
            )

        points_blocks: list[pd.DataFrame] = []
        for label, frame in zip(loaded_labels, loaded_frames):
            points = build_xy_points(frame, label, x_metric, y_metric)
            if not points.empty:
                points_blocks.append(points)

        if not points_blocks:
            ax_left.text(
                0.5,
                0.5,
                f"No points for metrics: {x_metric} vs {y_metric}",
                ha="center",
                va="center",
            )
            ax_left.set_axis_off()
            ax_right.text(0.5, 0.5, "No similarity matrix", ha="center", va="center")
            ax_right.set_axis_off()
            self.graphs_compare_source_label.setText(
                f"Source: loaded {len(loaded_frames)} datasets, but no valid metric pairs"
            )
            self.graphs_compare_figure.tight_layout()
            self.graphs_compare_figure.savefig(scatter_plot, **save_kw)
            self.graphs_compare_canvas.draw_idle()
            self.graphs_compare_heatmap_figure.tight_layout()
            self.graphs_compare_heatmap_canvas.draw_idle()
            emb_ax.text(0.5, 0.5, "No embedding", ha="center", va="center")
            emb_ax.set_axis_off()
            self.graphs_compare_embedding_figure.tight_layout()
            self.graphs_compare_embedding_figure.savefig(embedding_plot, **save_kw)
            self.graphs_compare_embedding_canvas.draw_idle()
            return

        all_points = pd.concat(points_blocks, ignore_index=True)
        all_points.to_csv(points_csv, sep=";", index=False)
        palette = plt.cm.get_cmap("tab10", max(10, len(points_blocks)))
        grouped = list(all_points.groupby("dataset", sort=False))
        color_map = self._parse_graphs_compare_color_map([name for name, _ in grouped])

        for i, (dataset_name, group_df) in enumerate(grouped):
            color = color_map.get(dataset_name, palette(i % 10))
            ax_left.scatter(
                group_df["x"],
                group_df["y"],
                s=scatter_point_size,
                alpha=0.75,
                marker=scatter_marker,
                color=color,
                edgecolors="none",
                label=f"{dataset_name} (n={len(group_df)})",
            )

            if show_hulls:
                unique_xy = (
                    group_df[["x", "y"]]
                    .dropna()
                    .drop_duplicates()
                )
                if len(unique_xy) >= 3:
                    hull_geom = MultiPoint(unique_xy.to_numpy(dtype=float)).convex_hull
                    if hull_geom.geom_type == "Polygon":
                        hull_coords = np.asarray(hull_geom.exterior.coords)
                        if hull_outline_only:
                            ax_left.plot(
                                hull_coords[:, 0],
                                hull_coords[:, 1],
                                color=color,
                                linewidth=1.5,
                                alpha=max(hull_alpha, 0.25),
                                zorder=2,
                            )
                        else:
                            ax_left.fill(
                                hull_coords[:, 0],
                                hull_coords[:, 1],
                                facecolor=color,
                                edgecolor=color,
                                linewidth=1.1,
                                alpha=hull_alpha,
                                zorder=1,
                            )

            centroid_x = float(group_df["x"].mean())
            centroid_y = float(group_df["y"].mean())
            ax_left.scatter(
                [centroid_x],
                [centroid_y],
                s=120,
                marker="X",
                color=color,
                edgecolors="k",
                linewidths=0.7,
                zorder=5,
            )

        if log_x:
            ax_left.set_xscale("log")
        if log_y:
            ax_left.set_yscale("log")
        self._update_graphs_compare_scatter_labels()
        ax_left.grid(True, alpha=0.25, which="both" if (log_x or log_y) else "major")
        ax_left.legend(loc="best", fontsize=8)

        labels, distance_matrix = compute_scaled_centroid_distance_matrix(all_points)
        self._graphs_compare_heatmap_default_title = "Centroid distance matrix (unitless z-space)"
        self._graphs_compare_heatmap_default_xlabel = "Dataset"
        self._graphs_compare_heatmap_default_ylabel = "Dataset"
        if len(labels) < 2:
            ax_right.text(
                0.5,
                0.5,
                "Need at least 2 datasets with valid points",
                ha="center",
                va="center",
            )
            ax_right.set_axis_off()
            self.graphs_compare_heatmap_info_label.setText(
                "Distance matrix guide: add at least 2 datasets with valid metric points."
            )
        else:
            matrix_for_plot = distance_matrix
            if show_half_heatmap:
                mask = np.triu(np.ones_like(distance_matrix, dtype=bool), k=1)
                matrix_for_plot = np.ma.array(distance_matrix, mask=mask)

            heat = ax_right.imshow(matrix_for_plot, cmap="RdYlGn_r")
            ax_right.set_xticks(range(len(labels)))
            ax_right.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
            ax_right.set_yticks(range(len(labels)))
            ax_right.set_yticklabels(labels, fontsize=9)
            self.graphs_compare_colorbar = self.graphs_compare_heatmap_figure.colorbar(
                heat, ax=ax_right, fraction=0.046, pad=0.04
            )
            self.graphs_compare_colorbar.set_label("Distance (unitless)")

            for r in range(len(labels)):
                for c in range(len(labels)):
                    if show_half_heatmap and c > r:
                        continue
                    ax_right.text(
                        c,
                        r,
                        f"{distance_matrix[r, c]:.2f}",
                        ha="center",
                        va="center",
                        fontsize=8,
                    )

            min_val = None
            min_pair = None
            max_val = None
            max_pair = None
            for r, label_r in enumerate(labels):
                for c in range(r + 1, len(labels)):
                    val = float(distance_matrix[r, c])
                    if min_val is None or val < min_val:
                        min_val = val
                        min_pair = (label_r, labels[c])
                    if max_val is None or val > max_val:
                        max_val = val
                        max_pair = (label_r, labels[c])

            triu_idx = np.triu_indices(len(labels), k=1)
            off_diag = distance_matrix[triu_idx]
            mean_d = float(np.mean(off_diag)) if len(off_diag) > 0 else 1.0
            min_d = float(np.min(off_diag)) if len(off_diag) > 0 else 0.0
            max_d = float(np.max(off_diag)) if len(off_diag) > 0 else 0.0
            t1 = mean_d * 0.5
            t3 = mean_d * 1.5
            pair_line = ""
            if min_pair is not None and min_val is not None:
                pair_line = (
                    f"<br><br><b>Most similar:</b><br>"
                    f"{min_pair[0]} ~ {min_pair[1]}<br>"
                    f"dist = {min_val:.2f}"
                )
            far_pair_line = ""
            if max_pair is not None and max_val is not None:
                far_pair_line = (
                    f"<br><br><b>Least similar:</b><br>"
                    f"{max_pair[0]} ~ {max_pair[1]}<br>"
                    f"dist = {max_val:.2f}"
                )
            info_html = (
                "<b>Distance matrix</b><br>"
                "<small>z-score multi-metric space</small><br><br>"
                "<b>Summary (off-diagonal)</b><br>"
                f"Mean:&nbsp;{mean_d:.2f}<br>"
                f"Min:&nbsp;{min_d:.2f}&nbsp;<small>(closest)</small><br>"
                f"Max:&nbsp;{max_d:.2f}&nbsp;<small>(farthest)</small><br><br>"
                "<b>Similarity scale</b><br>"
                f"<span style='color:#1a9641'>&#9646;&nbsp;&lt;&nbsp;{t1:.2f}"
                f"&nbsp;&mdash;&nbsp;Very similar</span><br>"
                f"<span style='color:#78c679'>&#9646;&nbsp;{t1:.2f}&ndash;{mean_d:.2f}"
                f"&nbsp;&mdash;&nbsp;Similar</span><br>"
                f"<span style='color:#fe9929'>&#9646;&nbsp;{mean_d:.2f}&ndash;{t3:.2f}"
                f"&nbsp;&mdash;&nbsp;Different</span><br>"
                f"<span style='color:#d7191c'>&#9646;&nbsp;&gt;&nbsp;{t3:.2f}"
                f"&nbsp;&mdash;&nbsp;Very different</span>"
                f"{pair_line}"
                f"{far_pair_line}"
            )
            self.graphs_compare_heatmap_info_label.setText(info_html)
            self._update_graphs_compare_heatmap_labels()

        if len(labels) >= 1:
            matrix_df = pd.DataFrame(distance_matrix, index=labels, columns=labels)
            matrix_df.insert(0, "dataset", labels)
            matrix_df.to_csv(matrix_csv, sep=";", index=False)

        similarity_df = compute_similarity_report(frames_by_label)
        if not similarity_df.empty:
            self.graphs_compare_similarity_model.set_dataframe(similarity_df)
            self.graphs_compare_similarity_table.resizeColumnsToContents()
        similarity_df.to_csv(similarity_csv, sep=";", index=False)

        embedding_df = compute_dataset_embedding(
            frames_by_label,
            method=embedding_method,
            level=embedding_level,
        )
        embedding_meta = (
            embedding_df.attrs.get("metadata", {})
            if hasattr(embedding_df, "attrs")
            else {}
        )
        method_used = str(embedding_meta.get("method_used", embedding_method)).upper()
        loadings_df = embedding_meta.get("loadings_table")
        if isinstance(loadings_df, pd.DataFrame) and not loadings_df.empty:
            self.graphs_compare_loadings_model.set_dataframe(loadings_df)
            self.graphs_compare_loadings_table.resizeColumnsToContents()
            loadings_df.to_csv(loadings_csv, sep=";", index=False)
            self._render_loadings_barplot(loadings_df)
        else:
            pd.DataFrame().to_csv(loadings_csv, sep=";", index=False)
            for _ax in self.graphs_compare_loadings_axes:
                _ax.set_axis_off()
            self.graphs_compare_loadings_canvas.draw()
        if embedding_df.empty:
            emb_ax.text(
                0.5,
                0.5,
                f"No embedding for method {embedding_method}",
                ha="center",
                va="center",
            )
            emb_ax.set_axis_off()
            self.graphs_compare_embedding_info_label.setText(
                f"Embedding summary: no embedding available for {embedding_method}"
            )
            self._graphs_compare_embedding_default_title = (
                f"{embedding_level_text} embedding ({method_used}, multi-metric)"
            )
            self._graphs_compare_embedding_default_xlabel = "Component 1"
            self._graphs_compare_embedding_default_ylabel = "Component 2"
        else:
            emb_ax.set_axis_on()
            cmap = plt.cm.get_cmap("tab10", max(10, len(loaded_labels)))
            if embedding_level == "cone":
                for idx, dataset_name in enumerate(loaded_labels):
                    subset = embedding_df[embedding_df["dataset"].astype(str) == str(dataset_name)]
                    if subset.empty:
                        continue
                    color = color_map.get(str(dataset_name), cmap(idx % 10))
                    emb_ax.scatter(
                        subset["emb_x"],
                        subset["emb_y"],
                        s=embedding_point_size,
                        marker=embedding_marker,
                        color=color,
                        alpha=0.65,
                        edgecolors="k",
                        linewidths=0.3,
                        label=f"{dataset_name} (n={len(subset)})",
                    )
                    emb_ax.scatter(
                        [float(subset["emb_x"].mean())],
                        [float(subset["emb_y"].mean())],
                        s=max(120, embedding_point_size + 25),
                        marker="X",
                        color=color,
                        edgecolors="k",
                        linewidths=0.7,
                        zorder=5,
                    )
                    emb_ax.annotate(
                        str(dataset_name),
                        (float(subset["emb_x"].mean()), float(subset["emb_y"].mean())),
                        textcoords="offset points",
                        xytext=(6, 4),
                        fontsize=8,
                    )
                emb_ax.legend(loc="best", fontsize=8)
            else:
                for idx, row in embedding_df.reset_index(drop=True).iterrows():
                    label = str(row["dataset"])
                    color = color_map.get(label, cmap(idx % 10))
                    x = float(row["emb_x"])
                    y = float(row["emb_y"])
                    emb_ax.scatter(
                        [x],
                        [y],
                        s=embedding_point_size,
                        marker=embedding_marker,
                        color=color,
                        edgecolors="k",
                        linewidths=0.6,
                    )
                    emb_ax.annotate(
                        label,
                        (x, y),
                        textcoords="offset points",
                        xytext=(6, 4),
                        fontsize=8,
                    )
            self._graphs_compare_embedding_default_title = (
                f"{embedding_level_text} embedding ({method_used}, multi-metric)"
            )
            explained_ratio = embedding_meta.get("explained_variance_ratio", [])
            if method_used == "PCA" and len(explained_ratio) >= 2:
                self._graphs_compare_embedding_default_xlabel = (
                    f"Component 1 ({100.0 * float(explained_ratio[0]):.1f}% var)"
                )
                self._graphs_compare_embedding_default_ylabel = (
                    f"Component 2 ({100.0 * float(explained_ratio[1]):.1f}% var)"
                )
            else:
                self._graphs_compare_embedding_default_xlabel = "Component 1"
                self._graphs_compare_embedding_default_ylabel = "Component 2"
            self._update_graphs_compare_embedding_labels()
            emb_ax.grid(True, alpha=0.25)
            top_pc1 = embedding_meta.get("top_loadings_pc1", [])
            top_pc2 = embedding_meta.get("top_loadings_pc2", [])
            summary_parts = [f"Level: {embedding_level_text}", f"Method used: {method_used}"]
            if method_used != str(embedding_method).upper():
                summary_parts.append(f"fallback from: {str(embedding_method).upper()}")
            if method_used == "PCA" and len(explained_ratio) >= 2:
                summary_parts.append(
                    f"PC1={100.0 * float(explained_ratio[0]):.1f}%, "
                    f"PC2={100.0 * float(explained_ratio[1]):.1f}%"
                )
            if embedding_level == "cone":
                summary_parts.append(f"points={len(embedding_df)} cones")
            else:
                summary_parts.append(f"points={len(embedding_df)} datasets")
            if top_pc1:
                summary_parts.append(
                    "Top PC1 loadings: "
                    + ", ".join(
                        str(name).replace("__median", " median").replace("__iqr", " IQR")
                        for name in top_pc1[:3]
                    )
                )
            if top_pc2:
                summary_parts.append(
                    "Top PC2 loadings: "
                    + ", ".join(
                        str(name).replace("__median", " median").replace("__iqr", " IQR")
                        for name in top_pc2[:3]
                    )
                )
            self.graphs_compare_embedding_info_label.setText(
                "Embedding summary: " + " | ".join(summary_parts)
            )
        embedding_df.to_csv(embedding_csv, sep=";", index=False)

        failed_text = ""
        if failed:
            failed_text = " | Failed: " + " ; ".join(failed[:3])

        self.graphs_compare_source_label.setText(
            f"Loaded {len(loaded_frames)} datasets ({len(all_points)} points){failed_text}\n"
            f"Saved: {scatter_plot.name}, {heatmap_plot.name}, {embedding_plot.name}, "
            f"{similarity_csv.name}"
        )

        self.graphs_compare_figure.tight_layout()
        self.graphs_compare_figure.savefig(scatter_plot, **save_kw)
        self.graphs_compare_canvas.draw_idle()
        self.graphs_compare_heatmap_figure.tight_layout()
        self.graphs_compare_heatmap_figure.savefig(heatmap_plot, **save_kw)
        self.graphs_compare_heatmap_canvas.draw_idle()
        self.graphs_compare_embedding_figure.tight_layout()
        self.graphs_compare_embedding_figure.savefig(embedding_plot, **save_kw)
        self.graphs_compare_embedding_canvas.draw_idle()
