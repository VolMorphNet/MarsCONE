"""Mixin for the DemOverlayMixin section of MainWindow."""
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




class DemOverlayMixin:
    """Mixin — mixed into MainWindow via multiple inheritance."""

    def _build_dem_overlay_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        config_group = QGroupBox("DEM overlay settings")
        config_layout = QGridLayout(config_group)

        self.dem_overlay_dem_dir_edit = QLineEdit()
        self.dem_overlay_gpkg_edit = QLineEdit()
        self.dem_overlay_output_dir_edit = QLineEdit()
        self.dem_overlay_centers_hybrid_edit = QLineEdit()
        self.dem_overlay_cone_ids_edit = QLineEdit()
        self.dem_overlay_use_manual_fix_check = QCheckBox("Use manual fix metrics")
        self.dem_overlay_dpi_spin = QSpinBox()
        self.dem_overlay_dpi_spin.setRange(72, 1200)
        self.dem_overlay_azimuth_spin = QSpinBox()
        self.dem_overlay_azimuth_spin.setRange(0, 360)
        self.dem_overlay_altitude_spin = QSpinBox()
        self.dem_overlay_altitude_spin.setRange(1, 90)

        config_layout.addWidget(QLabel("DEM dir (cropped)"), 0, 0)
        config_layout.addWidget(self.dem_overlay_dem_dir_edit, 0, 1)
        config_layout.addWidget(self._browse_button(self.dem_overlay_dem_dir_edit, True), 0, 2)

        config_layout.addWidget(QLabel("Database GPKG"), 1, 0)
        config_layout.addWidget(self.dem_overlay_gpkg_edit, 1, 1)
        config_layout.addWidget(self._browse_button(self.dem_overlay_gpkg_edit, False), 1, 2)

        config_layout.addWidget(QLabel("Output dir"), 2, 0)
        config_layout.addWidget(self.dem_overlay_output_dir_edit, 2, 1)
        config_layout.addWidget(self._browse_button(self.dem_overlay_output_dir_edit, True), 2, 2)

        config_layout.addWidget(QLabel("Centers hybrid GPKG"), 3, 0)
        config_layout.addWidget(self.dem_overlay_centers_hybrid_edit, 3, 1)
        config_layout.addWidget(
            self._browse_button(self.dem_overlay_centers_hybrid_edit, False), 3, 2
        )

        config_layout.addWidget(QLabel("Cone IDs (comma-separated, empty = all)"), 4, 0)
        config_layout.addWidget(self.dem_overlay_cone_ids_edit, 4, 1)
        self.dem_overlay_all_ids_button = QPushButton("All IDs")
        self.dem_overlay_all_ids_button.clicked.connect(self.dem_overlay_cone_ids_edit.clear)
        config_layout.addWidget(self.dem_overlay_all_ids_button, 4, 2)
        config_layout.addWidget(self.dem_overlay_use_manual_fix_check, 4, 3)
        self.dem_overlay_use_manual_fix_check.toggled.connect(
            lambda _checked: self._refresh_dem_overlay_preview(reset_to_first=True)
        )

        config_layout.addWidget(QLabel("DPI"), 5, 0)
        config_layout.addWidget(self.dem_overlay_dpi_spin, 5, 1)
        config_layout.addWidget(QLabel("Hillshade azimuth/altitude"), 5, 2)
        az_alt_row = QHBoxLayout()
        az_alt_row.addWidget(self.dem_overlay_azimuth_spin)
        az_alt_row.addWidget(self.dem_overlay_altitude_spin)
        config_layout.addLayout(az_alt_row, 5, 3)

        actions_row = QHBoxLayout()
        self.dem_overlay_defaults_button = QPushButton("Use base-path defaults")
        self.dem_overlay_read_data_button = QPushButton("Read data")
        self.dem_overlay_run_button = QPushButton("Run DEM overlay")
        self.dem_overlay_open_output_button = QPushButton("Open output folder")
        actions_row.addWidget(self.dem_overlay_defaults_button)
        actions_row.addWidget(self.dem_overlay_read_data_button)
        actions_row.addWidget(self.dem_overlay_run_button)
        actions_row.addWidget(self.dem_overlay_open_output_button)
        actions_row.addStretch(1)

        self.dem_overlay_defaults_button.clicked.connect(
            self._set_dem_overlay_defaults_from_base_path
        )
        self.dem_overlay_read_data_button.clicked.connect(self._read_dem_overlay_data)
        self.dem_overlay_run_button.clicked.connect(self._run_dem_overlay)
        self.dem_overlay_open_output_button.clicked.connect(self._open_dem_overlay_output_dir)

        preview_group = QGroupBox("DEM overlay preview")
        preview_layout = QVBoxLayout(preview_group)
        nav_row = QHBoxLayout()
        self.dem_overlay_prev_button = QPushButton("<- Prev")
        self.dem_overlay_next_button = QPushButton("Next ->")
        self.dem_overlay_preview_label = QLabel("No overlay images yet.")
        self.dem_overlay_preview_label.setAlignment(Qt.AlignCenter)
        self.dem_overlay_preview_label.setMinimumHeight(300)
        self.dem_overlay_preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.dem_overlay_context_label = QLabel("Click Area Preview to generate mini-map.")
        self.dem_overlay_context_label.setAlignment(Qt.AlignCenter)
        self.dem_overlay_context_label.setMinimumHeight(300)
        self.dem_overlay_context_label.setMinimumWidth(280)
        self.dem_overlay_context_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.dem_overlay_area_preview_button = QPushButton("Area Preview")
        self.dem_overlay_preview_file_label = QLabel("0/0")
        self.dem_overlay_preview_file_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.dem_overlay_filter_edit = QLineEdit()
        self.dem_overlay_filter_edit.setPlaceholderText("Filter cone ID (e.g. 10)")
        self.dem_overlay_filter_edit.setMaximumWidth(180)
        self.dem_overlay_topology_label = QLabel("Current cone: -")
        self.dem_overlay_topology_label.setMinimumWidth(170)
        self.dem_overlay_topology_combo = QComboBox()
        self.dem_overlay_topology_combo.addItems(["simple", "breached"])
        self.dem_overlay_topology_combo.setMinimumWidth(120)
        self.dem_overlay_apply_topology_button = QPushButton("Apply type")
        self.dem_overlay_filter_apply_button = QPushButton("Apply")
        self.dem_overlay_filter_clear_button = QPushButton("Clear")

        nav_row.addWidget(self.dem_overlay_prev_button)
        nav_row.addWidget(self.dem_overlay_next_button)
        nav_row.addWidget(self.dem_overlay_area_preview_button)
        nav_row.addWidget(self.dem_overlay_preview_file_label)
        nav_row.addStretch(1)
        nav_row.addWidget(QLabel("Cone ID"))
        nav_row.addWidget(self.dem_overlay_filter_edit)
        nav_row.addWidget(self.dem_overlay_filter_apply_button)
        nav_row.addWidget(self.dem_overlay_filter_clear_button)
        nav_row.addSpacing(12)
        nav_row.addWidget(self.dem_overlay_topology_label)
        nav_row.addWidget(self.dem_overlay_topology_combo)
        nav_row.addWidget(self.dem_overlay_apply_topology_button)

        self.dem_overlay_prev_button.clicked.connect(self._show_previous_dem_overlay_image)
        self.dem_overlay_next_button.clicked.connect(self._show_next_dem_overlay_image)
        self.dem_overlay_area_preview_button.clicked.connect(self._generate_dem_area_preview)
        self.dem_overlay_filter_apply_button.clicked.connect(
            lambda: self._refresh_dem_overlay_preview(reset_to_first=True)
        )
        self.dem_overlay_filter_edit.returnPressed.connect(
            lambda: self._refresh_dem_overlay_preview(reset_to_first=True)
        )
        self.dem_overlay_filter_clear_button.clicked.connect(self._clear_dem_overlay_filter)
        self.dem_overlay_apply_topology_button.clicked.connect(
            self._dem_overlay_apply_topology_override
        )

        preview_layout.addLayout(nav_row)
        image_row = QHBoxLayout()
        image_row.addWidget(self.dem_overlay_preview_label, stretch=5)
        image_row.addWidget(self.dem_overlay_context_label, stretch=2)
        preview_layout.addLayout(image_row)

        logs_group = QGroupBox("DEM overlay logs")
        logs_layout = QVBoxLayout(logs_group)
        self.dem_overlay_log_output = QPlainTextEdit()
        self.dem_overlay_log_output.setReadOnly(True)
        self.dem_overlay_log_output.setLineWrapMode(QPlainTextEdit.NoWrap)
        logs_layout.addWidget(self.dem_overlay_log_output)

        bottom_splitter = QSplitter(Qt.Horizontal)
        bottom_splitter.addWidget(preview_group)
        bottom_splitter.addWidget(logs_group)
        bottom_splitter.setSizes([700, 500])

        layout.addWidget(config_group)
        layout.addLayout(actions_row)
        layout.addWidget(bottom_splitter, stretch=1)
        return page

    def _current_dem_overlay_cone_id(self) -> str | None:
        if not self.dem_overlay_images or self.dem_overlay_image_index < 0:
            return None
        if self.dem_overlay_image_index >= len(self.dem_overlay_images):
            return None
        image_name = self.dem_overlay_images[self.dem_overlay_image_index].name
        return self._extract_cone_id_from_dem_overlay_name(image_name)

    def _sync_dem_overlay_topology_controls(self) -> None:
        cone_id = self._current_dem_overlay_cone_id()
        if not cone_id:
            self.dem_overlay_topology_label.setText("Current cone: -")
            self.dem_overlay_topology_combo.setCurrentText("simple")
            self.dem_overlay_topology_combo.setEnabled(False)
            self.dem_overlay_apply_topology_button.setEnabled(False)
            return

        self.dem_overlay_topology_combo.setEnabled(True)
        self.dem_overlay_apply_topology_button.setEnabled(True)

        work_df = ensure_breach_columns(self.complex_breach_singles_df)
        match = work_df[work_df["cone_id"].astype(str) == cone_id]
        active_match = (
            match[match["active"]] if not match.empty and "active" in match.columns else match
        )
        if not active_match.empty:
            topology_type = str(active_match.iloc[-1].get("topology_type", "simple"))
            if topology_type not in {"simple", "breached"}:
                topology_type = "breached"
            self.dem_overlay_topology_combo.setCurrentText(topology_type)
            self.dem_overlay_topology_label.setText(f"Current cone: {cone_id} (override)")
        else:
            self.dem_overlay_topology_combo.setCurrentText("simple")
            self.dem_overlay_topology_label.setText(f"Current cone: {cone_id} (default)")

    def _dem_overlay_apply_topology_override(self) -> None:
        cone_id = self._current_dem_overlay_cone_id()
        if not cone_id:
            QMessageBox.information(self, "DEM overlay", "No current cone is selected in preview.")
            return

        active_pairs = ensure_pair_columns(self.complex_pairs_df)
        for _, pair_row in active_pairs[active_pairs["active"]].iterrows():
            if cone_id in parse_member_ids(str(pair_row.get("member_ids", ""))):
                QMessageBox.information(
                    self,
                    "DEM overlay",
                    (
                        f"Cone {cone_id} belongs to active complex "
                        f"'{pair_row.get('complex_id', '')}'.\n"
                        "Edit complex topology in the Complex Cones tab."
                    ),
                )
                return

        topology_type = self.dem_overlay_topology_combo.currentText().strip().lower()
        work_df = ensure_breach_columns(self.complex_breach_singles_df)
        existing_mask = work_df["cone_id"].astype(str) == cone_id
        reason = "set from DEM overlay"
        new_row = {
            "cone_id": cone_id,
            "topology_type": topology_type,
            "reason": reason,
            "active": True,
        }

        if existing_mask.any():
            for column, value in new_row.items():
                work_df.loc[existing_mask, column] = value
            self._complex_append_log(
                f"Updated single-cone topology from DEM overlay: {cone_id} -> {topology_type}"
            )
        else:
            work_df = pd.concat([work_df, pd.DataFrame([new_row])], ignore_index=True)
            self._complex_append_log(
                f"Added single-cone topology from DEM overlay: {cone_id} -> {topology_type}"
            )

        self.complex_breach_singles_df = ensure_breach_columns(work_df)
        self.complex_breach_singles_model.set_dataframe(self.complex_breach_singles_df)
        self.complex_breach_singles_table.resizeColumnsToContents()
        self._breach_save_singles()
        self._sync_dem_overlay_topology_controls()
        self.statusBar().showMessage(f"Cone {cone_id} marked as {topology_type}.", 4000)

    def _read_dem_overlay_data(self, show_message: bool = True) -> None:
        output_dir = self._effective_dem_overlay_output_dir()
        self._refresh_dem_overlay_preview(reset_to_first=True)
        self._load_dem_area_preview_if_available()

        if show_message:
            index_path = output_dir / "dem_overlay_index.csv"
            if output_dir.exists() and index_path.exists():
                self.statusBar().showMessage("DEM overlay data loaded from output folder.", 5000)
            elif output_dir.exists():
                self.statusBar().showMessage(
                    "DEM overlay images loaded (index file missing).", 5000
                )
            else:
                self.statusBar().showMessage("DEM overlay output folder not found.", 5000)

    def _effective_dem_overlay_output_dir(self) -> Path:
        output_dir = Path(self.dem_overlay_output_dir_edit.text().strip())
        if self.dem_overlay_use_manual_fix_check.isChecked():
            return output_dir / "manual_fix"
        return output_dir

    def _set_dem_overlay_defaults_from_base_path(self) -> None:
        base_path = Path(self.base_path_edit.text().strip())
        self.dem_overlay_dem_dir_edit.setText(
            str(base_path / "output" / "generator" / "dem" / "cropped")
        )
        self.dem_overlay_gpkg_edit.setText(str(base_path / "db" / "database.gpkg"))
        self.dem_overlay_output_dir_edit.setText(
            str(base_path / "output" / "figures" / "dem_overlay")
        )
        self.dem_overlay_centers_hybrid_edit.setText(
            str(base_path / "output" / "analyzer" / "shapes" / "centers_hybrid.gpkg")
        )

    def _run_dem_overlay(self) -> None:
        if (
            self.dem_overlay_process is not None
            and self.dem_overlay_process.state() != QProcess.NotRunning
        ):
            QMessageBox.information(self, "DEM overlay", "DEM overlay process is already running.")
            return

        self.state = self._collect_state_from_form()
        save_state(self.mvp_root, self.state)

        python_executable = self.state.get("python_executable") or "python"
        dem_dir = Path(self.dem_overlay_dem_dir_edit.text().strip())
        gpkg_path = Path(self.dem_overlay_gpkg_edit.text().strip())
        output_dir = self._effective_dem_overlay_output_dir()
        centers_hybrid_path = (
            Path(self.dem_overlay_centers_hybrid_edit.text().strip())
            if self.dem_overlay_centers_hybrid_edit.text().strip()
            else None
        )

        problems = []
        if self.python_edit.text().strip() and not Path(python_executable).exists():
            problems.append(f"Python executable not found: {python_executable}")
        if not dem_dir.exists():
            problems.append(f"DEM directory not found: {dem_dir}")
        if not gpkg_path.exists():
            problems.append(f"GeoPackage not found: {gpkg_path}")
        if centers_hybrid_path and not centers_hybrid_path.exists():
            problems.append(f"Centers hybrid GPKG not found: {centers_hybrid_path}")

        if problems:
            QMessageBox.warning(self, "DEM overlay validation failed", "\n".join(problems))
            return

        self.dem_overlay_log_output.clear()
        self.dem_overlay_log_output.appendPlainText("=== Running DEM overlay ===")
        self.dem_overlay_run_button.setEnabled(False)

        args = [
            "-m",
            "marscone_mvp.dem_overlay_cli",
            "--dem-dir",
            str(dem_dir),
            "--gpkg-path",
            str(gpkg_path),
            "--output-dir",
            str(output_dir),
            "--dpi",
            str(self.dem_overlay_dpi_spin.value()),
            "--azimuth",
            str(self.dem_overlay_azimuth_spin.value()),
            "--altitude",
            str(self.dem_overlay_altitude_spin.value()),
        ]

        if centers_hybrid_path:
            args.extend(["--centers-hybrid-path", str(centers_hybrid_path)])

        if self.dem_overlay_use_manual_fix_check.isChecked():
            args.append("--use-manual-fix")

        cone_ids = self.dem_overlay_cone_ids_edit.text().strip()
        if cone_ids and cone_ids.lower() not in {"all", "*"}:
            args.extend(["--cone-ids", cone_ids])

        process = QProcess(self)
        process.setProgram(python_executable)
        process.setArguments(args)
        process.setWorkingDirectory(str(self.mvp_root))
        process_environment = QProcessEnvironment.systemEnvironment()
        if self.ignore_celestial_body_check.isChecked():
            process_environment.insert("PROJ_IGNORE_CELESTIAL_BODY", "YES")
        process.setProcessEnvironment(process_environment)

        process.readyReadStandardOutput.connect(self._on_dem_overlay_stdout)
        process.readyReadStandardError.connect(self._on_dem_overlay_stderr)
        process.finished.connect(self._on_dem_overlay_finished)

        self.dem_overlay_process = process
        process.start()
        self.statusBar().showMessage("Running DEM overlay...")

    def _on_dem_overlay_stdout(self) -> None:
        if self.dem_overlay_process is None:
            return
        text = self._read_process_buffer(self.dem_overlay_process.readAllStandardOutput)
        if text:
            self.dem_overlay_log_output.appendPlainText(text.rstrip())

    def _on_dem_overlay_stderr(self) -> None:
        if self.dem_overlay_process is None:
            return
        text = self._read_process_buffer(self.dem_overlay_process.readAllStandardError)
        if text:
            self.dem_overlay_log_output.appendPlainText(text.rstrip())

    def _on_dem_overlay_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        success = exit_status == QProcess.NormalExit and exit_code == 0
        self.dem_overlay_run_button.setEnabled(True)

        if success:
            self.statusBar().showMessage("DEM overlay finished.", 4000)
            self.dem_overlay_log_output.appendPlainText("=== DEM overlay finished successfully ===")
            self._refresh_dem_overlay_preview(reset_to_first=True)
        else:
            self.statusBar().showMessage("DEM overlay failed.", 4000)
            self.dem_overlay_log_output.appendPlainText("=== DEM overlay failed ===")

        self.dem_overlay_process = None

    def _open_dem_overlay_output_dir(self) -> None:
        output_dir = self._effective_dem_overlay_output_dir()
        if not output_dir.exists():
            QMessageBox.information(
                self, "DEM overlay", f"Output directory not found:\n{output_dir}"
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_dir)))

    def _clear_dem_overlay_filter(self) -> None:
        self.dem_overlay_filter_edit.clear()
        self._refresh_dem_overlay_preview(reset_to_first=True)

    def _refresh_dem_overlay_preview(self, reset_to_first: bool) -> None:
        current_cone = None
        if self.dem_overlay_images and 0 <= self.dem_overlay_image_index < len(
            self.dem_overlay_images
        ):
            current_cone = self._extract_cone_id_from_dem_overlay_name(
                self.dem_overlay_images[self.dem_overlay_image_index].name
            )

        output_dir = self._effective_dem_overlay_output_dir()
        filter_value = self.dem_overlay_filter_edit.text().strip()
        if not output_dir.exists():
            self.dem_overlay_images = []
            self.dem_overlay_image_index = -1
            self.dem_overlay_preview_label.setText("No overlay images yet.")
            self._update_dem_overlay_area_preview_highlight(None)
            self.dem_overlay_preview_file_label.setText("0/0")
            self.dem_overlay_prev_button.setEnabled(False)
            self.dem_overlay_next_button.setEnabled(False)
            self._sync_dem_overlay_topology_controls()
            return

        self.dem_overlay_images = sorted(output_dir.glob("*.png"))

        if not self.dem_overlay_images:
            self.dem_overlay_image_index = -1
            self.dem_overlay_preview_label.setText("No overlay PNG files in output directory.")
            self._update_dem_overlay_area_preview_highlight(None)
            self.dem_overlay_preview_file_label.setText("0/0")
            self.dem_overlay_prev_button.setEnabled(False)
            self.dem_overlay_next_button.setEnabled(False)
            self._sync_dem_overlay_topology_controls()
            return

        if reset_to_first and filter_value:
            jump_index = next(
                (
                    idx
                    for idx, image_path in enumerate(self.dem_overlay_images)
                    if f"cone{filter_value}_" in image_path.name
                ),
                -1,
            )
            if jump_index >= 0:
                self.dem_overlay_image_index = jump_index
            else:
                self.dem_overlay_image_index = 0
                self.statusBar().showMessage(
                    f"Cone ID {filter_value} not found in current preview list.",
                    4000,
                )
        elif reset_to_first:
            self.dem_overlay_image_index = 0
        elif current_cone is not None:
            match_index = next(
                (
                    idx
                    for idx, image_path in enumerate(self.dem_overlay_images)
                    if self._extract_cone_id_from_dem_overlay_name(image_path.name) == current_cone
                ),
                -1,
            )
            if match_index >= 0:
                self.dem_overlay_image_index = match_index
            else:
                self.dem_overlay_image_index = min(
                    max(self.dem_overlay_image_index, 0),
                    len(self.dem_overlay_images) - 1,
                )
        else:
            self.dem_overlay_image_index = min(
                max(self.dem_overlay_image_index, 0),
                len(self.dem_overlay_images) - 1,
            )
        self._show_dem_overlay_image()

    def _show_dem_overlay_image(self) -> None:
        if not self.dem_overlay_images or self.dem_overlay_image_index < 0:
            self.dem_overlay_preview_label.setText("No overlay images yet.")
            self._update_dem_overlay_area_preview_highlight(None)
            self.dem_overlay_preview_file_label.setText("0/0")
            self.dem_overlay_prev_button.setEnabled(False)
            self.dem_overlay_next_button.setEnabled(False)
            self._sync_dem_overlay_topology_controls()
            return

        image_path = self.dem_overlay_images[self.dem_overlay_image_index]
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            self.dem_overlay_preview_label.setText(f"Could not load image: {image_path.name}")
            return

        self.dem_overlay_current_pixmap = pixmap
        scaled = pixmap.scaled(
            self.dem_overlay_preview_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.dem_overlay_preview_label.setPixmap(scaled)
        self.dem_overlay_preview_file_label.setText(
            f"{self.dem_overlay_image_index + 1}/{len(self.dem_overlay_images)}: {image_path.name}"
        )
        self.dem_overlay_prev_button.setEnabled(self.dem_overlay_image_index > 0)
        self.dem_overlay_next_button.setEnabled(
            self.dem_overlay_image_index < len(self.dem_overlay_images) - 1
        )

        cone_id = self._extract_cone_id_from_dem_overlay_name(image_path.name)
        if cone_id is None:
            self._update_dem_overlay_area_preview_highlight(None)
        else:
            self._update_dem_overlay_area_preview_highlight(cone_id)
        self._sync_dem_overlay_topology_controls()

    def _clear_dem_overlay_context_preview(self, message: str) -> None:
        self.dem_overlay_context_current_pixmap = None
        self.dem_overlay_context_label.clear()
        self.dem_overlay_context_label.setText(message)

    def _extract_cone_id_from_dem_overlay_name(self, filename: str) -> str | None:
        match = re.match(r"cone(\d+)_overlay\.png$", filename)
        if not match:
            return None
        return match.group(1)

    def _compute_hillshade_array(
        self,
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
        shaded = np.sin(altitude) * np.sin(slope) + np.cos(altitude) * np.cos(slope) * np.cos(
            azimuth - aspect
        )
        return np.clip(shaded, 0, 1)

    def _dem_area_preview_paths(self) -> tuple[Path, Path]:
        output_dir = self._effective_dem_overlay_output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir / "dem_area_preview.jpg", output_dir / "dem_area_preview_meta.json"

    def _resolve_dem_area_preview_source_paths(self) -> tuple[Path | None, Path | None]:
        base_path = Path(self.base_path_edit.text().strip())
        dem_dir = base_path / "input" / "dem"
        dem_files = sorted(
            list(dem_dir.glob("*.tif"))
            + list(dem_dir.glob("*.tiff"))
            + list(dem_dir.glob("*.TIF"))
            + list(dem_dir.glob("*.TIFF"))
        )
        if not dem_files:
            return None, None

        dem_path = dem_files[0]
        centers_path = Path(self.dem_overlay_centers_hybrid_edit.text().strip())
        if not centers_path.exists():
            centers_path = base_path / "output" / "analyzer" / "shapes" / "centers_hybrid.gpkg"
        if not centers_path.exists():
            return dem_path, None
        return dem_path, centers_path

    def _load_dem_area_preview_if_available(self) -> None:
        dem_path, centers_path = self._resolve_dem_area_preview_source_paths()
        if dem_path is None or centers_path is None:
            self.dem_overlay_area_preview_base_pixmap = None
            self.dem_overlay_area_preview_bounds = None
            self.dem_overlay_area_preview_centers = {}
            self._clear_dem_overlay_context_preview("Click Area Preview to generate mini-map.")
            return

        if not self._try_load_dem_area_preview_from_cache(dem_path, centers_path):
            self.dem_overlay_area_preview_base_pixmap = None
            self.dem_overlay_area_preview_bounds = None
            self.dem_overlay_area_preview_centers = {}
            self._clear_dem_overlay_context_preview("Click Area Preview to generate mini-map.")

    def _try_load_dem_area_preview_from_cache(self, dem_path: Path, centers_path: Path) -> bool:
        area_preview_path, area_meta_path = self._dem_area_preview_paths()
        if not area_preview_path.exists() or not area_meta_path.exists():
            return False

        output_mtime = min(area_preview_path.stat().st_mtime, area_meta_path.stat().st_mtime)
        source_mtime = max(dem_path.stat().st_mtime, centers_path.stat().st_mtime)
        if source_mtime > output_mtime:
            return False

        pixmap = QPixmap(str(area_preview_path))
        if pixmap.isNull():
            return False

        try:
            meta = json.loads(area_meta_path.read_text(encoding="utf-8"))
            bounds_raw = meta.get("bounds")
            centers_raw = meta.get("centers", {})
            if not isinstance(bounds_raw, list) or len(bounds_raw) != 4:
                return False
            bounds = tuple(float(v) for v in bounds_raw)
            centers_map: dict[str, tuple[float, float]] = {}
            if isinstance(centers_raw, dict):
                for cone_id, xy in centers_raw.items():
                    if isinstance(xy, list) and len(xy) == 2:
                        centers_map[str(cone_id)] = (float(xy[0]), float(xy[1]))
        except Exception:  # pylint: disable=broad-exception-caught
            return False

        self.dem_overlay_area_preview_base_pixmap = pixmap
        self.dem_overlay_area_preview_bounds = bounds
        self.dem_overlay_area_preview_centers = centers_map

        current_cone = None
        if self.dem_overlay_images and self.dem_overlay_image_index >= 0:
            current_name = self.dem_overlay_images[self.dem_overlay_image_index].name
            current_cone = self._extract_cone_id_from_dem_overlay_name(current_name)
        self._update_dem_overlay_area_preview_highlight(current_cone)
        self.statusBar().showMessage(f"Area Preview loaded from cache: {area_preview_path}", 4000)
        return True

    def _generate_dem_area_preview(self) -> None:
        dem_path, centers_path = self._resolve_dem_area_preview_source_paths()
        if dem_path is None:
            self._clear_dem_overlay_context_preview("No DEM file in base_path/input/dem.")
            return

        if centers_path is None:
            self._clear_dem_overlay_context_preview("Centers file not found.")
            return

        if self._try_load_dem_area_preview_from_cache(dem_path, centers_path):
            return

        centers_gdf = gpd.read_file(centers_path)
        if "cone_id" in centers_gdf.columns:
            centers_gdf = centers_gdf.copy()
            centers_gdf["cone_id_norm"] = (
                centers_gdf["cone_id"].astype(str).str.replace(r"\.0$", "", regex=True)
            )

        with rasterio.open(dem_path) as src:
            target_max = 900
            scale = max(src.width, src.height) / float(target_max)
            scale = max(scale, 1.0)
            out_width = max(1, int(round(src.width / scale)))
            out_height = max(1, int(round(src.height / scale)))

            dem_band = src.read(
                1,
                masked=True,
                out_shape=(out_height, out_width),
                resampling=Resampling.bilinear,
            )
            dem = np.asarray(dem_band.filled(np.nan), dtype=float)

            bounds = src.bounds
            extent = [bounds.left, bounds.right, bounds.bottom, bounds.top]
            scale_x = src.width / float(out_width)
            scale_y = src.height / float(out_height)
            preview_transform = src.transform * rasterio.Affine.scale(scale_x, scale_y)
            hillshade = self._compute_hillshade_array(
                dem,
                preview_transform,
                float(self.dem_overlay_azimuth_spin.value()),
                float(self.dem_overlay_altitude_spin.value()),
            )

        fig, ax = plt.subplots(figsize=(3.4, 4.8))
        ax.imshow(hillshade, cmap="gray", extent=extent, origin="upper")

        if centers_gdf is not None and not centers_gdf.empty and "geometry" in centers_gdf.columns:
            ax.scatter(
                centers_gdf.geometry.x,
                centers_gdf.geometry.y,
                s=14,
                color="white",
                edgecolors="black",
                linewidths=0.3,
                alpha=0.8,
                zorder=5,
            )
        ax.set_title("Area preview")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_aspect("equal")

        area_preview_path, area_meta_path = self._dem_area_preview_paths()
        fig.savefig(area_preview_path, format="jpg", dpi=130, bbox_inches="tight", pad_inches=0.04)
        plt.close(fig)

        pixmap = QPixmap(str(area_preview_path))

        if pixmap.isNull():
            self._clear_dem_overlay_context_preview("Could not render DEM context preview.")
            return

        self.dem_overlay_area_preview_base_pixmap = pixmap
        self.dem_overlay_area_preview_bounds = (
            bounds.left,
            bounds.right,
            bounds.bottom,
            bounds.top,
        )

        centers_map: dict[str, tuple[float, float]] = {}
        if centers_gdf is not None and not centers_gdf.empty and "geometry" in centers_gdf.columns:
            for _, row in centers_gdf.iterrows():
                cone_id_norm = str(row["cone_id_norm"])
                centers_map[cone_id_norm] = (float(row.geometry.x), float(row.geometry.y))
        self.dem_overlay_area_preview_centers = centers_map

        meta = {
            "bounds": [bounds.left, bounds.right, bounds.bottom, bounds.top],
            "centers": {cone_id: [xy[0], xy[1]] for cone_id, xy in centers_map.items()},
            "source_dem": str(dem_path),
            "source_centers": str(centers_path),
        }
        try:
            area_meta_path.write_text(json.dumps(meta), encoding="utf-8")
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        current_cone = None
        if self.dem_overlay_images and self.dem_overlay_image_index >= 0:
            current_name = self.dem_overlay_images[self.dem_overlay_image_index].name
            current_cone = self._extract_cone_id_from_dem_overlay_name(current_name)
        self._update_dem_overlay_area_preview_highlight(current_cone)
        self.statusBar().showMessage(f"Area Preview saved: {area_preview_path}", 4000)

    def _update_dem_overlay_area_preview_highlight(self, cone_id: str | None) -> None:
        base = self.dem_overlay_area_preview_base_pixmap
        bounds = self.dem_overlay_area_preview_bounds

        if base is None or bounds is None:
            self._clear_dem_overlay_context_preview("Click Area Preview to generate mini-map.")
            return

        pixmap = base.copy()
        if cone_id and cone_id in self.dem_overlay_area_preview_centers:
            x_geo, y_geo = self.dem_overlay_area_preview_centers[cone_id]
            left, right, bottom, top = bounds
            if right != left and top != bottom:
                px = int((x_geo - left) / (right - left) * pixmap.width())
                py = int((top - y_geo) / (top - bottom) * pixmap.height())

                painter = QPainter(pixmap)
                pen = QPen(QColor("white"))
                pen.setWidth(2)
                painter.setPen(pen)
                painter.setBrush(QColor("red"))
                painter.drawEllipse(px - 5, py - 5, 10, 10)
                painter.end()

        self.dem_overlay_context_current_pixmap = pixmap
        scaled = pixmap.scaled(
            self.dem_overlay_context_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.dem_overlay_context_label.setPixmap(scaled)

    def _show_previous_dem_overlay_image(self) -> None:
        if self.dem_overlay_image_index <= 0:
            return
        self.dem_overlay_image_index -= 1
        self._show_dem_overlay_image()

    def _show_next_dem_overlay_image(self) -> None:
        if self.dem_overlay_image_index >= len(self.dem_overlay_images) - 1:
            return
        self.dem_overlay_image_index += 1
        self._show_dem_overlay_image()

