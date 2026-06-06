"""Mixin for the AppTabMixin section of MainWindow."""
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
    "n_transects",
    "rmse_height_settle_ratio",
    "rmse_height_ratio",
    "rmse_bottom_width_ratio",
    "rmse_bottom_elev_detrended",
    "rmse_bottom_elev",
    "rmse_center_to_top_diff",
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




class AppTabMixin:
    """Mixin — mixed into MainWindow via multiple inheritance."""

    def _build_project_group(self) -> QGroupBox:
        group = QGroupBox("Project")
        layout = QGridLayout(group)

        self.dev_root_edit = QLineEdit()
        self.base_path_edit = QLineEdit()
        self.python_edit = QLineEdit()
        self.dev_root_edit.setToolTip(
            "Root folder with generator-py, finder-py and analyzer-py modules used by the "
            "pipeline runner."
        )
        self.base_path_edit.setToolTip(
            "Dataset base folder (contains input and output subfolders used by all modules)."
        )
        self.python_edit.setToolTip(
            "Python interpreter used to execute pipeline scripts (recommended: selected conda "
            "env executable)."
        )

        layout.addWidget(QLabel("Dev root"), 0, 0)
        layout.addWidget(self.dev_root_edit, 0, 1)
        layout.addWidget(self._browse_button(self.dev_root_edit, True), 0, 2)

        layout.addWidget(QLabel("Base path"), 1, 0)
        layout.addWidget(self.base_path_edit, 1, 1)
        layout.addWidget(self._browse_button(self.base_path_edit, True), 1, 2)

        layout.addWidget(QLabel("Python executable"), 2, 0)
        layout.addWidget(self.python_edit, 2, 1)
        layout.addWidget(self._browse_button(self.python_edit, False), 2, 2)

        return group

    def _build_parameters_group(self) -> QGroupBox:
        group = QGroupBox("Parameters")
        layout = QHBoxLayout(group)

        generator_box = QGroupBox("Generator")
        generator_form = QFormLayout(generator_box)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["auto", "masks", "points"])
        self.mode_combo.setToolTip(
            "Generator input mode: auto detects source, masks uses polygon masks, points uses "
            "point seeds."
        )

        self.transect_length_spin = QSpinBox()
        self.transect_length_spin.setRange(1, 100000)
        self.transect_length_spin.setToolTip(
            "Total transect length in meters for each profile extracted around cone centers."
        )
        self.profile_resolution_spin = QSpinBox()
        self.profile_resolution_spin.setRange(1, 10000)
        self.profile_resolution_spin.setToolTip(
            "Sampling step along profiles in meters (smaller value = denser samples)."
        )
        self.buffer_width_spin = QSpinBox()
        self.buffer_width_spin.setRange(1, 100000)
        self.buffer_width_spin.setToolTip(
            "Half-width of profile extraction corridor in meters around each transect line. "
            "In practice, it can be set slightly larger than transect_length to keep a safe margin."
        )
        self.angle_step_spin = QDoubleSpinBox()
        self.angle_step_spin.setRange(0.001, 360.0)
        self.angle_step_spin.setDecimals(6)
        self.angle_step_spin.setSingleStep(0.125)
        self.angle_step_spin.setToolTip(
            "Angular spacing in degrees between transects (smaller step = more transects)."
        )

        generator_form.addRow("Mode", self.mode_combo)
        generator_form.addRow("Transect length", self.transect_length_spin)
        generator_form.addRow("Profile resolution", self.profile_resolution_spin)
        generator_form.addRow("Buffer width", self.buffer_width_spin)
        generator_form.addRow("Angle step", self.angle_step_spin)

        crs_box = QGroupBox("CRS")
        crs_form = QFormLayout(crs_box)
        self.crs_mode_combo = QComboBox()
        self.crs_mode_combo.addItems(["auto", "manual"])
        self.crs_mode_combo.setToolTip(
            "CRS mode: auto reads CRS from selected data source, manual uses value provided below."
        )
        self.crs_source_combo = QComboBox()
        self.crs_source_combo.addItems(["dem", "masks", "points"])
        self.crs_source_combo.setToolTip("Preferred source used for automatic CRS detection.")
        self.manual_crs_edit = QLineEdit()
        self.manual_crs_edit.setToolTip(
            "Manual CRS definition (for example EPSG:32633 or a full PROJ string)."
        )
        self.ignore_celestial_body_check = QCheckBox("Set PROJ_IGNORE_CELESTIAL_BODY=YES")
        self.ignore_celestial_body_check.setToolTip(
            "Allows CRS transforms between different celestial bodies "
            "(use only when you understand implications)."
        )
        self.detect_crs_button = QPushButton("Preview resolved CRS")
        self.detect_crs_button.setToolTip(
            "Preview the CRS that will be used by the current settings before running modules."
        )
        self.detect_crs_button.clicked.connect(self._preview_crs)

        crs_form.addRow("Mode", self.crs_mode_combo)
        crs_form.addRow("Auto source", self.crs_source_combo)
        crs_form.addRow("Manual CRS", self.manual_crs_edit)
        crs_form.addRow(self.ignore_celestial_body_check)
        crs_form.addRow(self.detect_crs_button)

        finder_box = QGroupBox("Finder")
        finder_form = QFormLayout(finder_box)
        self.finder_smoothing_enabled_check = QCheckBox("Enable profile smoothing")
        self.finder_smoothing_enabled_check.setToolTip(
            "Enable Savitzky-Golay smoothing before feature detection in Finder."
        )
        self.finder_smoothing_enabled_check.toggled.connect(self._update_finder_smoothing_ui)
        self.finder_smoothing_window_spin = QDoubleSpinBox()
        self.finder_smoothing_window_spin.setRange(1.0, 10000.0)
        self.finder_smoothing_window_spin.setSingleStep(10.0)
        self.finder_smoothing_window_spin.setSuffix(" m")
        self.finder_smoothing_window_spin.setToolTip(
            "Smoothing window length in meters (larger window = stronger smoothing)."
        )
        self.finder_smoothing_polyorder_spin = QSpinBox()
        self.finder_smoothing_polyorder_spin.setRange(1, 7)
        self.finder_smoothing_polyorder_spin.setToolTip(
            "Savitzky-Golay polynomial order (must be lower than effective window sample count)."
        )

        finder_form.addRow(self.finder_smoothing_enabled_check)
        finder_form.addRow("Smoothing window", self.finder_smoothing_window_spin)
        finder_form.addRow("SavGol polyorder", self.finder_smoothing_polyorder_spin)

        self.finder_edge_guard_spin = QDoubleSpinBox()
        self.finder_edge_guard_spin.setRange(0.0, 0.5)
        self.finder_edge_guard_spin.setSingleStep(0.01)
        self.finder_edge_guard_spin.setDecimals(2)
        self.finder_edge_guard_spin.setToolTip(
            "Fraction of the outer segment treated as edge zone (0 = disabled, "
            "default 0.12). Prevents bottom points from being placed at the "
            "very end of the transect."
        )
        finder_form.addRow("Bottom edge guard", self.finder_edge_guard_spin)

        analyzer_box = QGroupBox("Analyzer")
        analyzer_form = QFormLayout(analyzer_box)
        self.shape_threshold_spin = QDoubleSpinBox()
        self.shape_threshold_spin.setRange(0.0, 9999.0)
        self.shape_threshold_spin.setSingleStep(0.1)
        self.shape_threshold_spin.setToolTip(
            "Shape classification threshold used to separate flat, concave and convex profiles."
        )
        self.buffer_distance_spin = QDoubleSpinBox()
        self.buffer_distance_spin.setRange(0.0, 9999.0)
        self.buffer_distance_spin.setSingleStep(0.1)
        self.buffer_distance_spin.setToolTip(
            "Analyzer buffer distance in meters used for geometry operations on detected cone "
            "points."
        )
        self.quality_preset_combo = QComboBox()
        self.quality_preset_combo.addItems(["mars", "terrestrial", "bathymetry"])
        self.quality_preset_combo.setToolTip(
            "Preset of quality thresholds adapted to target environment."
        )
        self.quality_n_transects_min_spin = QSpinBox()
        self.quality_n_transects_min_spin.setRange(1, 360)
        self.quality_n_transects_min_spin.setToolTip(
            "Minimum number of transects required for reliable quality assessment."
        )
        self.quality_height_mid_spin = QDoubleSpinBox()
        self.quality_height_mid_spin.setRange(0.0, 2.0)
        self.quality_height_mid_spin.setDecimals(3)
        self.quality_height_mid_spin.setSingleStep(0.01)
        self.quality_height_mid_spin.setToolTip("Moderate-warning threshold for RMSE height ratio.")
        self.quality_height_high_spin = QDoubleSpinBox()
        self.quality_height_high_spin.setRange(0.0, 2.0)
        self.quality_height_high_spin.setDecimals(3)
        self.quality_height_high_spin.setSingleStep(0.01)
        self.quality_height_high_spin.setToolTip("High-warning threshold for RMSE height ratio.")
        self.quality_bottom_width_mid_spin = QDoubleSpinBox()
        self.quality_bottom_width_mid_spin.setRange(0.0, 2.0)
        self.quality_bottom_width_mid_spin.setDecimals(3)
        self.quality_bottom_width_mid_spin.setSingleStep(0.01)
        self.quality_bottom_width_mid_spin.setToolTip(
            "Moderate-warning threshold for RMSE bottom-width ratio."
        )
        self.quality_bottom_width_high_spin = QDoubleSpinBox()
        self.quality_bottom_width_high_spin.setRange(0.0, 2.0)
        self.quality_bottom_width_high_spin.setDecimals(3)
        self.quality_bottom_width_high_spin.setSingleStep(0.01)
        self.quality_bottom_width_high_spin.setToolTip(
            "High-warning threshold for RMSE bottom-width ratio."
        )
        self.quality_bottom_rmse_mid_spin = QDoubleSpinBox()
        self.quality_bottom_rmse_mid_spin.setRange(0.0, 1000.0)
        self.quality_bottom_rmse_mid_spin.setDecimals(3)
        self.quality_bottom_rmse_mid_spin.setSingleStep(0.5)
        self.quality_bottom_rmse_mid_spin.setToolTip(
            "Moderate-warning threshold for detrended bottom-elevation RMSE in meters."
        )
        self.quality_bottom_rmse_high_spin = QDoubleSpinBox()
        self.quality_bottom_rmse_high_spin.setRange(0.0, 1000.0)
        self.quality_bottom_rmse_high_spin.setDecimals(3)
        self.quality_bottom_rmse_high_spin.setSingleStep(0.5)
        self.quality_bottom_rmse_high_spin.setToolTip(
            "High-warning threshold for detrended bottom-elevation RMSE in meters."
        )
        self.quality_center_top_mid_spin = QDoubleSpinBox()
        self.quality_center_top_mid_spin.setRange(0.0, 1000.0)
        self.quality_center_top_mid_spin.setDecimals(3)
        self.quality_center_top_mid_spin.setSingleStep(0.5)
        self.quality_center_top_mid_spin.setToolTip(
            "Moderate-warning threshold for center-to-top RMSE in meters."
        )
        self.quality_center_top_high_spin = QDoubleSpinBox()
        self.quality_center_top_high_spin.setRange(0.0, 1000.0)
        self.quality_center_top_high_spin.setDecimals(3)
        self.quality_center_top_high_spin.setSingleStep(0.5)
        self.quality_center_top_high_spin.setToolTip(
            "High-warning threshold for center-to-top RMSE in meters."
        )

        # QA thresholds modal dialog
        self._qa_dialog = QDialog(self)
        self._qa_dialog.setWindowTitle("QA Thresholds")
        _dlg_layout = QVBoxLayout(self._qa_dialog)
        _dlg_form = QFormLayout()
        _dlg_form.addRow("Min transects", self.quality_n_transects_min_spin)
        _dlg_form.addRow("Height ratio mid", self.quality_height_mid_spin)
        _dlg_form.addRow("Height ratio high", self.quality_height_high_spin)
        _dlg_form.addRow("Width ratio mid", self.quality_bottom_width_mid_spin)
        _dlg_form.addRow("Width ratio high", self.quality_bottom_width_high_spin)
        _dlg_form.addRow("Bottom RMSE mid", self.quality_bottom_rmse_mid_spin)
        _dlg_form.addRow("Bottom RMSE high", self.quality_bottom_rmse_high_spin)
        _dlg_form.addRow("Center-top RMSE mid", self.quality_center_top_mid_spin)
        _dlg_form.addRow("Center-top RMSE high", self.quality_center_top_high_spin)
        _dlg_layout.addLayout(_dlg_form)
        _dlg_btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        _dlg_btns.accepted.connect(self._qa_dialog.accept)
        _dlg_btns.rejected.connect(self._qa_dialog.reject)
        _dlg_layout.addWidget(_dlg_btns)

        self.use_manual_fix_check = QCheckBox("Use manual fix")
        self.use_manual_fix_check.setToolTip(
            "Use saved manual point overrides (if available) when running Analyzer and loading "
            "results."
        )
        self.use_manual_fix_check.toggled.connect(lambda _checked: self._update_results_path())
        self.export_geojson_check = QCheckBox("Export GeoJSON")
        self.export_geojson_check.setToolTip(
            "Export per-transect GeoJSON diagnostics from Analyzer."
        )
        self.export_summary_gpkg_check = QCheckBox("Export summary GPKG")
        self.export_summary_gpkg_check.setToolTip(
            "Export summary GeoPackage layers (cones, centers, top/bottom points)."
        )

        # Quality preset row with "Set QA" button to open the modal dialog for editing thresholds
        self.set_qa_button = QPushButton("Set QA...")
        self.set_qa_button.setToolTip(
            "Open dialog to edit all quality-threshold values for the selected preset."
        )
        self.set_qa_button.clicked.connect(self._open_qa_dialog)
        self.quality_preset_combo.currentTextChanged.connect(self._on_quality_preset_changed)
        _qa_preset_widget = QWidget()
        _qa_preset_layout = QHBoxLayout(_qa_preset_widget)
        _qa_preset_layout.setContentsMargins(0, 0, 0, 0)
        _qa_preset_layout.addWidget(self.quality_preset_combo)
        _qa_preset_layout.addWidget(self.set_qa_button)

        analyzer_form.addRow("Shape threshold", self.shape_threshold_spin)
        analyzer_form.addRow("Buffer distance", self.buffer_distance_spin)
        analyzer_form.addRow("Quality preset", _qa_preset_widget)
        analyzer_form.addRow(self.use_manual_fix_check)
        analyzer_form.addRow(self.export_geojson_check)
        analyzer_form.addRow(self.export_summary_gpkg_check)

        layout.addWidget(generator_box)
        layout.addWidget(crs_box)
        layout.addWidget(finder_box)
        layout.addWidget(analyzer_box)
        layout.setStretch(0, 2)
        layout.setStretch(1, 5)
        layout.setStretch(2, 3)
        layout.setStretch(3, 2)
        return group

    def _build_actions_row(self) -> QHBoxLayout:
        layout = QHBoxLayout()

        self.save_button = QPushButton("Save settings")
        self.read_data_button = QPushButton("Read data")
        self.validate_button = QPushButton("Validate paths")
        self.run_generator_button = QPushButton("Run generator")
        self.run_finder_button = QPushButton("Run finder")
        self.run_analyzer_button = QPushButton("Run analyzer")
        self.run_full_button = QPushButton("Run full pipeline")
        self.stop_button = QPushButton("Stop")

        self.save_button.clicked.connect(self._save_settings)
        self.read_data_button.clicked.connect(self._read_existing_data)
        self.validate_button.clicked.connect(self._validate_paths)
        self.run_generator_button.clicked.connect(lambda: self._run_modules(["generator"]))
        self.run_finder_button.clicked.connect(lambda: self._run_modules(["finder"]))
        self.run_analyzer_button.clicked.connect(lambda: self._run_modules(["analyzer"]))
        self.run_full_button.clicked.connect(
            lambda: self._run_modules(["generator", "finder", "analyzer"])
        )
        self.stop_button.clicked.connect(self._stop_all)

        for button in [
            self.save_button,
            self.read_data_button,
            self.validate_button,
            self.run_generator_button,
            self.run_finder_button,
            self.run_analyzer_button,
            self.run_full_button,
            self.stop_button,
        ]:
            layout.addWidget(button)

        return layout

    def _build_results_group(self) -> QGroupBox:
        group = QGroupBox("Results")
        layout = QVBoxLayout(group)
        top_row = QHBoxLayout()

        self.results_path_edit = QLineEdit()
        self.results_path_edit.setReadOnly(True)
        self.refresh_results_button = QPushButton("Refresh results")
        self.refresh_results_button.clicked.connect(self._load_results)

        top_row.addWidget(QLabel("Analyzer CSV"))
        top_row.addWidget(self.results_path_edit)
        top_row.addWidget(self.refresh_results_button)

        self.results_table = QTableView()
        self.results_table.setModel(self.results_model)
        self.results_table.horizontalHeader().setStretchLastSection(False)

        layout.addLayout(top_row)
        layout.addWidget(self.results_table)
        return group

    def _build_logs_group(self) -> QGroupBox:
        group = QGroupBox("Logs")
        layout = QVBoxLayout(group)
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setLineWrapMode(QPlainTextEdit.NoWrap)
        layout.addWidget(self.log_output)
        return group

    def _build_input_diagnostics_group(self) -> QGroupBox:
        group = QGroupBox("Input diagnostics")
        layout = QVBoxLayout(group)
        top_row = QHBoxLayout()

        self.refresh_diagnostics_button = QPushButton("Refresh diagnostics")
        self.refresh_diagnostics_button.clicked.connect(self._refresh_input_diagnostics)
        top_row.addWidget(self.refresh_diagnostics_button)
        top_row.addStretch(1)

        self.diagnostics_output = QPlainTextEdit()
        self.diagnostics_output.setReadOnly(True)
        self.diagnostics_output.setLineWrapMode(QPlainTextEdit.NoWrap)

        layout.addLayout(top_row)
        layout.addWidget(self.diagnostics_output)
        return group

    def _bind_runner_signals(self) -> None:
        self.runner.log_emitted.connect(self._append_log)
        self.runner.status_changed.connect(self.statusBar().showMessage)
        self.runner.pipeline_finished.connect(self._on_pipeline_finished)
        self.runner.module_finished.connect(self._on_module_finished)

    def _apply_state_to_form(self) -> None:
        self.dev_root_edit.setText(self.state["dev_root"])
        self.base_path_edit.setText(self.state["base_path"])
        self.python_edit.setText(self.state["python_executable"])

        generator = self.state["generator"]
        finder = self.state["finder"]
        analyzer = self.state["analyzer"]
        crs = self.state["crs"]

        self.mode_combo.setCurrentText(generator["mode"])
        self.transect_length_spin.setValue(generator["transect_length"])
        self.profile_resolution_spin.setValue(generator["profile_resolution"])
        self.buffer_width_spin.setValue(generator["buffer_width"])
        self.angle_step_spin.setValue(generator["transect_angle_step"])

        self.finder_smoothing_enabled_check.setChecked(finder.get("smoothing_enabled", False))
        self.finder_smoothing_window_spin.setValue(finder.get("smoothing_window_m", 120.0))
        self.finder_smoothing_polyorder_spin.setValue(finder.get("smoothing_polyorder", 2))
        self.finder_edge_guard_spin.setValue(finder.get("bottom_edge_guard_frac", 0.12))
        self._update_finder_smoothing_ui()

        self.shape_threshold_spin.setValue(analyzer["shape_threshold"])
        self.buffer_distance_spin.setValue(analyzer["buffer_distance"])
        self.quality_preset_combo.setCurrentText(analyzer.get("quality_preset", "terrestrial"))
        quality_thresholds = analyzer.get("quality_thresholds", {})
        self.quality_n_transects_min_spin.setValue(
            int(quality_thresholds.get("n_transects_min", 6))
        )
        self.quality_height_mid_spin.setValue(
            float(quality_thresholds.get("height_ratio_mid", 0.12))
        )
        self.quality_height_high_spin.setValue(
            float(quality_thresholds.get("height_ratio_high", 0.25))
        )
        self.quality_bottom_width_mid_spin.setValue(
            float(quality_thresholds.get("bottom_width_ratio_mid", 0.15))
        )
        self.quality_bottom_width_high_spin.setValue(
            float(quality_thresholds.get("bottom_width_ratio_high", 0.35))
        )
        self.quality_bottom_rmse_mid_spin.setValue(
            float(quality_thresholds.get("bottom_elev_rmse_mid", 12.0))
        )
        self.quality_bottom_rmse_high_spin.setValue(
            float(quality_thresholds.get("bottom_elev_rmse_high", 35.0))
        )
        self.quality_center_top_mid_spin.setValue(
            float(quality_thresholds.get("center_top_rmse_mid", 10.0))
        )
        self.quality_center_top_high_spin.setValue(
            float(quality_thresholds.get("center_top_rmse_high", 20.0))
        )
        self.use_manual_fix_check.setChecked(analyzer.get("use_manual_fix", False))
        self.export_geojson_check.setChecked(analyzer["export_geojson"])
        self.export_summary_gpkg_check.setChecked(analyzer["export_summary_gpkg"])
        self.crs_mode_combo.setCurrentText(crs["mode"])
        self.crs_source_combo.setCurrentText(crs["source"])
        self.manual_crs_edit.setText(crs["manual_value"])
        self.ignore_celestial_body_check.setChecked(crs["ignore_celestial_body"])

        cross_section = self.state["cross_section"]
        self.cs_profile_dir_edit.setText(cross_section["profile_dir"])
        self.cs_finder_path_edit.setText(cross_section["finder_path"])
        self.cs_output_dir_edit.setText(cross_section["output_dir"])
        self.cs_cone_ids_edit.setText(cross_section["cone_ids"])
        self.cs_dpi_spin.setValue(cross_section["dpi"])
        self.cs_angle_tol_spin.setValue(cross_section["angle_tolerance_deg"])

        dem_overlay = self.state["dem_overlay"]
        self.dem_overlay_dem_dir_edit.setText(dem_overlay["dem_dir"])
        self.dem_overlay_gpkg_edit.setText(dem_overlay["gpkg_path"])
        self.dem_overlay_output_dir_edit.setText(dem_overlay["output_dir"])
        self.dem_overlay_centers_hybrid_edit.setText(dem_overlay.get("centers_hybrid_path", ""))
        self.dem_overlay_cone_ids_edit.setText(dem_overlay["cone_ids"])
        self.dem_overlay_use_manual_fix_check.setChecked(dem_overlay.get("use_manual_fix", False))
        self.dem_overlay_dpi_spin.setValue(dem_overlay["dpi"])
        self.dem_overlay_azimuth_spin.setValue(dem_overlay["azimuth_deg"])
        self.dem_overlay_altitude_spin.setValue(dem_overlay["altitude_deg"])

        dataset_compare = self.state.get("dataset_compare", {})
        self.graphs_compare_show_hulls_check.setChecked(
            bool(dataset_compare.get("show_hulls", False))
        )
        self.graphs_compare_hull_style_combo.setCurrentText(
            str(dataset_compare.get("hull_style", "Fill + outline"))
        )
        self.graphs_compare_hull_alpha_spin.setValue(
            float(dataset_compare.get("hull_alpha", 0.14))
        )
        self.graphs_compare_show_reference_rows_check.setChecked(
            bool(dataset_compare.get("show_reference_rows", False))
        )
        self.graphs_compare_scatter_title_edit.setText(
            str(dataset_compare.get("scatter_title", ""))
        )
        self.graphs_compare_scatter_xlabel_edit.setText(
            str(dataset_compare.get("scatter_xlabel", ""))
        )
        self.graphs_compare_scatter_ylabel_edit.setText(
            str(dataset_compare.get("scatter_ylabel", ""))
        )
        self.graphs_compare_heatmap_title_edit.setText(
            str(dataset_compare.get("heatmap_title", ""))
        )
        self.graphs_compare_heatmap_xlabel_edit.setText(
            str(dataset_compare.get("heatmap_xlabel", ""))
        )
        self.graphs_compare_heatmap_ylabel_edit.setText(
            str(dataset_compare.get("heatmap_ylabel", ""))
        )
        self.graphs_compare_heatmap_half_check.setChecked(
            bool(dataset_compare.get("heatmap_half_matrix", False))
        )
        self.graphs_compare_embedding_title_edit.setText(
            str(dataset_compare.get("embedding_title", ""))
        )
        self.graphs_compare_embedding_xlabel_edit.setText(
            str(dataset_compare.get("embedding_xlabel", ""))
        )
        self.graphs_compare_embedding_ylabel_edit.setText(
            str(dataset_compare.get("embedding_ylabel", ""))
        )
        self.graphs_compare_export_format_combo.setCurrentText(
            str(dataset_compare.get("export_format", "PNG"))
        )
        sources_text = str(dataset_compare.get("sources_text", "")).strip()
        if sources_text:
            self.graphs_compare_sources_edit.setPlainText(sources_text)
        else:
            current_base = self.base_path_edit.text().strip()
            if current_base:
                self.graphs_compare_sources_edit.setPlainText(f"Current;{current_base}")
            else:
                self.graphs_compare_sources_edit.setPlainText("")
        self.graphs_compare_colors_edit.setPlainText(
            str(dataset_compare.get("colors_text", "")).strip()
        )
        self.graphs_compare_x_combo.setCurrentText(str(dataset_compare.get("x_metric", "Wco")))
        self.graphs_compare_y_combo.setCurrentText(
            str(dataset_compare.get("y_metric", "WCR_WCO_ratio"))
        )
        self.graphs_compare_use_manual_fix_check.setChecked(
            bool(dataset_compare.get("use_manual_fix", self.use_manual_fix_check.isChecked()))
        )
        self.graphs_compare_embedding_method_combo.setCurrentText(
            str(dataset_compare.get("embedding_method", "PCA"))
        )
        self.graphs_compare_embedding_level_combo.setCurrentText(
            str(dataset_compare.get("embedding_level", "Dataset level"))
        )
        self.graphs_compare_scatter_point_size_spin.setValue(
            int(dataset_compare.get("scatter_point_size", 28))
        )
        self.graphs_compare_scatter_marker_combo.setCurrentText(
            str(dataset_compare.get("scatter_marker", "o"))
        )
        self.graphs_compare_embedding_point_size_spin.setValue(
            int(dataset_compare.get("embedding_point_size", 90))
        )
        self.graphs_compare_embedding_marker_combo.setCurrentText(
            str(dataset_compare.get("embedding_marker", "o"))
        )

        self._update_results_path()
        self._refresh_input_diagnostics()
        self._refresh_cross_section_preview(reset_to_first=True)
        self._refresh_dem_overlay_preview(reset_to_first=True)
        self._complex_load_saved_definitions(show_message=False)
        self._breach_load_saved_singles(show_message=False)
        self._complex_recompute_outputs(show_message=False)

    def _collect_state_from_form(self) -> dict:
        return {
            "dev_root": self.dev_root_edit.text().strip(),
            "base_path": self.base_path_edit.text().strip(),
            "python_executable": self.python_edit.text().strip(),
            "crs": {
                "mode": self.crs_mode_combo.currentText(),
                "source": self.crs_source_combo.currentText(),
                "manual_value": self.manual_crs_edit.text().strip(),
                "ignore_celestial_body": self.ignore_celestial_body_check.isChecked(),
            },
            "generator": {
                "mode": self.mode_combo.currentText(),
                "transect_length": self.transect_length_spin.value(),
                "profile_resolution": self.profile_resolution_spin.value(),
                "buffer_width": self.buffer_width_spin.value(),
                "transect_angle_step": self.angle_step_spin.value(),
            },
            "finder": {
                "smoothing_enabled": self.finder_smoothing_enabled_check.isChecked(),
                "smoothing_window_m": self.finder_smoothing_window_spin.value(),
                "smoothing_polyorder": self.finder_smoothing_polyorder_spin.value(),
                "bottom_edge_guard_frac": self.finder_edge_guard_spin.value(),
            },
            "analyzer": {
                "shape_threshold": self.shape_threshold_spin.value(),
                "buffer_distance": self.buffer_distance_spin.value(),
                "quality_preset": self.quality_preset_combo.currentText(),
                "quality_thresholds": {
                    "n_transects_min": self.quality_n_transects_min_spin.value(),
                    "height_ratio_mid": self.quality_height_mid_spin.value(),
                    "height_ratio_high": self.quality_height_high_spin.value(),
                    "bottom_width_ratio_mid": self.quality_bottom_width_mid_spin.value(),
                    "bottom_width_ratio_high": self.quality_bottom_width_high_spin.value(),
                    "bottom_elev_rmse_mid": self.quality_bottom_rmse_mid_spin.value(),
                    "bottom_elev_rmse_high": self.quality_bottom_rmse_high_spin.value(),
                    "center_top_rmse_mid": self.quality_center_top_mid_spin.value(),
                    "center_top_rmse_high": self.quality_center_top_high_spin.value(),
                },
                "use_manual_fix": self.use_manual_fix_check.isChecked(),
                "export_geojson": self.export_geojson_check.isChecked(),
                "export_summary_gpkg": self.export_summary_gpkg_check.isChecked(),
            },
            "cross_section": {
                "profile_dir": self.cs_profile_dir_edit.text().strip(),
                "finder_path": self.cs_finder_path_edit.text().strip(),
                "output_dir": self.cs_output_dir_edit.text().strip(),
                "cone_ids": self.cs_cone_ids_edit.text().strip(),
                "dpi": self.cs_dpi_spin.value(),
                "angle_tolerance_deg": self.cs_angle_tol_spin.value(),
            },
            "dem_overlay": {
                "dem_dir": self.dem_overlay_dem_dir_edit.text().strip(),
                "gpkg_path": self.dem_overlay_gpkg_edit.text().strip(),
                "output_dir": self.dem_overlay_output_dir_edit.text().strip(),
                "centers_hybrid_path": self.dem_overlay_centers_hybrid_edit.text().strip(),
                "cone_ids": self.dem_overlay_cone_ids_edit.text().strip(),
                "use_manual_fix": self.dem_overlay_use_manual_fix_check.isChecked(),
                "dpi": self.dem_overlay_dpi_spin.value(),
                "azimuth_deg": self.dem_overlay_azimuth_spin.value(),
                "altitude_deg": self.dem_overlay_altitude_spin.value(),
            },
            "dataset_compare": {
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
            },
        }

    def _update_finder_smoothing_ui(self) -> None:
        enabled = self.finder_smoothing_enabled_check.isChecked()
        self.finder_smoothing_window_spin.setEnabled(enabled)
        self.finder_smoothing_polyorder_spin.setEnabled(enabled)

    def _on_quality_preset_changed(self, preset: str) -> None:
        vals = _QA_PRESETS.get(preset, _QA_PRESETS["terrestrial"])
        self.quality_n_transects_min_spin.setValue(int(vals["n_transects_min"]))
        self.quality_height_mid_spin.setValue(float(vals["height_ratio_mid"]))
        self.quality_height_high_spin.setValue(float(vals["height_ratio_high"]))
        self.quality_bottom_width_mid_spin.setValue(float(vals["bottom_width_ratio_mid"]))
        self.quality_bottom_width_high_spin.setValue(float(vals["bottom_width_ratio_high"]))
        self.quality_bottom_rmse_mid_spin.setValue(float(vals["bottom_elev_rmse_mid"]))
        self.quality_bottom_rmse_high_spin.setValue(float(vals["bottom_elev_rmse_high"]))
        self.quality_center_top_mid_spin.setValue(float(vals["center_top_rmse_mid"]))
        self.quality_center_top_high_spin.setValue(float(vals["center_top_rmse_high"]))

    def _open_qa_dialog(self) -> None:
        snapshot = {
            "n_transects_min": self.quality_n_transects_min_spin.value(),
            "height_ratio_mid": self.quality_height_mid_spin.value(),
            "height_ratio_high": self.quality_height_high_spin.value(),
            "bottom_width_ratio_mid": self.quality_bottom_width_mid_spin.value(),
            "bottom_width_ratio_high": self.quality_bottom_width_high_spin.value(),
            "bottom_elev_rmse_mid": self.quality_bottom_rmse_mid_spin.value(),
            "bottom_elev_rmse_high": self.quality_bottom_rmse_high_spin.value(),
            "center_top_rmse_mid": self.quality_center_top_mid_spin.value(),
            "center_top_rmse_high": self.quality_center_top_high_spin.value(),
        }
        result = self._qa_dialog.exec()
        if result == QDialog.Rejected:
            self.quality_n_transects_min_spin.setValue(int(snapshot["n_transects_min"]))
            self.quality_height_mid_spin.setValue(snapshot["height_ratio_mid"])
            self.quality_height_high_spin.setValue(snapshot["height_ratio_high"])
            self.quality_bottom_width_mid_spin.setValue(snapshot["bottom_width_ratio_mid"])
            self.quality_bottom_width_high_spin.setValue(snapshot["bottom_width_ratio_high"])
            self.quality_bottom_rmse_mid_spin.setValue(snapshot["bottom_elev_rmse_mid"])
            self.quality_bottom_rmse_high_spin.setValue(snapshot["bottom_elev_rmse_high"])
            self.quality_center_top_mid_spin.setValue(snapshot["center_top_rmse_mid"])
            self.quality_center_top_high_spin.setValue(snapshot["center_top_rmse_high"])

    def _save_settings(self) -> None:
        self.state = self._collect_state_from_form()
        save_state(self.mvp_root, self.state)
        self._update_results_path()
        self._refresh_input_diagnostics()
        self.statusBar().showMessage("Settings saved.", 4000)

    def _read_existing_data(self) -> None:
        # Load existing outputs for current base path without running pipeline.
        self._update_results_path()

        loaded_any = False
        csv_path = Path(self.results_path_edit.text())
        if csv_path.exists():
            self._load_results()
            loaded_any = True

        self._read_cross_section_data(show_message=False)
        self._read_dem_overlay_data(show_message=False)

        if loaded_any:
            self.statusBar().showMessage("Read data: existing outputs loaded.", 5000)
        else:
            self.statusBar().showMessage(
                "Read data: no cone_summary.csv in current base path.", 5000
            )

    def _validate_paths(self) -> None:
        state = self._collect_state_from_form()
        problems = []

        dev_root = Path(state["dev_root"])
        base_path = Path(state["base_path"])
        python_path = Path(state["python_executable"])

        if not dev_root.exists():
            problems.append(f"Dev root not found: {dev_root}")
        for module_dir in ["generator-py", "finder-py", "analyzer-py"]:
            if not (dev_root / module_dir / "main.py").exists():
                problems.append(f"Missing module entrypoint: {dev_root / module_dir / 'main.py'}")
        if not base_path.exists():
            problems.append(f"Base path not found: {base_path}")
        if self.python_edit.text().strip() and not python_path.exists():
            problems.append(f"Python executable not found: {python_path}")
        try:
            self._resolve_crs_text(state)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            problems.append(f"CRS resolution failed: {exc}")

        if problems:
            QMessageBox.warning(self, "Validation failed", "\n".join(problems))
            return

        QMessageBox.information(self, "Validation", "Paths look valid.")

    def _run_modules(self, modules: list[str]) -> None:
        self.state = self._collect_state_from_form()
        save_state(self.mvp_root, self.state)
        self._update_results_path()
        self._refresh_input_diagnostics()
        self.runner.run_modules(modules, self.state)

    def _update_results_path(self) -> None:
        summary_name = (
            "fix_cone_summary.csv" if self.use_manual_fix_check.isChecked() else "cone_summary.csv"
        )
        csv_path = Path(self.base_path_edit.text().strip()) / "output" / "analyzer" / summary_name
        self.results_path_edit.setText(str(csv_path))

    def _load_results(self) -> None:
        csv_path = Path(self.results_path_edit.text())
        if not csv_path.exists():
            QMessageBox.information(self, "Results", f"Results file not found:\n{csv_path}")
            return

        dataframe = pd.read_csv(csv_path, sep=";")
        visible_columns = [column for column in SUMMARY_COLUMNS if column in dataframe.columns]
        if visible_columns:
            dataframe = dataframe[visible_columns]
        self.results_model.set_dataframe(dataframe)
        self.results_table.resizeColumnsToContents()
        self.statusBar().showMessage("Results loaded.", 4000)

    def _append_log(self, text: str) -> None:
        self.log_output.appendPlainText(text)
        self.log_output.verticalScrollBar().setValue(self.log_output.verticalScrollBar().maximum())

    def resizeEvent(self, event) -> None:  # pylint: disable=invalid-name
        super().resizeEvent(event)
        if self.cross_section_current_pixmap is not None:
            scaled = self.cross_section_current_pixmap.scaled(
                self.cs_preview_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.cs_preview_label.setPixmap(scaled)
        if self.dem_overlay_current_pixmap is not None:
            scaled = self.dem_overlay_current_pixmap.scaled(
                self.dem_overlay_preview_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.dem_overlay_preview_label.setPixmap(scaled)
        if self.dem_overlay_context_current_pixmap is not None:
            scaled = self.dem_overlay_context_current_pixmap.scaled(
                self.dem_overlay_context_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self.dem_overlay_context_label.setPixmap(scaled)

    def _preview_crs(self) -> None:
        self.state = self._collect_state_from_form()
        try:
            text = self._resolve_crs_text(self.state)
            QMessageBox.information(self, "Resolved CRS", text)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            QMessageBox.warning(self, "Resolved CRS", f"Unavailable: {exc}")

    def _resolve_crs_text(self, state: dict) -> str:
        return describe_resolved_crs(state)

    def _refresh_input_diagnostics(self) -> None:
        base_path = Path(self.base_path_edit.text().strip())
        lines = [f"Base path: {base_path}"]

        if not base_path.exists():
            lines.append("Base path does not exist.")
            self.diagnostics_output.setPlainText("\n".join(lines))
            return

        lines.extend(self._diagnose_dem(base_path))
        lines.extend(self._diagnose_vectors(base_path, "crop", "Masks"))
        lines.extend(self._diagnose_vectors(base_path, "points", "Points"))

        self.diagnostics_output.setPlainText("\n".join(lines))

    def _diagnose_dem(self, base_path: Path) -> list[str]:
        dem_dir = base_path / "input" / "dem"
        lines = ["", f"DEM folder: {dem_dir}"]
        if not dem_dir.exists():
            lines.append("  Missing folder")
            return lines

        tif_files = sorted(
            list(dem_dir.glob("*.tif"))
            + list(dem_dir.glob("*.tiff"))
            + list(dem_dir.glob("*.TIF"))
            + list(dem_dir.glob("*.TIFF"))
        )
        lines.append(f"  DEM files: {len(tif_files)}")
        if not tif_files:
            return lines

        sample = tif_files[0]
        lines.append(f"  Sample DEM: {sample.name}")
        try:
            with rasterio.open(sample) as src:
                lines.append(f"  DEM CRS: {src.crs}")
                lines.append(f"  DEM size: {src.width} x {src.height}")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            lines.append(f"  DEM read error: {exc}")
        return lines

    def _diagnose_vectors(self, base_path: Path, relative_dir: str, title: str) -> list[str]:
        folder = base_path / "input" / relative_dir
        lines = ["", f"{title} folder: {folder}"]
        if not folder.exists():
            lines.append("  Missing folder")
            return lines

        shp_files = sorted(folder.glob("*.shp"))
        lines.append(f"  Shapefiles: {len(shp_files)}")
        if not shp_files:
            return lines

        sample = shp_files[0]
        lines.append(f"  Sample SHP: {sample.name}")
        try:
            gdf = gpd.read_file(sample)
            lines.append(f"  CRS: {gdf.crs}")
            lines.append(f"  Features: {len(gdf)}")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            lines.append(f"  Read error: {exc}")

        return lines

    def _on_module_finished(self, module_name: str, success: bool) -> None:
        state = "OK" if success else "FAILED"
        self._append_log(f"=== {module_name} finished: {state} ===")

    def _on_pipeline_finished(self, success: bool) -> None:
        if success:
            self._load_results_if_available()

    def _load_results_if_available(self) -> None:
        csv_path = Path(self.results_path_edit.text())
        if csv_path.exists():
            self._load_results()

    def _stop_all(self) -> None:
        self.runner.stop()
        if (
            self.cross_section_process is not None
            and self.cross_section_process.state() != QProcess.NotRunning
        ):
            self.cross_section_process.kill()
            self.cs_run_button.setEnabled(True)
            self.statusBar().showMessage("Cross-section process stopped by user.", 4000)
        if (
            self.dem_overlay_process is not None
            and self.dem_overlay_process.state() != QProcess.NotRunning
        ):
            self.dem_overlay_process.kill()
            self.dem_overlay_run_button.setEnabled(True)
            self.statusBar().showMessage("DEM overlay process stopped by user.", 4000)


