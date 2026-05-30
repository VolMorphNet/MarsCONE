"""Mixin for the CrossSectionMixin section of MainWindow."""
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




class CrossSectionMixin:
    """Mixin — mixed into MainWindow via multiple inheritance."""

    def _build_crosssection_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        config_group = QGroupBox("Cross-section settings")
        config_layout = QGridLayout(config_group)

        self.cs_profile_dir_edit = QLineEdit()
        self.cs_finder_path_edit = QLineEdit()
        self.cs_output_dir_edit = QLineEdit()
        self.cs_cone_ids_edit = QLineEdit()
        self.cs_dpi_spin = QSpinBox()
        self.cs_dpi_spin.setRange(72, 1200)
        self.cs_angle_tol_spin = QDoubleSpinBox()
        self.cs_angle_tol_spin.setDecimals(4)
        self.cs_angle_tol_spin.setRange(0.0, 10.0)
        self.cs_angle_tol_spin.setSingleStep(0.001)

        config_layout.addWidget(QLabel("Profile dir"), 0, 0)
        config_layout.addWidget(self.cs_profile_dir_edit, 0, 1)
        config_layout.addWidget(self._browse_button(self.cs_profile_dir_edit, True), 0, 2)

        config_layout.addWidget(QLabel("Finder CSV"), 1, 0)
        config_layout.addWidget(self.cs_finder_path_edit, 1, 1)
        config_layout.addWidget(self._browse_button(self.cs_finder_path_edit, False), 1, 2)

        config_layout.addWidget(QLabel("Output dir"), 2, 0)
        config_layout.addWidget(self.cs_output_dir_edit, 2, 1)
        config_layout.addWidget(self._browse_button(self.cs_output_dir_edit, True), 2, 2)

        config_layout.addWidget(QLabel("Cone IDs (comma-separated, empty = all)"), 3, 0)
        config_layout.addWidget(self.cs_cone_ids_edit, 3, 1)
        self.cs_all_ids_button = QPushButton("All IDs")
        self.cs_all_ids_button.clicked.connect(self.cs_cone_ids_edit.clear)
        config_layout.addWidget(self.cs_all_ids_button, 3, 2)

        config_layout.addWidget(QLabel("DPI"), 4, 0)
        config_layout.addWidget(self.cs_dpi_spin, 4, 1)
        config_layout.addWidget(QLabel("Angle tolerance (deg)"), 4, 2)
        config_layout.addWidget(self.cs_angle_tol_spin, 4, 3)

        actions_row = QHBoxLayout()
        self.cs_use_defaults_button = QPushButton("Use base-path defaults")
        self.cs_read_data_button = QPushButton("Read data")
        self.cs_run_button = QPushButton("Run cross-sections")
        self.cs_open_output_button = QPushButton("Open output folder")
        self.cs_cross_metrics_button = QPushButton("Cross Metrics")
        self.cs_cone_metrics_button = QPushButton("Cone Metrics")
        self.cs_metrics_stats_button = QPushButton("Metrics stats")
        actions_row.addWidget(self.cs_use_defaults_button)
        actions_row.addWidget(self.cs_read_data_button)
        actions_row.addWidget(self.cs_run_button)
        actions_row.addWidget(self.cs_open_output_button)
        actions_row.addWidget(self.cs_cross_metrics_button)
        actions_row.addWidget(self.cs_cone_metrics_button)
        actions_row.addWidget(self.cs_metrics_stats_button)
        actions_row.addStretch(1)

        self.cs_use_defaults_button.clicked.connect(self._set_cross_section_defaults_from_base_path)
        self.cs_read_data_button.clicked.connect(self._read_cross_section_data)
        self.cs_run_button.clicked.connect(self._run_cross_sections)
        self.cs_open_output_button.clicked.connect(self._open_cross_section_output_dir)
        self.cs_cross_metrics_button.clicked.connect(self._show_cross_metrics_table)
        self.cs_cone_metrics_button.clicked.connect(self._show_cone_metrics_table)
        self.cs_metrics_stats_button.clicked.connect(self._show_cross_section_metrics_stats)

        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout(preview_group)
        nav_row = QHBoxLayout()
        self.cs_prev_button = QPushButton("<- Prev")
        self.cs_next_button = QPushButton("Next ->")
        self.cs_preview_label = QLabel("No plots yet.")
        self.cs_preview_label.setAlignment(Qt.AlignCenter)
        self.cs_preview_label.setMinimumHeight(300)
        self.cs_preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.cs_preview_file_label = QLabel("0/0")
        self.cs_preview_file_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.cs_preview_source_label = QLabel("Source: -")
        self.cs_preview_source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.cs_preview_filter_edit = QLineEdit()
        self.cs_preview_filter_edit.setPlaceholderText("Filter cone ID (e.g. 10)")
        self.cs_preview_filter_edit.setMaximumWidth(180)
        self.cs_preview_use_manual_fix_check = QCheckBox("Use manual fix")
        self.cs_preview_filter_apply_button = QPushButton("Apply")
        self.cs_preview_filter_clear_button = QPushButton("Clear")

        nav_row.addWidget(self.cs_prev_button)
        nav_row.addWidget(self.cs_next_button)
        nav_row.addWidget(self.cs_preview_file_label)
        nav_row.addStretch(1)
        nav_row.addWidget(QLabel("Cone ID"))
        nav_row.addWidget(self.cs_preview_filter_edit)
        nav_row.addWidget(self.cs_preview_use_manual_fix_check)
        nav_row.addWidget(self.cs_preview_filter_apply_button)
        nav_row.addWidget(self.cs_preview_filter_clear_button)

        self.cs_prev_button.clicked.connect(self._show_previous_cross_section_image)
        self.cs_next_button.clicked.connect(self._show_next_cross_section_image)
        self.cs_preview_filter_apply_button.clicked.connect(
            lambda: self._refresh_cross_section_preview(reset_to_first=True)
        )
        self.cs_preview_filter_edit.returnPressed.connect(
            lambda: self._refresh_cross_section_preview(reset_to_first=True)
        )
        self.cs_preview_filter_clear_button.clicked.connect(self._clear_cross_section_filter)
        self.cs_preview_use_manual_fix_check.toggled.connect(
            lambda _checked: self._refresh_cross_section_preview(reset_to_first=False)
        )

        preview_layout.addLayout(nav_row)
        preview_layout.addWidget(self.cs_preview_source_label)
        preview_layout.addWidget(self.cs_preview_label)

        logs_group = QGroupBox("Cross-section logs")
        logs_layout = QVBoxLayout(logs_group)
        self.cs_log_output = QPlainTextEdit()
        self.cs_log_output.setReadOnly(True)
        self.cs_log_output.setLineWrapMode(QPlainTextEdit.NoWrap)
        logs_layout.addWidget(self.cs_log_output)

        bottom_splitter = QSplitter(Qt.Horizontal)
        bottom_splitter.addWidget(preview_group)
        bottom_splitter.addWidget(logs_group)
        bottom_splitter.setSizes([700, 500])

        layout.addWidget(config_group)
        layout.addLayout(actions_row)
        layout.addWidget(bottom_splitter, stretch=1)
        return page

    def _read_cross_section_data(self, show_message: bool = True) -> None:
        output_dir = self._effective_cross_section_output_dir()
        self._refresh_cross_section_preview(reset_to_first=True)

        if show_message:
            metrics_path = output_dir / "cross_section_metrics.csv"
            if output_dir.exists() and metrics_path.exists():
                self.statusBar().showMessage("Cross-section data loaded from output folder.", 5000)
            elif output_dir.exists():
                self.statusBar().showMessage(
                    "Cross-section images loaded (metrics file missing).", 5000
                )
            else:
                self.statusBar().showMessage("Cross-section output folder not found.", 5000)

    def _set_cross_section_defaults_from_base_path(self) -> None:
        base_path = Path(self.base_path_edit.text().strip())
        self.cs_profile_dir_edit.setText(
            str(base_path / "output" / "generator" / "profiles" / "whole")
        )
        self.cs_finder_path_edit.setText(str(base_path / "output" / "finder" / "finder_method.csv"))
        self.cs_output_dir_edit.setText(str(base_path / "output" / "figures" / "cross_sections"))

    def _run_cross_sections(self) -> None:
        if (
            self.cross_section_process is not None
            and self.cross_section_process.state() != QProcess.NotRunning
        ):
            QMessageBox.information(
                self, "Cross-section", "Cross-section process is already running."
            )
            return

        self.state = self._collect_state_from_form()
        save_state(self.mvp_root, self.state)

        python_executable = self.state.get("python_executable") or "python"
        profile_dir = Path(self.cs_profile_dir_edit.text().strip())
        finder_path = Path(self.cs_finder_path_edit.text().strip())
        output_dir = Path(self.cs_output_dir_edit.text().strip())

        problems = []
        if self.python_edit.text().strip() and not Path(python_executable).exists():
            problems.append(f"Python executable not found: {python_executable}")
        if not profile_dir.exists():
            problems.append(f"Profile directory not found: {profile_dir}")
        if not finder_path.exists():
            problems.append(f"Finder CSV not found: {finder_path}")

        if problems:
            QMessageBox.warning(self, "Cross-section validation failed", "\n".join(problems))
            return

        self.cs_log_output.clear()
        self.cs_log_output.appendPlainText("=== Running cross-sections ===")
        self.cs_run_button.setEnabled(False)

        args = [
            "-m",
            "marscone_mvp.cross_section_cli",
            "--profile-dir",
            str(profile_dir),
            "--finder-path",
            str(finder_path),
            "--output-dir",
            str(output_dir),
            "--dpi",
            str(self.cs_dpi_spin.value()),
            "--angle-tolerance",
            str(self.cs_angle_tol_spin.value()),
        ]

        cone_ids = self.cs_cone_ids_edit.text().strip()
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

        process.readyReadStandardOutput.connect(self._on_cross_section_stdout)
        process.readyReadStandardError.connect(self._on_cross_section_stderr)
        process.finished.connect(self._on_cross_section_finished)

        self.cross_section_process = process
        process.start()
        self.statusBar().showMessage("Running cross-sections...")

    def _read_process_buffer(self, reader) -> str:
        data = reader()
        return bytes(data).decode("utf-8", errors="replace")

    def _on_cross_section_stdout(self) -> None:
        if self.cross_section_process is None:
            return
        text = self._read_process_buffer(self.cross_section_process.readAllStandardOutput)
        if text:
            self.cs_log_output.appendPlainText(text.rstrip())

    def _on_cross_section_stderr(self) -> None:
        if self.cross_section_process is None:
            return
        text = self._read_process_buffer(self.cross_section_process.readAllStandardError)
        if text:
            self.cs_log_output.appendPlainText(text.rstrip())

    def _on_cross_section_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        success = exit_status == QProcess.NormalExit and exit_code == 0
        self.cs_run_button.setEnabled(True)

        if success:
            self.statusBar().showMessage("Cross-sections finished.", 4000)
            self.cs_log_output.appendPlainText("=== Cross-sections finished successfully ===")
            self._refresh_cross_section_preview(reset_to_first=True)
        else:
            self.statusBar().showMessage("Cross-sections failed.", 4000)
            self.cs_log_output.appendPlainText("=== Cross-sections failed ===")

        self.cross_section_process = None

    def _open_cross_section_output_dir(self) -> None:
        output_dir = self._effective_cross_section_output_dir()
        if not output_dir.exists():
            QMessageBox.information(
                self, "Cross-section", f"Output directory not found:\n{output_dir}"
            )
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_dir)))

    def _show_cross_metrics_table(self) -> None:
        self._show_metrics_table_dialog("results.csv", "Cross Metrics")

    def _show_cone_metrics_table(self) -> None:
        self._show_metrics_table_dialog("cone_summary.csv", "Cone Metrics")

    def _show_metrics_table_dialog(self, base_filename: str, title: str) -> None:
        source_df = pd.DataFrame()

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(980, 560)

        layout = QVBoxLayout(dialog)
        top_row = QHBoxLayout()
        use_manual_fix_check = QCheckBox("Use manual fix")
        use_manual_fix_check.setChecked(self.use_manual_fix_check.isChecked())
        source_label = QLabel("")
        top_row.addWidget(use_manual_fix_check)
        top_row.addWidget(source_label)
        top_row.addStretch(1)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Cone ID filter"))
        filter_combo = QComboBox(dialog)
        filter_combo.addItem("All")
        filter_combo.setMaximumWidth(140)
        filter_edit = QLineEdit(dialog)
        filter_edit.setPlaceholderText("e.g. 10")
        filter_edit.setMaximumWidth(180)
        apply_button = QPushButton("Apply", dialog)
        clear_button = QPushButton("Clear", dialog)
        filter_row.addWidget(filter_combo)
        filter_row.addWidget(filter_edit)
        filter_row.addWidget(apply_button)
        filter_row.addWidget(clear_button)
        filter_row.addStretch(1)

        table = QTableView(dialog)
        model = DataFrameTableModel(float_precision=2)
        table.setModel(model)
        table.setSortingEnabled(True)

        def apply_filter() -> None:
            nonlocal source_df
            cone_filter = filter_edit.text().strip()
            selected_combo = filter_combo.currentText().strip()
            if selected_combo and selected_combo != "All":
                cone_filter = selected_combo
            if not cone_filter:
                filtered = source_df
            else:
                if "cone_id" in source_df.columns:
                    filtered = source_df[source_df["cone_id"].astype(str) == cone_filter]
                else:
                    filtered = source_df.iloc[0:0]
            model.set_dataframe(filtered.reset_index(drop=True))
            table.resizeColumnsToContents()

        def clear_filter() -> None:
            filter_combo.setCurrentText("All")
            filter_edit.clear()
            apply_filter()

        def refresh_source() -> None:
            nonlocal source_df
            source_df = self._load_analyzer_metrics_csv(
                base_filename,
                title,
                use_manual_fix=use_manual_fix_check.isChecked(),
                show_error=False,
            )
            if source_df is None:
                source_df = pd.DataFrame()

            round_columns = ["H_left", "H_right", "D_left", "D_right"]
            for column in round_columns:
                if column in source_df.columns:
                    source_df[column] = pd.to_numeric(source_df[column], errors="coerce").round(2)

            source_name = (
                f"fix_{base_filename}" if use_manual_fix_check.isChecked() else base_filename
            )
            source_path = (
                Path(self.base_path_edit.text().strip()) / "output" / "analyzer" / source_name
            )
            source_label.setText(f"Source: {source_path}")

            filter_combo.blockSignals(True)
            filter_combo.clear()
            filter_combo.addItem("All")
            if "cone_id" in source_df.columns:
                unique_ids = sorted(source_df["cone_id"].astype(str).unique())
                filter_combo.addItems(unique_ids)
            filter_combo.blockSignals(False)
            apply_filter()

        apply_button.clicked.connect(apply_filter)
        clear_button.clicked.connect(clear_filter)
        filter_edit.returnPressed.connect(apply_filter)
        filter_combo.currentTextChanged.connect(lambda _text: apply_filter())
        use_manual_fix_check.toggled.connect(lambda _checked: refresh_source())

        layout.addLayout(top_row)
        layout.addLayout(filter_row)
        layout.addWidget(table)

        refresh_source()

        dialog.exec()

    def _show_cross_section_metrics_stats(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Cross-section metrics stats")
        dialog.resize(980, 560)

        layout = QVBoxLayout(dialog)
        top_row = QHBoxLayout()
        use_manual_fix_check = QCheckBox("Use manual fix")
        use_manual_fix_check.setChecked(self.use_manual_fix_check.isChecked())
        source_label = QLabel("")
        top_row.addWidget(use_manual_fix_check)
        top_row.addWidget(source_label)
        top_row.addStretch(1)

        table = QTableView(dialog)
        model = DataFrameTableModel(float_precision=2)
        table.setModel(model)
        table.setSortingEnabled(True)
        layout.addLayout(top_row)
        layout.addWidget(table)

        def refresh_stats() -> None:
            source_df = self._load_analyzer_metrics_csv(
                "cone_summary.csv",
                "Metrics stats",
                use_manual_fix=use_manual_fix_check.isChecked(),
                show_error=False,
            )
            if source_df is None:
                source_df = pd.DataFrame()

            metrics_df = self._extract_cone_metric_plot_columns(source_df)
            stats_df = self._build_stats_dataframe_from_metrics(metrics_df)
            if not stats_df.empty:
                value_columns = [
                    "min",
                    "p05",
                    "p25",
                    "p50 (median)",
                    "mean",
                    "p75",
                    "p95",
                    "max",
                ]
                for column in value_columns:
                    stats_df[column] = pd.to_numeric(stats_df[column], errors="coerce").round(2)

            output_dir = Path(self.base_path_edit.text().strip()) / "output" / "analyzer"
            output_dir.mkdir(parents=True, exist_ok=True)
            stats_name = (
                "fix_cross_metrics_stats.csv"
                if use_manual_fix_check.isChecked()
                else "cross_metrics_stats.csv"
            )
            stats_path = output_dir / stats_name
            if not stats_df.empty:
                stats_df.to_csv(stats_path, index=False, sep=";")

            source_name = (
                "fix_cone_summary.csv" if use_manual_fix_check.isChecked() else "cone_summary.csv"
            )
            source_label.setText(f"Source: {output_dir / source_name} | Saved stats: {stats_path}")
            model.set_dataframe(stats_df)
            table.resizeColumnsToContents()

        use_manual_fix_check.toggled.connect(lambda _checked: refresh_stats())
        refresh_stats()

        dialog.exec()

    def _show_cross_section_metrics_graphs(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Cross-section metrics graphs")
        dialog.resize(1040, 560)

        excluded_graph_metrics = {"volume", "H_WCO_ratio", "WCR_WCO_ratio"}

        layout = QVBoxLayout(dialog)
        top_row = QHBoxLayout()
        use_manual_fix_check = QCheckBox("Use manual fix")
        use_manual_fix_check.setChecked(self.use_manual_fix_check.isChecked())
        source_label = QLabel("")
        top_row.addWidget(use_manual_fix_check)
        top_row.addWidget(source_label)
        top_row.addStretch(1)
        layout.addLayout(top_row)

        figure, axes = plt.subplots(1, 2, figsize=(12, 4.8))
        canvas = FigureCanvas(figure)
        layout.addWidget(canvas)

        def refresh_graphs() -> None:
            source_df = self._load_analyzer_metrics_csv(
                "cone_summary.csv",
                "Metrics graphs",
                use_manual_fix=use_manual_fix_check.isChecked(),
                show_error=False,
            )
            axes[0].clear()
            axes[1].clear()

            if source_df is None:
                source_df = pd.DataFrame()

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
                if use_manual_fix_check.isChecked()
                else "cross_metrics_graphs.png"
            )
            graphs_path = output_dir / graph_name

            if numeric_df.dropna(how="all").empty or not numeric_columns:
                axes[0].text(0.5, 0.5, "No numeric values", ha="center", va="center")
                axes[0].set_axis_off()
            else:
                numeric_df = numeric_df[numeric_columns]
                numeric_df.boxplot(ax=axes[0])
                axes[0].set_title("Metric distributions (boxplot)")
                axes[0].set_ylabel("Value")
                axes[0].tick_params(axis="x", rotation=30)

            if volume_df.empty:
                axes[1].text(0.5, 0.5, "No volume values", ha="center", va="center")
                axes[1].set_axis_off()
            else:
                axes[1].scatter(
                    volume_df["cone_id"], volume_df["volume_km3"], alpha=0.75, color="#4C78A8"
                )
                axes[1].set_title("Volume by cone (scatter, km^3)")
                axes[1].set_xlabel("Cone ID")
                axes[1].set_ylabel("Volume (km^3)")

                if len(volume_df) >= 2:
                    trend_coeff = np.polyfit(volume_df["cone_id"], volume_df["volume_km3"], deg=1)
                    trend = np.poly1d(trend_coeff)
                    x_sorted = np.sort(volume_df["cone_id"].to_numpy())
                    axes[1].plot(
                        x_sorted, trend(x_sorted), color="#E45756", linewidth=2, label="Trend line"
                    )
                    axes[1].legend(loc="best")

                top_n = volume_df.nlargest(min(3, len(volume_df)), "volume_km3")
                for _, row in top_n.iterrows():
                    axes[1].annotate(
                        f"{int(row['cone_id'])}",
                        (row["cone_id"], row["volume_km3"]),
                        textcoords="offset points",
                        xytext=(4, 4),
                        fontsize=8,
                    )

            figure.tight_layout()
            figure.savefig(graphs_path, dpi=200)
            source_name = (
                "fix_cone_summary.csv" if use_manual_fix_check.isChecked() else "cone_summary.csv"
            )
            source_label.setText(f"Source: {output_dir / source_name} | Saved graph: {graphs_path}")
            canvas.draw_idle()

        use_manual_fix_check.toggled.connect(lambda _checked: refresh_graphs())
        refresh_graphs()

        dialog.exec()
        plt.close(figure)

    def _show_cross_section_metrics_correlation(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Cross-section metrics correlation")
        dialog.resize(1360, 560)

        layout = QVBoxLayout(dialog)
        top_row = QHBoxLayout()
        use_manual_fix_check = QCheckBox("Use manual fix")
        use_manual_fix_check.setChecked(self.use_manual_fix_check.isChecked())
        source_label = QLabel("")
        top_row.addWidget(use_manual_fix_check)
        top_row.addWidget(source_label)
        top_row.addStretch(1)
        layout.addLayout(top_row)

        figure, axes = plt.subplots(
            1, 2, figsize=(13.2, 5.0), gridspec_kw={"width_ratios": [1.0, 1.25]}
        )
        canvas = FigureCanvas(figure)
        layout.addWidget(canvas)
        corr_colorbar = None
        slope_colorbar = None

        def refresh_plot() -> None:
            nonlocal corr_colorbar, slope_colorbar
            source_df = self._load_analyzer_metrics_csv(
                "cone_summary.csv",
                "Metrics correlation",
                use_manual_fix=use_manual_fix_check.isChecked(),
                show_error=False,
            )

            if corr_colorbar is not None:
                corr_colorbar.remove()
                corr_colorbar = None
            if slope_colorbar is not None:
                slope_colorbar.remove()
                slope_colorbar = None

            axes[0].clear()
            axes[1].clear()

            if source_df is None:
                source_df = pd.DataFrame()

            metrics_df = self._extract_cone_metric_plot_columns(source_df)
            numeric_columns = [
                column for column in metrics_df.columns if metrics_df[column].notna().any()
            ]
            metrics_df = metrics_df[numeric_columns] if numeric_columns else pd.DataFrame()
            slope_depth_df = pd.DataFrame(
                {
                    "cone_id": self._safe_numeric_series(source_df, "cone_id"),
                    "avg_slope_deg": self._safe_numeric_series(
                        metrics_df, "avg_slope_deg", source_df.index
                    ),
                    "D": self._safe_numeric_series(metrics_df, "D", source_df.index),
                    "Wcr": self._safe_numeric_series(metrics_df, "Wcr", source_df.index),
                    "H": self._safe_numeric_series(metrics_df, "H", source_df.index),
                }
            ).dropna(subset=["avg_slope_deg", "D", "Wcr", "H"])

            output_dir = Path(self.base_path_edit.text().strip()) / "output" / "analyzer"
            output_dir.mkdir(parents=True, exist_ok=True)
            graph_name = (
                "fix_cross_metrics_correlation.png"
                if use_manual_fix_check.isChecked()
                else "cross_metrics_correlation.png"
            )
            graph_path = output_dir / graph_name

            if slope_depth_df.empty:
                axes[0].text(
                    0.5, 0.5, "No numeric values for avg_slope_deg/depth", ha="center", va="center"
                )
                axes[0].set_axis_off()
            else:
                h_values = slope_depth_df["H"].to_numpy()
                h_min = float(np.min(h_values))
                h_max = float(np.max(h_values))
                if h_max > h_min:
                    point_sizes = 40.0 + 200.0 * (h_values - h_min) / (h_max - h_min)
                else:
                    point_sizes = np.full(len(h_values), 120.0)

                scatter = axes[0].scatter(
                    slope_depth_df["avg_slope_deg"],
                    slope_depth_df["D"],
                    c=slope_depth_df["Wcr"],
                    s=point_sizes,
                    cmap="viridis",
                    alpha=0.8,
                    edgecolors="k",
                    linewidths=0.3,
                )
                axes[0].set_title("avg_slope_deg vs depth (color=Wcr, size=H)")
                axes[0].set_xlabel("Average slope [deg]")
                axes[0].set_ylabel("Depth")
                axes[0].grid(True, alpha=0.25)
                slope_colorbar = figure.colorbar(scatter, ax=axes[0], fraction=0.046, pad=0.04)
                slope_colorbar.set_label("Wcr")

                if len(slope_depth_df) >= 2:
                    coeff = np.polyfit(slope_depth_df["avg_slope_deg"], slope_depth_df["D"], deg=1)
                    trend = np.poly1d(coeff)
                    x_sorted = np.sort(slope_depth_df["avg_slope_deg"].to_numpy())
                    axes[0].plot(
                        x_sorted, trend(x_sorted), color="#E45756", linewidth=2, label="Trend line"
                    )

                    corr_value = slope_depth_df[["avg_slope_deg", "D"]].corr().iloc[0, 1]
                    axes[0].legend(title=f"r = {corr_value:.2f}", loc="best")

                deepest = slope_depth_df.nlargest(min(3, len(slope_depth_df)), "D")
                for _, row in deepest.iterrows():
                    cone_id = int(row["cone_id"]) if pd.notna(row["cone_id"]) else "?"
                    axes[0].annotate(
                        str(cone_id),
                        (row["avg_slope_deg"], row["D"]),
                        textcoords="offset points",
                        xytext=(4, 4),
                        fontsize=8,
                    )

            if metrics_df.shape[1] < 2:
                axes[1].text(
                    0.5, 0.5, "Need at least two numeric metrics", ha="center", va="center"
                )
                axes[1].set_axis_off()
            else:
                corr = metrics_df.corr(numeric_only=True)
                image = axes[1].imshow(corr.values, vmin=-1.0, vmax=1.0, cmap="coolwarm")
                axes[1].set_xticks(range(len(corr.columns)))
                axes[1].set_xticklabels(corr.columns, rotation=35, ha="right")
                axes[1].set_yticks(range(len(corr.index)))
                axes[1].set_yticklabels(corr.index)
                axes[1].set_title("Metric correlation matrix")

                for i in range(len(corr.index)):
                    for j in range(len(corr.columns)):
                        axes[1].text(
                            j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center", fontsize=8
                        )

                corr_colorbar = figure.colorbar(image, ax=axes[1], fraction=0.046, pad=0.04)
                corr_colorbar.set_label("Pearson r")

            figure.tight_layout()
            figure.savefig(graph_path, dpi=200)
            source_name = (
                "fix_cone_summary.csv" if use_manual_fix_check.isChecked() else "cone_summary.csv"
            )
            source_label.setText(f"Source: {output_dir / source_name} | Saved graph: {graph_path}")
            canvas.draw_idle()

        use_manual_fix_check.toggled.connect(lambda _checked: refresh_plot())
        refresh_plot()

        dialog.exec()
        plt.close(figure)

    def _show_cross_section_wco_scatter(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Cross-section Wco/Wcr scatter")
        dialog.resize(1400, 560)

        layout = QVBoxLayout(dialog)
        top_row = QHBoxLayout()
        use_manual_fix_check = QCheckBox("Use manual fix")
        use_manual_fix_check.setChecked(self.use_manual_fix_check.isChecked())
        source_label = QLabel("")
        top_row.addWidget(use_manual_fix_check)
        top_row.addWidget(source_label)
        top_row.addStretch(1)
        layout.addLayout(top_row)

        figure, (ax1, ax2) = plt.subplots(1, 2, figsize=(13.6, 5.0))
        canvas = FigureCanvas(figure)
        layout.addWidget(canvas)
        scatter_colorbar1 = None
        scatter_colorbar2 = None

        def refresh_plot() -> None:
            nonlocal scatter_colorbar1, scatter_colorbar2
            source_df = self._load_analyzer_metrics_csv(
                "cone_summary.csv",
                "Wco scatter",
                use_manual_fix=use_manual_fix_check.isChecked(),
                show_error=False,
            )

            if scatter_colorbar1 is not None:
                scatter_colorbar1.remove()
                scatter_colorbar1 = None
            if scatter_colorbar2 is not None:
                scatter_colorbar2.remove()
                scatter_colorbar2 = None

            ax1.clear()
            ax2.clear()

            if source_df is None:
                source_df = pd.DataFrame()

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
                if use_manual_fix_check.isChecked()
                else "cross_wco_wcr_depth_scatter.png"
            )
            graph_path = output_dir / graph_name

            if scatter_df.empty:
                ax1.text(0.5, 0.5, "No data", ha="center", va="center")
                ax1.set_axis_off()
                ax2.text(0.5, 0.5, "No data", ha="center", va="center")
                ax2.set_axis_off()
            else:
                # Left plot: Wco vs Wcr colored by depth
                points1 = ax1.scatter(
                    scatter_df["Wco"],
                    scatter_df["Wcr"],
                    c=scatter_df["D"],
                    cmap="viridis",
                    alpha=0.8,
                    edgecolors="k",
                    linewidths=0.3,
                )
                ax1.set_title("Wco vs Wcr (colored by depth)")
                ax1.set_xlabel("Wco")
                ax1.set_ylabel("Wcr")
                scatter_colorbar1 = figure.colorbar(points1, ax=ax1, fraction=0.046, pad=0.04)
                scatter_colorbar1.set_label("Depth")

                if len(scatter_df) >= 2:
                    coeff = np.polyfit(scatter_df["Wco"], scatter_df["Wcr"], deg=1)
                    trend = np.poly1d(coeff)
                    x_sorted = np.sort(scatter_df["Wco"].to_numpy())
                    ax1.plot(x_sorted, trend(x_sorted), color="#E45756", linewidth=2, label="Trend")
                    ax1.legend(loc="best")

                deepest = scatter_df.nlargest(min(3, len(scatter_df)), "D")
                for _, row in deepest.iterrows():
                    cone_id = int(row["cone_id"]) if pd.notna(row["cone_id"]) else "?"
                    ax1.annotate(
                        str(cone_id),
                        (row["Wco"], row["Wcr"]),
                        textcoords="offset points",
                        xytext=(4, 4),
                        fontsize=8,
                    )

                # Right plot: Wcr vs H_WCO_ratio colored by depth
                points2 = ax2.scatter(
                    scatter_df["Wcr"],
                    scatter_df["H_WCO_ratio"],
                    c=scatter_df["D"],
                    cmap="viridis",
                    alpha=0.8,
                    edgecolors="k",
                    linewidths=0.3,
                )
                ax2.set_title("Wcr vs H/Wco ratio (colored by depth)")
                ax2.set_xlabel("Wcr")
                ax2.set_ylabel("H/Wco ratio")
                scatter_colorbar2 = figure.colorbar(points2, ax=ax2, fraction=0.046, pad=0.04)
                scatter_colorbar2.set_label("Depth")

                if len(scatter_df) >= 2:
                    coeff2 = np.polyfit(scatter_df["Wcr"], scatter_df["H_WCO_ratio"], deg=1)
                    trend2 = np.poly1d(coeff2)
                    x_sorted2 = np.sort(scatter_df["Wcr"].to_numpy())
                    ax2.plot(
                        x_sorted2, trend2(x_sorted2), color="#E45756", linewidth=2, label="Trend"
                    )
                    ax2.legend(loc="best")

            figure.tight_layout()
            figure.savefig(graph_path, dpi=200)
            source_name = (
                "fix_cone_summary.csv" if use_manual_fix_check.isChecked() else "cone_summary.csv"
            )
            source_label.setText(f"Source: {output_dir / source_name} | Saved: {graph_path}")
            canvas.draw_idle()

        use_manual_fix_check.toggled.connect(lambda _checked: refresh_plot())
        refresh_plot()

        dialog.exec()
        plt.close(figure)

    def _show_cross_section_scatters(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Cross-section Scatters & Distributions")
        dialog.resize(1200, 700)

        layout = QVBoxLayout(dialog)
        top_row = QHBoxLayout()
        use_manual_fix_check = QCheckBox("Use manual fix")
        use_manual_fix_check.setChecked(self.use_manual_fix_check.isChecked())
        source_label = QLabel("")
        top_row.addWidget(use_manual_fix_check)
        top_row.addWidget(source_label)
        top_row.addStretch(1)
        layout.addLayout(top_row)

        # Create tab widget
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # ===== TAB 1: 2D Histogram H vs Depth + Scatter =====
        tab1_widget = QWidget()
        tab1_layout = QVBoxLayout(tab1_widget)
        figure1, (ax1a, ax1b) = plt.subplots(1, 2, figsize=(11.6, 5.2))
        canvas1 = FigureCanvas(figure1)
        tab1_layout.addWidget(canvas1)
        tabs.addTab(tab1_widget, "H vs Depth & Data")

        hist_colorbar1 = None

        def refresh_tab1() -> None:
            nonlocal hist_colorbar1
            source_df = self._load_analyzer_metrics_csv(
                "cone_summary.csv",
                "Scatters - Tab1",
                use_manual_fix=use_manual_fix_check.isChecked(),
                show_error=False,
            )

            if hist_colorbar1 is not None:
                hist_colorbar1.remove()
                hist_colorbar1 = None

            ax1a.clear()
            ax1b.clear()

            if source_df is None:
                source_df = pd.DataFrame()

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
                # 2D Histogram (H vs Depth)
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
                im1 = ax1a.imshow(
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
                hist_colorbar1 = figure1.colorbar(im1, ax=ax1a)
                hist_colorbar1.set_label("Count")

                # Scatter H vs D with trend
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

            figure1.tight_layout()
            canvas1.draw_idle()

        # ===== Distribution Histograms =====
        tab2_widget = QWidget()
        tab2_layout = QVBoxLayout(tab2_widget)
        figure2, ((ax2a, ax2b), (ax2c, ax2d)) = plt.subplots(2, 2, figsize=(11.6, 6.0))
        canvas2 = FigureCanvas(figure2)
        tab2_layout.addWidget(canvas2)
        tabs.addTab(tab2_widget, "Distributions")

        def refresh_tab2() -> None:
            source_df = self._load_analyzer_metrics_csv(
                "cone_summary.csv",
                "Scatters - Tab2",
                use_manual_fix=use_manual_fix_check.isChecked(),
                show_error=False,
            )

            ax2a.clear()
            ax2b.clear()
            ax2c.clear()
            ax2d.clear()

            if source_df is None:
                source_df = pd.DataFrame()

            metrics_df = self._extract_cone_metric_plot_columns(source_df)

            h_vals = self._safe_numeric_series(metrics_df, "H", source_df.index).dropna()
            wco_vals = self._safe_numeric_series(metrics_df, "Wco", source_df.index).dropna()
            wcr_vals = self._safe_numeric_series(metrics_df, "Wcr", source_df.index).dropna()
            d_vals = self._safe_numeric_series(metrics_df, "D", source_df.index).dropna()

            if not h_vals.empty:
                ax2a.hist(h_vals, bins=15, color="steelblue", edgecolor="black", alpha=0.7)
                ax2a.set_title("Height (H) Distribution")
                ax2a.set_xlabel("Height")
                ax2a.set_ylabel("Frequency")
                ax2a.grid(True, alpha=0.3)
            else:
                ax2a.text(0.5, 0.5, "No H data", ha="center", va="center")
                ax2a.set_axis_off()

            if not wco_vals.empty:
                ax2b.hist(wco_vals, bins=15, color="coral", edgecolor="black", alpha=0.7)
                ax2b.set_title("Base Diameter (Wco) Distribution")
                ax2b.set_xlabel("Wco")
                ax2b.set_ylabel("Frequency")
                ax2b.grid(True, alpha=0.3)
            else:
                ax2b.text(0.5, 0.5, "No Wco data", ha="center", va="center")
                ax2b.set_axis_off()

            if not wcr_vals.empty:
                ax2c.hist(wcr_vals, bins=15, color="mediumseagreen", edgecolor="black", alpha=0.7)
                ax2c.set_title("Top Diameter (Wcr) Distribution")
                ax2c.set_xlabel("Wcr")
                ax2c.set_ylabel("Frequency")
                ax2c.grid(True, alpha=0.3)
            else:
                ax2c.text(0.5, 0.5, "No Wcr data", ha="center", va="center")
                ax2c.set_axis_off()

            if not d_vals.empty:
                ax2d.hist(d_vals, bins=15, color="mediumpurple", edgecolor="black", alpha=0.7)
                ax2d.set_title("Depth (D) Distribution")
                ax2d.set_xlabel("Depth")
                ax2d.set_ylabel("Frequency")
                ax2d.grid(True, alpha=0.3)
            else:
                ax2d.text(0.5, 0.5, "No D data", ha="center", va="center")
                ax2d.set_axis_off()

            figure2.tight_layout()
            canvas2.draw_idle()

        def refresh_all_tabs() -> None:
            refresh_tab1()
            refresh_tab2()

            output_dir = Path(self.base_path_edit.text().strip()) / "output" / "analyzer"
            output_dir.mkdir(parents=True, exist_ok=True)
            tab1_name = (
                "fix_cross_scatters_tab1.png"
                if use_manual_fix_check.isChecked()
                else "cross_scatters_tab1.png"
            )
            tab2_name = (
                "fix_cross_scatters_tab2.png"
                if use_manual_fix_check.isChecked()
                else "cross_scatters_tab2.png"
            )
            tab1_path = output_dir / tab1_name
            tab2_path = output_dir / tab2_name
            figure1.savefig(tab1_path, dpi=200)
            figure2.savefig(tab2_path, dpi=200)
            source_name = (
                "fix_cone_summary.csv" if use_manual_fix_check.isChecked() else "cone_summary.csv"
            )
            source_label.setText(
                f"Source: {output_dir / source_name} | Saved: {tab1_path.name}, {tab2_path.name}"
            )

        use_manual_fix_check.toggled.connect(lambda _checked: refresh_all_tabs())
        refresh_all_tabs()

        dialog.exec()
        plt.close(figure1)
        plt.close(figure2)

    def _load_cross_section_metrics(self) -> tuple[pd.DataFrame | None, Path]:
        output_dir = Path(self.cs_output_dir_edit.text().strip())
        metrics_path = output_dir / "cross_section_metrics.csv"
        if not metrics_path.exists():
            QMessageBox.information(
                self, "Cross-section", f"Metrics file not found:\n{metrics_path}"
            )
            return None, output_dir
        return pd.read_csv(metrics_path, sep=";"), output_dir

    def _clear_cross_section_filter(self) -> None:
        self.cs_preview_filter_edit.clear()
        self._refresh_cross_section_preview(reset_to_first=True)

    def _effective_cross_section_output_dir(self) -> Path:
        output_dir = Path(self.cs_output_dir_edit.text().strip())
        if self.cs_preview_use_manual_fix_check.isChecked():
            return output_dir / "manual_fix"
        return output_dir

    def _update_cross_section_preview_source_label(self, output_dir: Path) -> None:
        mode = "manual_fix" if self.cs_preview_use_manual_fix_check.isChecked() else "standard"
        self.cs_preview_source_label.setText(f"Source ({mode}): {output_dir}")

    def _sync_manual_fix_cross_section_previews(self) -> None:
        base_output_dir = Path(self.cs_output_dir_edit.text().strip())
        manual_output_dir = base_output_dir / "manual_fix"
        manual_output_dir.mkdir(parents=True, exist_ok=True)

        overrides_path = self._manual_fix_overrides_path()
        if not overrides_path.exists():
            return

        overrides_df = pd.read_csv(overrides_path, sep=";")
        if overrides_df.empty:
            return

        required_columns = {"cone_id", "axis_deg", "slot", "sample_idx"}
        if not required_columns.issubset(set(overrides_df.columns)):
            return

        work_df = overrides_df.copy()
        work_df["cone_id_norm"] = (
            work_df["cone_id"].astype(str).str.replace(r"\.0$", "", regex=True)
        )
        work_df["axis_deg_num"] = pd.to_numeric(work_df["axis_deg"], errors="coerce")
        work_df["sample_idx_num"] = pd.to_numeric(work_df["sample_idx"], errors="coerce")
        work_df = work_df.dropna(subset=["axis_deg_num", "sample_idx_num"])
        if work_df.empty:
            return

        generated = 0
        for (cone_id_norm, axis_deg), group in work_df.groupby(
            ["cone_id_norm", "axis_deg_num"], sort=False
        ):
            model = self._manual_fix_build_model(str(cone_id_norm), float(axis_deg))
            if model is None:
                continue

            combined_profile = model["combined_profile"]
            if combined_profile is None or combined_profile.empty:
                continue

            slot_indices = dict(model["slot_indices"])
            max_index = len(combined_profile) - 1

            for _, row in group.iterrows():
                slot_key = str(row.get("slot", ""))
                if slot_key not in slot_indices:
                    continue
                sample_idx = int(row["sample_idx_num"])
                sample_idx = max(0, min(sample_idx, max_index))
                slot_indices[slot_key] = sample_idx

            output_path = (
                manual_output_dir / f"cone{cone_id_norm}_axis{int(round(float(axis_deg)))}.png"
            )
            if self._render_manual_fix_cross_section_image(
                model, slot_indices, str(cone_id_norm), float(axis_deg), output_path
            ):
                generated += 1

        if generated > 0:
            self.cs_log_output.appendPlainText(
                "Manual Fix preview sync: generated/updated "
                f"{generated} image(s) in {manual_output_dir}"
            )

    def _render_manual_fix_cross_section_image(
        self,
        model: dict,
        slot_indices: dict[str, int],
        cone_id: str,
        axis_deg: float,
        output_path: Path,
    ) -> bool:
        combined_profile = model.get("combined_profile")
        if combined_profile is None or combined_profile.empty:
            return False

        profile_a_plot = model.get("profile_a_plot")
        profile_b_plot = model.get("profile_b_plot")

        fig, ax = plt.subplots(figsize=(12, 5))
        if profile_a_plot is not None:
            x_a, z_a = profile_a_plot
            ax.plot(x_a, z_a, "k-", linewidth=1.5, label="Transect A")
        if profile_b_plot is not None:
            x_b, z_b = profile_b_plot
            ax.plot(x_b, z_b, "k--", linewidth=1.5, label="Transect B")

        points_values: dict[str, tuple[float, float]] = {}
        for slot_key, slot_label, color in MANUAL_FIX_SLOTS:
            idx = int(slot_indices.get(slot_key, 0))
            idx = max(0, min(idx, len(combined_profile) - 1))
            row = combined_profile.iloc[idx]
            x_val = float(row["x_plot"])
            z_val = float(row["elevation"])
            points_values[slot_key] = (x_val, z_val)
            ax.scatter(
                x_val,
                z_val,
                s=80,
                color=color,
                edgecolors="k",
                zorder=5,
                label=slot_label,
            )

        wco = wcr = h_left = h_right = d_left = d_right = None
        d_wcr_left = d_wcr_right = None
        if "left_near_bottom" in points_values and "right_near_bottom" in points_values:
            wco = points_values["right_near_bottom"][0] - points_values["left_near_bottom"][0]
        if "left_top" in points_values and "right_top" in points_values:
            wcr = points_values["right_top"][0] - points_values["left_top"][0]
        if "left_top" in points_values and "left_near_bottom" in points_values:
            h_left = points_values["left_top"][1] - points_values["left_near_bottom"][1]
        if "right_top" in points_values and "right_near_bottom" in points_values:
            h_right = points_values["right_top"][1] - points_values["right_near_bottom"][1]
        if "left_top" in points_values and "center" in points_values:
            d_left = points_values["left_top"][1] - points_values["center"][1]
        if "right_top" in points_values and "center" in points_values:
            d_right = points_values["right_top"][1] - points_values["center"][1]

        if wcr is not None and wcr > 0:
            if d_left is not None:
                d_wcr_left = d_left / wcr
            if d_right is not None:
                d_wcr_right = d_right / wcr

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

        if metrics_lines:
            ax.text(
                0.02,
                0.98,
                "\n".join(metrics_lines),
                transform=ax.transAxes,
                ha="left",
                va="top",
                fontsize=9,
                bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.8},
            )

        ax.set_xlabel("Distance (m)")
        ax.set_ylabel("Elevation (m)")
        ax.set_title(f"Cross section - cone {cone_id} (axis ~ {axis_deg:.0f} deg) [manual fix]")
        ax.grid(True, alpha=0.3)

        handles, labels = ax.get_legend_handles_labels()
        unique = {}
        for handle, label in zip(handles, labels):
            if label not in unique:
                unique[label] = handle
        ax.legend(unique.values(), unique.keys(), loc="upper right")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.tight_layout()
        fig.savefig(output_path, dpi=self.cs_dpi_spin.value())
        plt.close(fig)
        return True

    def _refresh_cross_section_preview(self, reset_to_first: bool) -> None:
        if self.cs_preview_use_manual_fix_check.isChecked():
            self._sync_manual_fix_cross_section_previews()

        current_key = None
        if self.cross_section_images and 0 <= self.cross_section_image_index < len(
            self.cross_section_images
        ):
            current_key = self._extract_cone_axis_from_cross_section_name(
                self.cross_section_images[self.cross_section_image_index].name
            )

        output_dir = self._effective_cross_section_output_dir()
        self._update_cross_section_preview_source_label(output_dir)
        filter_value = self.cs_preview_filter_edit.text().strip()
        if not output_dir.exists():
            self.cross_section_images = []
            self.cross_section_image_index = -1
            self.cs_preview_label.setText("No plots yet.")
            self.cs_preview_file_label.setText("0/0")
            self.cs_prev_button.setEnabled(False)
            self.cs_next_button.setEnabled(False)
            return

        self.cross_section_images = sorted(output_dir.glob("*.png"))
        if not self.cross_section_images:
            self.cross_section_image_index = -1
            self.cs_preview_label.setText("No PNG files in output directory.")
            self.cs_preview_file_label.setText("0/0")
            self.cs_prev_button.setEnabled(False)
            self.cs_next_button.setEnabled(False)
            return

        if reset_to_first and filter_value:
            jump_index = next(
                (
                    idx
                    for idx, image_path in enumerate(self.cross_section_images)
                    if f"cone{filter_value}_" in image_path.name
                ),
                -1,
            )
            if jump_index >= 0:
                self.cross_section_image_index = jump_index
            else:
                self.cross_section_image_index = 0
                self.statusBar().showMessage(
                    f"Cone ID {filter_value} not found in current preview list.",
                    4000,
                )
        elif reset_to_first:
            self.cross_section_image_index = 0
        elif current_key is not None:
            match_index = next(
                (
                    idx
                    for idx, image_path in enumerate(self.cross_section_images)
                    if self._extract_cone_axis_from_cross_section_name(image_path.name)
                    == current_key
                ),
                -1,
            )
            if match_index >= 0:
                self.cross_section_image_index = match_index
            else:
                self.cross_section_image_index = min(
                    max(self.cross_section_image_index, 0),
                    len(self.cross_section_images) - 1,
                )
        else:
            self.cross_section_image_index = min(
                max(self.cross_section_image_index, 0),
                len(self.cross_section_images) - 1,
            )
        self._show_cross_section_image()

    def _show_cross_section_image(self) -> None:
        if not self.cross_section_images or self.cross_section_image_index < 0:
            self.cs_preview_label.setText("No plots yet.")
            self.cs_preview_file_label.setText("0/0")
            self.cs_prev_button.setEnabled(False)
            self.cs_next_button.setEnabled(False)
            return

        image_path = self.cross_section_images[self.cross_section_image_index]
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            self.cs_preview_label.setText(f"Could not load image: {image_path.name}")
            return

        self.cross_section_current_pixmap = pixmap
        scaled = pixmap.scaled(
            self.cs_preview_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.cs_preview_label.setPixmap(scaled)
        self.cs_preview_file_label.setText(
            f"{self.cross_section_image_index + 1}/{len(self.cross_section_images)}: "
            f"{image_path.name}"
        )
        self.cs_prev_button.setEnabled(self.cross_section_image_index > 0)
        self.cs_next_button.setEnabled(
            self.cross_section_image_index < len(self.cross_section_images) - 1
        )

    def _show_previous_cross_section_image(self) -> None:
        if self.cross_section_image_index <= 0:
            return
        self.cross_section_image_index -= 1
        self._show_cross_section_image()

    def _show_next_cross_section_image(self) -> None:
        if self.cross_section_image_index >= len(self.cross_section_images) - 1:
            return
        self.cross_section_image_index += 1
        self._show_cross_section_image()

    def _extract_cone_axis_from_cross_section_name(self, filename: str) -> tuple[str, float] | None:
        match = re.match(r"cone(\d+)_axis(\d+)\.png$", filename)
        if not match:
            return None
        return match.group(1), float(match.group(2))
