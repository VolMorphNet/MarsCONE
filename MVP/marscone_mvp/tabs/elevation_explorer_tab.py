"""Mixin for the ElevationExplorerMixin section of MainWindow."""
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




class ElevationExplorerMixin:
    """Mixin — mixed into MainWindow via multiple inheritance."""

    def _build_breached_cones_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        explorer_group = QGroupBox("Elevation Explorer")
        explorer_layout = QVBoxLayout(explorer_group)

        controls_grid = QGridLayout()
        self.breached_cone_id_edit = QLineEdit()
        self.breached_cone_id_edit.setPlaceholderText("e.g. 35")
        self.breached_cone_id_edit.setMaximumWidth(220)
        self.breached_cone_from_dem_button = QPushButton("Use current DEM cone")
        self.breached_refresh_button = QPushButton("Refresh profile")
        self.breached_suggest_angle_button = QPushButton("Suggest angle")
        self.breached_suggest_angle_button.setVisible(
            False
        )  # Disabled: suggestion algorithm needs refinement
        self.breached_suggest_point_button = QPushButton("Suggest point")
        self.breached_suggest_point_button.setVisible(
            False
        )  # Disabled: suggestion algorithm needs refinement

        self.breached_angle_dial = QDial()
        self.breached_angle_dial.setRange(0, 359)
        self.breached_angle_dial.setNotchesVisible(True)
        self.breached_angle_dial.setWrapping(True)
        self.breached_angle_spin = QDoubleSpinBox()
        self.breached_angle_spin.setRange(0.0, 359.9)
        self.breached_angle_spin.setDecimals(1)
        self.breached_angle_spin.setSingleStep(0.5)

        self.breached_transect_length_spin = QSpinBox()
        self.breached_transect_length_spin.setRange(100, 50000)
        default_length = 2000
        if hasattr(self, "transect_length_spin"):
            default_length = int(self.transect_length_spin.value())
        self.breached_transect_length_spin.setValue(default_length)
        self.breached_sample_step_spin = QDoubleSpinBox()
        self.breached_sample_step_spin.setRange(0.5, 100.0)
        self.breached_sample_step_spin.setDecimals(2)
        self.breached_sample_step_spin.setValue(5.0)

        controls_grid.addWidget(QLabel("Cone ID"), 0, 0)
        controls_grid.addWidget(self.breached_cone_id_edit, 0, 1)
        controls_grid.addWidget(self.breached_cone_from_dem_button, 0, 2)
        controls_grid.addWidget(self.breached_refresh_button, 0, 3)
        controls_grid.addWidget(self.breached_suggest_angle_button, 0, 4)
        controls_grid.addWidget(self.breached_suggest_point_button, 0, 5)
        controls_grid.addWidget(QLabel("Transect length (m)"), 0, 6)
        controls_grid.addWidget(self.breached_transect_length_spin, 0, 7)
        controls_grid.addWidget(QLabel("Sample step (m)"), 0, 8)
        controls_grid.addWidget(self.breached_sample_step_spin, 0, 9)

        controls_grid.addWidget(QLabel("Transect angle (deg)"), 1, 0)
        controls_grid.addWidget(self.breached_angle_dial, 1, 1)
        controls_grid.addWidget(self.breached_angle_spin, 1, 2)

        self.breached_source_label = QLabel("Source: -")
        self.breached_source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.breached_map_figure, self.breached_map_ax = plt.subplots(figsize=(6.2, 5.2))
        self.breached_map_canvas = FigureCanvas(self.breached_map_figure)
        self.breached_map_canvas.mpl_connect("button_press_event", self._on_breached_map_click)
        self.breached_profile_figure, self.breached_profile_ax = plt.subplots(figsize=(6.2, 5.2))
        self.breached_profile_canvas = FigureCanvas(self.breached_profile_figure)
        self.breached_profile_canvas.mpl_connect(
            "button_press_event", self._on_breached_profile_click
        )

        preview_splitter = QSplitter(Qt.Horizontal)
        map_widget = QWidget()
        map_layout = QVBoxLayout(map_widget)
        map_layout.addWidget(QLabel("DEM with transect"))
        map_layout.addWidget(self.breached_map_canvas)
        profile_widget = QWidget()
        profile_layout = QVBoxLayout(profile_widget)
        profile_layout.addWidget(QLabel("Transect profile (click to mark point)"))
        profile_layout.addWidget(self.breached_profile_canvas)
        preview_splitter.addWidget(map_widget)
        preview_splitter.addWidget(profile_widget)
        preview_splitter.setSizes([640, 640])

        explorer_layout.addLayout(controls_grid)
        explorer_layout.addWidget(self.breached_source_label)
        explorer_layout.addWidget(preview_splitter)

        save_group = QGroupBox("Save point")
        save_layout = QVBoxLayout(save_group)

        save_fields_layout = QGridLayout()
        self.breached_save_cone_label = QLabel("-")
        self.breached_save_angle_label = QLabel("-")
        self.breached_save_distance_label = QLabel("-")
        self.breached_save_elevation_label = QLabel("-")

        save_fields_layout.addWidget(QLabel("Cone ID:"), 0, 0)
        save_fields_layout.addWidget(self.breached_save_cone_label, 0, 1)
        save_fields_layout.addWidget(QLabel("Angle:"), 0, 2)
        save_fields_layout.addWidget(self.breached_save_angle_label, 0, 3)
        save_fields_layout.addWidget(QLabel("Distance:"), 1, 0)
        save_fields_layout.addWidget(self.breached_save_distance_label, 1, 1)
        save_fields_layout.addWidget(QLabel("Elevation:"), 1, 2)
        save_fields_layout.addWidget(self.breached_save_elevation_label, 1, 3)

        confidence_layout = QHBoxLayout()
        confidence_layout.addWidget(QLabel("Confidence:"))
        self.breached_confidence_combo = QComboBox()
        self.breached_confidence_combo.addItems(["High", "Medium", "Low"])
        self.breached_confidence_combo.setCurrentIndex(0)
        confidence_layout.addWidget(self.breached_confidence_combo)
        confidence_layout.addStretch(1)

        notes_layout = QHBoxLayout()
        notes_layout.addWidget(QLabel("Notes:"))
        self.breached_notes_edit = QLineEdit()
        self.breached_notes_edit.setPlaceholderText("Optional notes about this point...")
        notes_layout.addWidget(self.breached_notes_edit)

        action_layout = QHBoxLayout()
        self.breached_save_button = QPushButton("Save point")
        action_layout.addStretch(1)
        action_layout.addWidget(self.breached_save_button)

        self.breached_save_status_label = QLabel("Ready to save")
        self.breached_save_status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.breached_save_status_label.setWordWrap(True)

        save_layout.addLayout(save_fields_layout)
        save_layout.addLayout(confidence_layout)
        save_layout.addLayout(notes_layout)
        save_layout.addLayout(action_layout)
        save_layout.addWidget(self.breached_save_status_label)

        saved_table_group = QGroupBox("Saved points")
        saved_table_layout = QVBoxLayout(saved_table_group)
        self.breached_saved_table = QTableView()
        self.breached_saved_table.setModel(self.breached_saved_points_model)
        self.breached_saved_table.setSortingEnabled(False)
        self.breached_saved_table.setSelectionBehavior(QTableView.SelectRows)
        self.breached_saved_table.setSelectionMode(QTableView.SingleSelection)
        self.breached_saved_table.setMinimumHeight(160)
        saved_table_layout.addWidget(self.breached_saved_table)

        self.complex_breach_singles_table = QTableView()
        self.complex_breach_singles_table.setModel(self.complex_breach_singles_model)

        self.breached_cone_from_dem_button.clicked.connect(self._breached_set_cone_from_dem_preview)
        self.breached_refresh_button.clicked.connect(self._refresh_breached_transect_preview)
        self.breached_cone_id_edit.returnPressed.connect(self._refresh_breached_transect_preview)
        self.breached_cone_id_edit.textChanged.connect(
            lambda _t: self._refresh_breached_saved_points_table()
        )
        self.breached_angle_dial.valueChanged.connect(self._on_breached_angle_dial_changed)
        self.breached_angle_spin.valueChanged.connect(self._on_breached_angle_spin_changed)
        self.breached_transect_length_spin.valueChanged.connect(
            lambda _v: self._refresh_breached_transect_preview()
        )
        self.breached_sample_step_spin.valueChanged.connect(
            lambda _v: self._refresh_breached_transect_preview()
        )
        self.breached_save_button.clicked.connect(self._on_breached_save_point)
        self.breached_suggest_angle_button.clicked.connect(self._on_breached_suggest_angle)
        self.breached_suggest_point_button.clicked.connect(self._on_breached_suggest_point)
        self.breached_saved_table.selectionModel().selectionChanged.connect(
            lambda _selected, _deselected: self._on_breached_saved_table_selection_changed()
        )

        if hasattr(self, "transect_length_spin"):
            self.breached_transect_length_spin.setValue(int(self.transect_length_spin.value()))
            self.transect_length_spin.valueChanged.connect(
                lambda v: self.breached_transect_length_spin.setValue(int(v))
            )
        self.breached_angle_spin.setValue(0.0)

        current_cone = self._current_dem_overlay_cone_id()
        if current_cone:
            self.breached_cone_id_edit.setText(current_cone)

        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(save_group, 1)
        bottom_layout.addWidget(saved_table_group, 2)

        layout.insertWidget(0, explorer_group, stretch=3)
        layout.addLayout(bottom_layout, stretch=1)
        self._refresh_breached_transect_preview()
        self._refresh_breached_saved_points_table()
        return page

    def _on_breached_angle_dial_changed(self, value: int) -> None:
        if self.breached_angle_sync_in_progress:
            return
        self.breached_angle_sync_in_progress = True
        self.breached_angle_spin.setValue(float(value))
        self.breached_angle_sync_in_progress = False
        self._refresh_breached_transect_preview()

    def _on_breached_angle_spin_changed(self, value: float) -> None:
        if self.breached_angle_sync_in_progress:
            return
        self.breached_angle_sync_in_progress = True
        self.breached_angle_dial.setValue(int(round(value)) % 360)
        self.breached_angle_sync_in_progress = False
        self._refresh_breached_transect_preview()

    def _breached_set_cone_from_dem_preview(self) -> None:
        cone_id = self._current_dem_overlay_cone_id()
        if not cone_id:
            QMessageBox.information(
                self, "Elevation Explorer", "No cone selected in DEM overlay preview."
            )
            return
        self.breached_cone_id_edit.setText(cone_id)
        self._refresh_breached_transect_preview()
        self._refresh_breached_saved_points_table()

    def _resolve_breached_dem_path(self) -> Path | None:
        cone_id = self.breached_cone_id_edit.text().strip()
        normalized_cone_id = self._normalize_cone_id_for_match(cone_id)

        dem_dir_text = (
            self.dem_overlay_dem_dir_edit.text().strip()
            if hasattr(self, "dem_overlay_dem_dir_edit")
            else ""
        )
        if dem_dir_text:
            dem_dir = Path(dem_dir_text)
            if dem_dir.exists():
                if normalized_cone_id:
                    for pattern in [
                        f"cone_{normalized_cone_id}_dem.tif",
                        f"cone_{normalized_cone_id}_dem.tiff",
                        f"cone_{normalized_cone_id}_dem.TIF",
                        f"cone_{normalized_cone_id}_dem.TIFF",
                    ]:
                        found = list(dem_dir.glob(pattern))
                        if found:
                            return found[0]

                dem_files = sorted(
                    list(dem_dir.glob("*.tif"))
                    + list(dem_dir.glob("*.tiff"))
                    + list(dem_dir.glob("*.TIF"))
                    + list(dem_dir.glob("*.TIFF"))
                )
                if dem_files:
                    return dem_files[0]

        dem_path, _ = self._resolve_dem_area_preview_source_paths()
        return dem_path

    @staticmethod
    def _normalize_cone_id_for_match(value) -> str:
        return str(value).strip().replace(".0", "")

    def _resolve_breached_center_xy(self, cone_id: str) -> tuple[float, float] | None:
        normalized_id = self._normalize_cone_id_for_match(cone_id)

        centers_text = (
            self.dem_overlay_centers_hybrid_edit.text().strip()
            if hasattr(self, "dem_overlay_centers_hybrid_edit")
            else ""
        )
        centers_path = Path(centers_text) if centers_text else Path("")
        if not centers_path.exists():
            centers_path = (
                Path(self.base_path_edit.text().strip())
                / "output"
                / "analyzer"
                / "shapes"
                / "centers_hybrid.gpkg"
            )

        if centers_path.exists():
            try:
                centers_gdf = gpd.read_file(centers_path)
                id_column = None
                for candidate in ["cone_id", "id", "ID", "cone"]:
                    if candidate in centers_gdf.columns:
                        id_column = candidate
                        break
                if id_column is None:
                    for column in centers_gdf.columns:
                        if "cone" in str(column).lower() or str(column).lower().endswith("id"):
                            id_column = column
                            break

                if id_column is not None and "geometry" in centers_gdf.columns:
                    match = centers_gdf[
                        centers_gdf[id_column].astype(str).str.replace(r"\\.0$", "", regex=True)
                        == normalized_id
                    ]
                    if not match.empty:
                        geom = match.geometry.iloc[0]
                        return float(geom.x), float(geom.y)
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        cone_summary_path = (
            Path(self.base_path_edit.text().strip()) / "output" / "analyzer" / "cone_summary.csv"
        )
        if cone_summary_path.exists():
            try:
                cone_summary = pd.read_csv(cone_summary_path, sep=";")
                if {"cone_id", "center_x", "center_y"}.issubset(set(cone_summary.columns)):
                    cone_summary["cone_id_norm"] = (
                        cone_summary["cone_id"].astype(str).str.replace(r"\\.0$", "", regex=True)
                    )
                    match = cone_summary[cone_summary["cone_id_norm"] == normalized_id]
                    if not match.empty:
                        row = match.iloc[0]
                        x_val = pd.to_numeric(row.get("center_x"), errors="coerce")
                        y_val = pd.to_numeric(row.get("center_y"), errors="coerce")
                        if pd.notna(x_val) and pd.notna(y_val):
                            return float(x_val), float(y_val)
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        return None

    def _refresh_breached_transect_preview(self) -> None:
        cone_id = self.breached_cone_id_edit.text().strip()
        if not cone_id:
            self.breached_map_snapshot = None
            self.breached_map_ax.clear()
            self.breached_profile_ax.clear()
            self.breached_map_ax.text(0.5, 0.5, "Enter Cone ID", ha="center", va="center")
            self.breached_profile_ax.text(0.5, 0.5, "No profile", ha="center", va="center")
            self.breached_map_ax.set_axis_off()
            self.breached_profile_ax.set_axis_off()
            self.breached_map_canvas.draw_idle()
            self.breached_profile_canvas.draw_idle()
            self.breached_source_label.setText("Source: -")
            return

        center_xy = self._resolve_breached_center_xy(cone_id)
        if center_xy is None:
            self.breached_map_snapshot = None
            self.breached_map_ax.clear()
            self.breached_profile_ax.clear()
            self.breached_map_ax.text(
                0.5, 0.5, f"Center not found for cone {cone_id}", ha="center", va="center"
            )
            self.breached_profile_ax.text(0.5, 0.5, "No profile", ha="center", va="center")
            self.breached_map_ax.set_axis_off()
            self.breached_profile_ax.set_axis_off()
            self.breached_map_canvas.draw_idle()
            self.breached_profile_canvas.draw_idle()
            self.breached_source_label.setText("Source: center missing")
            return

        dem_path = self._resolve_breached_dem_path()
        if dem_path is None or not dem_path.exists():
            self.breached_map_snapshot = None
            self.breached_map_ax.clear()
            self.breached_profile_ax.clear()
            self.breached_map_ax.text(0.5, 0.5, "DEM not found", ha="center", va="center")
            self.breached_profile_ax.text(0.5, 0.5, "No profile", ha="center", va="center")
            self.breached_map_ax.set_axis_off()
            self.breached_profile_ax.set_axis_off()
            self.breached_map_canvas.draw_idle()
            self.breached_profile_canvas.draw_idle()
            self.breached_source_label.setText("Source: DEM missing")
            return

        angle_deg = float(self.breached_angle_spin.value())
        transect_length = float(self.breached_transect_length_spin.value())
        step = float(self.breached_sample_step_spin.value())
        half = transect_length / 2.0
        theta = np.deg2rad(angle_deg)
        dx = np.cos(theta)
        dy = np.sin(theta)
        x0 = center_xy[0] - half * dx
        y0 = center_xy[1] - half * dy
        x1 = center_xy[0] + half * dx
        y1 = center_xy[1] + half * dy
        sample_count = max(2, int(np.ceil(transect_length / max(step, 0.5))) + 1)
        xs = np.linspace(x0, x1, sample_count)
        ys = np.linspace(y0, y1, sample_count)

        try:
            with rasterio.open(dem_path) as src:
                samples = list(src.sample(list(zip(xs, ys))))
                z = np.array([float(v[0]) if len(v) else np.nan for v in samples], dtype=float)
                if src.nodata is not None:
                    z = np.where(np.isclose(z, src.nodata), np.nan, z)

                # Keep preview scale data-driven: follow transect length and DEM footprint
                # around the cone center instead of enforcing a fixed large minimum radius.
                base_radius = half * 1.2
                min_radius = max(step * 8.0, 30.0)
                radius = max(base_radius, min_radius)

                bounds = src.bounds
                if (
                    bounds.left <= center_xy[0] <= bounds.right
                    and bounds.bottom <= center_xy[1] <= bounds.top
                ):
                    available_radius = min(
                        center_xy[0] - bounds.left,
                        bounds.right - center_xy[0],
                        center_xy[1] - bounds.bottom,
                        bounds.top - center_xy[1],
                    )
                    if np.isfinite(available_radius) and available_radius > 0:
                        radius = min(radius, float(available_radius) * 0.98)
                        radius = max(radius, min_radius)

                left = center_xy[0] - radius
                right = center_xy[0] + radius
                bottom = center_xy[1] - radius
                top = center_xy[1] + radius

                window = rio_from_bounds(left, bottom, right, top, transform=src.transform)
                dem_window = src.read(1, window=window, boundless=True, fill_value=np.nan)
                win_transform = rio_window_transform(window, src.transform)

                x_min = win_transform.c
                x_max = win_transform.c + win_transform.a * dem_window.shape[1]
                y_max = win_transform.f
                y_min = win_transform.f + win_transform.e * dem_window.shape[0]
                extent = [
                    min(x_min, x_max),
                    max(x_min, x_max),
                    min(y_min, y_max),
                    max(y_min, y_max),
                ]

                dem_window_float = dem_window.astype(float)
                azimuth_deg = (
                    float(self.dem_overlay_azimuth_spin.value())
                    if hasattr(self, "dem_overlay_azimuth_spin")
                    else 315.0
                )
                altitude_deg = (
                    float(self.dem_overlay_altitude_spin.value())
                    if hasattr(self, "dem_overlay_altitude_spin")
                    else 45.0
                )
                hillshade_window = self._compute_hillshade_array(
                    dem_window_float, win_transform, azimuth_deg, altitude_deg
                )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            self.breached_map_snapshot = None
            self.breached_map_ax.clear()
            self.breached_profile_ax.clear()
            self.breached_map_ax.text(0.5, 0.5, f"DEM read error:\n{exc}", ha="center", va="center")
            self.breached_profile_ax.text(0.5, 0.5, "No profile", ha="center", va="center")
            self.breached_map_ax.set_axis_off()
            self.breached_profile_ax.set_axis_off()
            self.breached_map_canvas.draw_idle()
            self.breached_profile_canvas.draw_idle()
            self.breached_source_label.setText(f"Source: DEM read failed ({dem_path})")
            return

        self.breached_center_xy = center_xy
        self.breached_profile_distances = np.linspace(-half, half, sample_count)
        self.breached_profile_elevations = z
        self.breached_map_snapshot = {
            "hillshade": hillshade_window,
            "extent": extent,
            "x0": float(x0),
            "y0": float(y0),
            "x1": float(x1),
            "y1": float(y1),
            "center_x": float(center_xy[0]),
            "center_y": float(center_xy[1]),
            "xs": np.asarray(xs, dtype=float),
            "ys": np.asarray(ys, dtype=float),
            "z": np.asarray(z, dtype=float),
            "cone_id": cone_id,
            "angle_deg": float(angle_deg),
        }
        if self.breached_profile_selected_index is not None:
            if self.breached_profile_selected_index >= len(self.breached_profile_distances):
                self.breached_profile_selected_index = None

        self.breached_map_ax.clear()
        if np.all(~np.isfinite(dem_window)):
            self.breached_map_ax.text(0.5, 0.5, "No DEM values in window", ha="center", va="center")
            self.breached_map_ax.set_axis_off()
        else:
            self.breached_map_ax.imshow(
                hillshade_window, cmap="gray", extent=extent, origin="upper"
            )
            self.breached_map_ax.plot([x0, x1], [y0, y1], color="#E45756", linewidth=2)
            self.breached_map_ax.scatter(
                [center_xy[0]], [center_xy[1]], marker="*", s=120, color="lime", edgecolors="k"
            )
            if self.breached_profile_selected_index is not None:
                idx = int(self.breached_profile_selected_index)
                if 0 <= idx < len(xs) and np.isfinite(z[idx]):
                    self.breached_map_ax.scatter(
                        [float(xs[idx])],
                        [float(ys[idx])],
                        marker="o",
                        s=72,
                        color="#FF4D5A",
                        edgecolors="white",
                        linewidths=0.9,
                        zorder=6,
                    )
            self.breached_map_ax.set_aspect("equal", adjustable="box")
            self.breached_map_ax.set_xlabel("Easting (m)")
            self.breached_map_ax.set_ylabel("Northing (m)")
            self.breached_map_ax.set_title(f"Cone {cone_id} | angle {angle_deg:.1f} deg")

        self._render_breached_profile_plot(cone_id)

        centers_text = (
            self.dem_overlay_centers_hybrid_edit.text().strip()
            if hasattr(self, "dem_overlay_centers_hybrid_edit")
            else ""
        )
        self.breached_source_label.setText(
            f"Source: DEM={dem_path} | Centers={centers_text or 'default'}"
        )
        self.breached_map_figure.tight_layout()
        self.breached_map_canvas.draw_idle()

        self._update_breached_save_labels()
        self._refresh_breached_saved_points_table()

    def _render_breached_profile_plot(self, cone_id: str) -> None:
        self.breached_profile_ax.clear()
        if self.breached_profile_distances is None or self.breached_profile_elevations is None:
            self.breached_profile_ax.text(0.5, 0.5, "No profile", ha="center", va="center")
            self.breached_profile_ax.set_axis_off()
            self.breached_profile_canvas.draw_idle()
            return

        x = self.breached_profile_distances
        z = self.breached_profile_elevations
        self.breached_profile_ax.plot(x, z, color="#2F2F2F", linewidth=1.6)
        self.breached_profile_ax.grid(True, alpha=0.25)
        self.breached_profile_ax.set_xlabel("Distance along transect (m)")
        self.breached_profile_ax.set_ylabel("Elevation (m)")
        self.breached_profile_ax.set_title(f"Cone {cone_id} transect profile")

        if self.breached_profile_selected_index is not None:
            idx = int(self.breached_profile_selected_index)
            if 0 <= idx < len(x) and np.isfinite(z[idx]):
                x_sel = float(x[idx])
                z_sel = float(z[idx])
                self.breached_profile_ax.scatter([x_sel], [z_sel], color="#E45756", s=60, zorder=5)
                self.breached_profile_ax.annotate(
                    f"point elev: {z_sel:.2f} m",
                    (x_sel, z_sel),
                    textcoords="offset points",
                    xytext=(8, 8),
                    fontsize=9,
                    bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.85},
                )

        self.breached_profile_figure.tight_layout()
        self.breached_profile_canvas.draw_idle()

    def _on_breached_profile_click(self, event) -> None:
        if event.inaxes != self.breached_profile_ax or event.xdata is None:
            return
        if self.breached_profile_distances is None or self.breached_profile_elevations is None:
            return

        x = self.breached_profile_distances
        valid = np.isfinite(x)
        if not valid.any():
            return

        idx = int(np.argmin(np.abs(x - float(event.xdata))))
        self.breached_profile_selected_index = idx
        self._refresh_breached_transect_preview()

    def _on_breached_map_click(self, event) -> None:
        if event.inaxes != self.breached_map_ax:
            return
        self._open_breached_map_zoom_dialog()

    def _open_breached_map_zoom_dialog(self) -> None:
        snapshot = self.breached_map_snapshot
        if not snapshot:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("DEM preview (enlarged)")
        dialog.resize(980, 860)
        dialog_layout = QVBoxLayout(dialog)

        fig, ax = plt.subplots(figsize=(9.0, 8.0))
        canvas = FigureCanvas(fig)
        dialog_layout.addWidget(canvas)

        ax.imshow(snapshot["hillshade"], cmap="gray", extent=snapshot["extent"], origin="upper")
        ax.plot(
            [snapshot["x0"], snapshot["x1"]],
            [snapshot["y0"], snapshot["y1"]],
            color="#E45756",
            linewidth=2,
        )
        ax.scatter(
            [snapshot["center_x"]],
            [snapshot["center_y"]],
            marker="*",
            s=140,
            color="lime",
            edgecolors="k",
            zorder=5,
        )

        selected_idx = self.breached_profile_selected_index
        if selected_idx is not None:
            xs = snapshot["xs"]
            ys = snapshot["ys"]
            zs = snapshot["z"]
            idx = int(selected_idx)
            if 0 <= idx < len(xs) and np.isfinite(zs[idx]):
                ax.scatter(
                    [float(xs[idx])],
                    [float(ys[idx])],
                    marker="o",
                    s=95,
                    color="#FF4D5A",
                    edgecolors="white",
                    linewidths=1.0,
                    zorder=6,
                )

        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("Easting (m)")
        ax.set_ylabel("Northing (m)")
        ax.set_title(f"Cone {snapshot['cone_id']} | angle {snapshot['angle_deg']:.1f} deg")
        fig.tight_layout()
        canvas.draw_idle()

        dialog.exec()

    def _update_breached_save_labels(self) -> None:
        cone_id = self.breached_cone_id_edit.text().strip()
        angle_deg = float(self.breached_angle_spin.value())

        self.breached_save_cone_label.setText(cone_id or "-")
        self.breached_save_angle_label.setText(f"{angle_deg:.1f}°")

        if (
            self.breached_profile_distances is None
            or self.breached_profile_elevations is None
            or self.breached_profile_selected_index is None
        ):
            self.breached_save_distance_label.setText("-")
            self.breached_save_elevation_label.setText("-")
        else:
            idx = int(self.breached_profile_selected_index)
            if 0 <= idx < len(self.breached_profile_distances):
                dist = float(self.breached_profile_distances[idx])
                elev = float(self.breached_profile_elevations[idx])
                self.breached_save_distance_label.setText(f"{dist:.1f} m")
                self.breached_save_elevation_label.setText(f"{elev:.2f} m")
            else:
                self.breached_save_distance_label.setText("-")
                self.breached_save_elevation_label.setText("-")

    def _get_breached_save_csv_path(self) -> Path:
        base = (
            Path(self.base_path_edit.text().strip())
            if hasattr(self, "base_path_edit")
            else Path(".")
        )
        csv_path = base / "output" / "analyzer" / "breached_cone_points.csv"
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        return csv_path

    def _refresh_breached_saved_points_table(self) -> None:
        csv_path = self._get_breached_save_csv_path()
        if not csv_path.exists():
            self.breached_saved_points_df = pd.DataFrame(
                columns=[
                    "cone_id",
                    "angle_deg",
                    "distance_m",
                    "elevation_m",
                    "top_elevation",
                    "center_elevation",
                    "elevation_difference",
                    "confidence",
                    "notes",
                    "timestamp_utc",
                ]
            )
            self.breached_saved_table_sync_in_progress = True
            self.breached_saved_points_model.set_dataframe(self.breached_saved_points_df)
            self.breached_saved_table_sync_in_progress = False
            if hasattr(self, "breached_saved_table"):
                self.breached_saved_table.resizeColumnsToContents()
            return

        try:
            df = pd.read_csv(csv_path, sep=";")
        except Exception:  # pylint: disable=broad-exception-caught
            self.breached_saved_points_df = pd.DataFrame()
            self.breached_saved_table_sync_in_progress = True
            self.breached_saved_points_model.set_dataframe(self.breached_saved_points_df)
            self.breached_saved_table_sync_in_progress = False
            return

        cone_id = (
            self.breached_cone_id_edit.text().strip()
            if hasattr(self, "breached_cone_id_edit")
            else ""
        )
        if cone_id and "cone_id" in df.columns:
            cone_norm = self._normalize_cone_id_for_match(cone_id)
            df = df[df["cone_id"].astype(str).map(self._normalize_cone_id_for_match) == cone_norm]

        if "timestamp_utc" in df.columns:
            ts = pd.to_datetime(df["timestamp_utc"], errors="coerce", utc=True)
            df = (
                df.assign(_ts_sort=ts)
                .sort_values(by="_ts_sort", ascending=False, kind="mergesort", na_position="last")
                .drop(columns=["_ts_sort"])
            )

        preferred_order = [
            "cone_id",
            "angle_deg",
            "distance_m",
            "elevation_m",
            "top_elevation",
            "center_elevation",
            "elevation_difference",
            "confidence",
            "notes",
            "timestamp_utc",
        ]
        ordered_cols = [col for col in preferred_order if col in df.columns]
        if ordered_cols:
            df = df[ordered_cols]

        self.breached_saved_points_df = df.reset_index(drop=True)
        self.breached_saved_table_sync_in_progress = True
        self.breached_saved_points_model.set_dataframe(self.breached_saved_points_df)
        self.breached_saved_table_sync_in_progress = False
        if hasattr(self, "breached_saved_table"):
            self.breached_saved_table.resizeColumnsToContents()

    def _on_breached_saved_table_selection_changed(self) -> None:
        if self.breached_saved_table_sync_in_progress:
            return
        if self.breached_saved_points_df.empty:
            return

        selection_model = (
            self.breached_saved_table.selectionModel()
            if hasattr(self, "breached_saved_table")
            else None
        )
        if selection_model is None:
            return
        selected_rows = selection_model.selectedRows()
        if not selected_rows:
            return

        row_idx = selected_rows[0].row()
        if row_idx < 0 or row_idx >= len(self.breached_saved_points_df.index):
            return

        row = self.breached_saved_points_df.iloc[row_idx]
        cone_id = self._normalize_cone_id_for_match(row.get("cone_id", ""))
        angle_deg = pd.to_numeric(row.get("angle_deg"), errors="coerce")
        distance_m = pd.to_numeric(row.get("distance_m"), errors="coerce")
        notes = str(row.get("notes", ""))
        confidence = str(row.get("confidence", ""))

        if not cone_id or pd.isna(angle_deg):
            return

        self.breached_cone_id_edit.setText(cone_id)
        self.breached_angle_sync_in_progress = True
        self.breached_angle_spin.setValue(float(angle_deg) % 360.0)
        self.breached_angle_dial.setValue(int(round(float(angle_deg))) % 360)
        self.breached_angle_sync_in_progress = False

        self.breached_profile_selected_index = None
        self._refresh_breached_transect_preview()

        if (
            pd.notna(distance_m)
            and self.breached_profile_distances is not None
            and len(self.breached_profile_distances)
        ):
            idx = int(np.argmin(np.abs(self.breached_profile_distances - float(distance_m))))
            self.breached_profile_selected_index = idx
            self._refresh_breached_transect_preview()

        if confidence in {"High", "Medium", "Low"}:
            self.breached_confidence_combo.setCurrentText(confidence)
        self.breached_notes_edit.setText(notes)
        self.breached_save_status_label.setText(
            f"Loaded saved record: cone {cone_id}, angle {float(angle_deg):.1f}°, "
            f"distance {float(distance_m):.1f} m"
            if pd.notna(distance_m)
            else f"Loaded saved record: cone {cone_id}, angle {float(angle_deg):.1f}°"
        )

    def _compute_breached_samples_for_angle(
        self,
        src: rasterio.io.DatasetReader,
        center_xy: tuple[float, float],
        angle_deg: float,
        transect_length: float,
        step: float,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        half = transect_length / 2.0
        theta = np.deg2rad(angle_deg)
        dx = np.cos(theta)
        dy = np.sin(theta)
        x0 = center_xy[0] - half * dx
        y0 = center_xy[1] - half * dy
        x1 = center_xy[0] + half * dx
        y1 = center_xy[1] + half * dy
        sample_count = max(2, int(np.ceil(transect_length / max(step, 0.5))) + 1)
        xs = np.linspace(x0, x1, sample_count)
        ys = np.linspace(y0, y1, sample_count)
        samples = list(src.sample(list(zip(xs, ys))))
        z = np.array([float(v[0]) if len(v) else np.nan for v in samples], dtype=float)
        if src.nodata is not None:
            z = np.where(np.isclose(z, src.nodata), np.nan, z)
        return xs, ys, z

    def _compute_dem_breach_angle_candidates(
        self,
        src: rasterio.io.DatasetReader,
        center_xy: tuple[float, float],
        transect_length: float,
        step: float,
    ) -> list[tuple[float, float, float, float]]:
        max_radius = transect_length / 2.0
        radial_step = max(step, 2.0)
        radii = np.arange(radial_step, max_radius + radial_step * 0.5, radial_step, dtype=float)
        if len(radii) < 10:
            return []

        inner_mask = (radii >= 0.18 * max_radius) & (radii <= 0.38 * max_radius)
        rim_mask = (radii >= 0.38 * max_radius) & (radii <= 0.72 * max_radius)
        outer_mask = (radii >= 0.72 * max_radius) & (radii <= 0.95 * max_radius)
        if not (inner_mask.any() and rim_mask.any() and outer_mask.any()):
            return []

        metrics: list[dict] = []
        for angle in range(0, 360, 5):
            theta = np.deg2rad(float(angle))
            xs = center_xy[0] + radii * np.cos(theta)
            ys = center_xy[1] + radii * np.sin(theta)
            samples = list(src.sample(list(zip(xs, ys))))
            z = np.array([float(v[0]) if len(v) else np.nan for v in samples], dtype=float)
            if src.nodata is not None:
                z = np.where(np.isclose(z, src.nodata), np.nan, z)
            if np.sum(np.isfinite(z)) < int(0.7 * len(z)):
                continue

            median = np.nanmedian(z[np.isfinite(z)])
            z_filled = np.where(np.isfinite(z), z, median)
            smooth = np.convolve(z_filled, np.array([1.0, 2.0, 3.0, 2.0, 1.0]) / 9.0, mode="same")
            grad = np.gradient(smooth, radii)

            rim_profile = smooth[rim_mask]
            inner_profile = smooth[inner_mask]
            outer_profile = smooth[outer_mask]
            if len(rim_profile) < 3 or len(inner_profile) < 3 or len(outer_profile) < 3:
                continue

            rim_peak = float(np.nanmax(rim_profile))
            inner_med = float(np.nanmedian(inner_profile))
            outer_med = float(np.nanmedian(outer_profile))
            flank_drop = rim_peak - outer_med
            bowl_depth = rim_peak - inner_med

            # Find strongest descent around rim-to-flank transition.
            transition_mask = (radii >= 0.45 * max_radius) & (radii <= 0.85 * max_radius)
            transition_grad = np.where(transition_mask, grad, np.nan)
            if np.any(np.isfinite(transition_grad)):
                min_grad_idx = int(np.nanargmin(transition_grad))
                suggested_radius = float(radii[min_grad_idx])
                slope_strength = float(max(0.0, -transition_grad[min_grad_idx]))
            else:
                suggested_radius = float(np.nanmedian(radii[rim_mask]))
                slope_strength = 0.0

            metrics.append(
                {
                    "angle": float(angle),
                    "rim_peak": rim_peak,
                    "flank_drop": float(flank_drop),
                    "bowl_depth": float(bowl_depth),
                    "slope_strength": slope_strength,
                    "suggested_radius": suggested_radius,
                }
            )

        if not metrics:
            return []

        rim_values = np.array([m["rim_peak"] for m in metrics], dtype=float)
        rim_med = float(np.nanmedian(rim_values))
        rim_iqr = float(np.nanpercentile(rim_values, 75) - np.nanpercentile(rim_values, 25))
        rim_scale = max(rim_iqr, 1e-6)

        candidates: list[tuple[float, float, float, float]] = []
        for m in metrics:
            rim_deficit = max(0.0, (rim_med - m["rim_peak"]) / rim_scale)
            score = (
                0.55 * rim_deficit
                + 0.20 * max(0.0, m["flank_drop"])
                + 0.15 * max(0.0, m["bowl_depth"])
                + 0.10 * max(0.0, m["slope_strength"])
            )
            candidates.append(
                (
                    float(score),
                    float(m["angle"]),
                    float(m["suggested_radius"]),
                    float(m["rim_peak"]),
                )
            )

        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates

    def _pick_breached_profile_index_for_radius(self, suggested_radius: float) -> int | None:
        if self.breached_profile_distances is None or self.breached_profile_elevations is None:
            return None
        d = np.asarray(self.breached_profile_distances, dtype=float)
        z = np.asarray(self.breached_profile_elevations, dtype=float)
        if len(d) == 0 or len(z) != len(d):
            return None

        idx_pos = int(np.argmin(np.abs(d - abs(suggested_radius))))
        idx_neg = int(np.argmin(np.abs(d + abs(suggested_radius))))

        z_pos = z[idx_pos] if 0 <= idx_pos < len(z) else np.nan
        z_neg = z[idx_neg] if 0 <= idx_neg < len(z) else np.nan

        if np.isfinite(z_pos) and np.isfinite(z_neg):
            return idx_pos if z_pos <= z_neg else idx_neg
        if np.isfinite(z_pos):
            return idx_pos
        if np.isfinite(z_neg):
            return idx_neg
        return None

    @staticmethod
    def _suggest_breach_index_from_profile_values(
        z: np.ndarray,
        distances: np.ndarray | None = None,
    ) -> int | None:
        if z is None or len(z) < 7:
            return None
        z_work = np.asarray(z, dtype=float)
        if np.sum(np.isfinite(z_work)) < 7:
            return None

        median = np.nanmedian(z_work[np.isfinite(z_work)])
        z_filled = np.where(np.isfinite(z_work), z_work, median)
        # Slightly stronger smoothing to reduce local roughness-driven false picks.
        kernel = np.array([1.0, 2.0, 3.0, 2.0, 1.0], dtype=float)
        kernel /= kernel.sum()
        smooth = np.convolve(z_filled, kernel, mode="same")
        grad = np.gradient(smooth)
        curv = np.gradient(grad)

        n = len(smooth)
        edge_margin = max(4, int(0.15 * n))
        idx_all = np.arange(n)
        edge_mask = (idx_all >= edge_margin) & (idx_all < (n - edge_margin))

        if distances is not None and len(distances) == n:
            d = np.asarray(distances, dtype=float)
            half = float(np.nanmax(np.abs(d))) if np.any(np.isfinite(d)) else 0.0
            if half > 0:
                # Prefer points in a crater-flank belt and avoid center/end artifacts.
                dist_mask = (np.abs(d) >= 0.12 * half) & (np.abs(d) <= 0.78 * half)
            else:
                dist_mask = np.ones(n, dtype=bool)
        else:
            d = np.zeros(n, dtype=float)
            half = 1.0
            dist_mask = np.ones(n, dtype=bool)

        finite_mask = np.isfinite(grad) & np.isfinite(curv) & np.isfinite(smooth)
        base_mask = edge_mask & dist_mask & finite_mask
        if not base_mask.any():
            base_mask = edge_mask & finite_mask
        if not base_mask.any():
            return None

        q25, q90 = np.nanpercentile(smooth[np.isfinite(smooth)], [25, 90])
        elev_band = np.clip((smooth - q25) / max(q90 - q25, 1e-6), 0.0, 1.0)
        slope_term = np.maximum(0.0, -grad)
        curv_term = np.maximum(0.0, curv)
        dist_penalty = (np.abs(d) / max(half, 1e-6)) ** 2

        # Composite index-level score to avoid selecting endpoints and flat tails.
        idx_score = 0.58 * slope_term + 0.24 * curv_term + 0.18 * elev_band - 0.20 * dist_penalty
        idx_score = np.where(base_mask, idx_score, -np.inf)
        best_idx = int(np.nanargmax(idx_score))
        if not np.isfinite(idx_score[best_idx]):
            return None
        return best_idx

    def _score_breached_profile_candidate(
        self,
        z: np.ndarray,
        distances: np.ndarray | None = None,
    ) -> tuple[float, int | None]:
        idx = self._suggest_breach_index_from_profile_values(z, distances=distances)
        if idx is None:
            return float("-inf"), None

        z_work = np.asarray(z, dtype=float)
        if np.sum(np.isfinite(z_work)) < 7:
            return float("-inf"), None
        median = np.nanmedian(z_work[np.isfinite(z_work)])
        z_filled = np.where(np.isfinite(z_work), z_work, median)
        kernel = np.array([1.0, 2.0, 3.0, 2.0, 1.0], dtype=float)
        kernel /= kernel.sum()
        smooth = np.convolve(z_filled, kernel, mode="same")
        grad = np.gradient(smooth)
        curv = np.gradient(grad)

        relief = float(np.nanmax(smooth) - np.nanmin(smooth))
        slope_strength = float(max(0.0, -grad[idx])) if np.isfinite(grad[idx]) else 0.0
        curvature_strength = float(max(0.0, curv[idx])) if np.isfinite(curv[idx]) else 0.0
        rim_contrast = float(np.nanpercentile(smooth, 90) - np.nanpercentile(smooth, 50))
        grad_noise = float(np.nanstd(np.diff(grad))) if len(grad) > 2 else 0.0

        dist_penalty = 0.0
        if distances is not None and len(distances) == len(smooth):
            d = np.asarray(distances, dtype=float)
            half = float(np.nanmax(np.abs(d))) if np.any(np.isfinite(d)) else 0.0
            if half > 0:
                dist_penalty = float((abs(d[idx]) / half) ** 2)

        score = (
            0.50 * slope_strength
            + 0.20 * curvature_strength
            + 0.20 * relief
            + 0.10 * rim_contrast
            - 0.10 * grad_noise
            - 0.30 * dist_penalty
        )
        return score, idx

    def _on_breached_suggest_angle(self) -> None:
        cone_id = self.breached_cone_id_edit.text().strip()
        if not cone_id:
            QMessageBox.information(self, "Suggest angle", "Set Cone ID first.")
            return

        center_xy = self._resolve_breached_center_xy(cone_id)
        if center_xy is None:
            QMessageBox.information(self, "Suggest angle", f"Center not found for cone {cone_id}.")
            return

        dem_path = self._resolve_breached_dem_path()
        if dem_path is None or not dem_path.exists():
            QMessageBox.information(self, "Suggest angle", "DEM not found for current cone.")
            return

        transect_length = float(self.breached_transect_length_spin.value())
        step = float(self.breached_sample_step_spin.value())
        candidates: list[tuple[float, float, float, float]] = []

        try:
            with rasterio.open(dem_path) as src:
                candidates = self._compute_dem_breach_angle_candidates(
                    src,
                    center_xy,
                    transect_length,
                    step,
                )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            QMessageBox.warning(self, "Suggest angle", f"Angle scan failed:\n{exc}")
            return

        if not candidates:
            QMessageBox.information(self, "Suggest angle", "No valid angle candidates found.")
            return

        _best_score, best_angle, best_radius, _best_rim = candidates[0]

        self.breached_suggested_angle_deg = best_angle
        self.breached_suggested_index = None

        self.breached_angle_spin.setValue(best_angle)
        self._refresh_breached_transect_preview()
        idx = self._pick_breached_profile_index_for_radius(best_radius)
        if idx is not None:
            self.breached_profile_selected_index = int(idx)
            self.breached_suggested_index = int(idx)
            self._refresh_breached_transect_preview()

    def _on_breached_suggest_point(self) -> None:
        if self.breached_profile_elevations is None or len(self.breached_profile_elevations) < 5:
            QMessageBox.information(self, "Suggest point", "Refresh profile first.")
            return

        idx = self._suggest_breach_index_from_profile_values(
            self.breached_profile_elevations,
            distances=self.breached_profile_distances,
        )
        if idx is None:
            QMessageBox.information(self, "Suggest point", "Could not suggest a point.")
            return

        self.breached_suggested_index = int(idx)
        self.breached_profile_selected_index = int(idx)
        self._refresh_breached_transect_preview()

    def _on_breached_save_point(self) -> None:
        cone_id = self.breached_cone_id_edit.text().strip()
        if not cone_id:
            QMessageBox.warning(self, "Save point", "Cone ID is required")
            return

        if self.breached_profile_selected_index is None:
            QMessageBox.warning(
                self, "Save point", "No point selected - click on profile to select"
            )
            return

        angle_deg = float(self.breached_angle_spin.value())
        idx = int(self.breached_profile_selected_index)

        if not (
            0 <= idx < len(self.breached_profile_distances)
            and 0 <= idx < len(self.breached_profile_elevations)
        ):
            QMessageBox.warning(self, "Save point", "Invalid selected index")
            return

        distance_m = float(self.breached_profile_distances[idx])
        elevation_m = float(self.breached_profile_elevations[idx])
        confidence = self.breached_confidence_combo.currentText()
        notes = self.breached_notes_edit.text().strip()
        timestamp_utc = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        # Calculate analytical columns
        top_elevation = (
            float(np.nanmax(self.breached_profile_elevations))
            if np.any(np.isfinite(self.breached_profile_elevations))
            else np.nan
        )

        # Find center elevation (where distance ≈ 0)
        center_idx = np.argmin(np.abs(self.breached_profile_distances))
        center_elevation = (
            float(self.breached_profile_elevations[center_idx])
            if np.isfinite(self.breached_profile_elevations[center_idx])
            else np.nan
        )

        elevation_difference = (
            elevation_m - center_elevation if np.isfinite(center_elevation) else np.nan
        )

        csv_path = self._get_breached_save_csv_path()

        new_row = pd.DataFrame(
            [
                {
                    "cone_id": cone_id,
                    "angle_deg": angle_deg,
                    "distance_m": distance_m,
                    "elevation_m": elevation_m,
                    "top_elevation": top_elevation,
                    "center_elevation": center_elevation,
                    "elevation_difference": elevation_difference,
                    "confidence": confidence,
                    "notes": notes,
                    "timestamp_utc": timestamp_utc,
                }
            ]
        )

        try:
            if csv_path.exists():
                existing_df = pd.read_csv(csv_path, sep=";")
                combined_df = pd.concat([existing_df, new_row], ignore_index=True)
            else:
                combined_df = new_row

            combined_df.to_csv(csv_path, sep=";", index=False)

            status_msg = (
                f"✓ Saved: cone {cone_id}, angle {angle_deg:.1f}°, elev {elevation_m:.2f}m "
                f"[{confidence}]"
            )
            self.breached_save_status_label.setText(status_msg)
            self._refresh_breached_saved_points_table()

            self.breached_notes_edit.clear()
            self.breached_confidence_combo.setCurrentIndex(0)

            QMessageBox.information(
                self, "Save point", f"Point saved successfully!\n\n{status_msg}"
            )

        except (KeyError, TypeError, ValueError, OSError) as exc:
            QMessageBox.critical(self, "Save point", f"Error saving point:\n{exc}")
            self.breached_save_status_label.setText(f"✗ Error: {exc}")

