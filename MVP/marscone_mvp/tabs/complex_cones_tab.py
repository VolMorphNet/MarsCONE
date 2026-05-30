"""Mixin for the ComplexConesMixin section of MainWindow."""
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




class ComplexConesMixin:
    """Mixin — mixed into MainWindow via multiple inheritance."""

    def _build_complex_cones_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        config_group = QGroupBox("Complex cone definitions")
        config_layout = QGridLayout(config_group)

        self.complex_id_edit = QLineEdit()
        self.complex_member_ids_edit = QLineEdit()
        self.complex_member_ids_edit.setPlaceholderText("e.g. 33, 39")
        self.complex_topology_combo = QComboBox()
        self.complex_topology_combo.addItems(["complex"])
        self.complex_notes_edit = QLineEdit()
        self.complex_use_manual_fix_check = QCheckBox("Use manual fix metrics")
        self.complex_use_manual_fix_check.setChecked(self.use_manual_fix_check.isChecked())
        self.complex_active_check = QCheckBox("Active")
        self.complex_active_check.setChecked(True)

        config_layout.addWidget(QLabel("Complex ID"), 0, 0)
        config_layout.addWidget(self.complex_id_edit, 0, 1)
        config_layout.addWidget(QLabel("Member cone IDs"), 0, 2)
        config_layout.addWidget(self.complex_member_ids_edit, 0, 3)
        config_layout.addWidget(QLabel("Topology type"), 1, 0)
        config_layout.addWidget(self.complex_topology_combo, 1, 1)
        config_layout.addWidget(QLabel("Notes"), 1, 2)
        config_layout.addWidget(self.complex_notes_edit, 1, 3)
        config_layout.addWidget(self.complex_use_manual_fix_check, 2, 0)
        config_layout.addWidget(self.complex_active_check, 2, 1)

        actions_row = QHBoxLayout()
        self.complex_add_update_button = QPushButton("Add / Update")
        self.complex_remove_button = QPushButton("Remove selected")
        self.complex_load_button = QPushButton("Load saved")
        self.complex_save_button = QPushButton("Save definitions")
        self.complex_compute_button = QPushButton("Compute outputs")
        self.complex_open_output_button = QPushButton("Open output folder")
        self.complex_view_in_dem_button = QPushButton("View in DEM")
        actions_row.addWidget(self.complex_add_update_button)
        actions_row.addWidget(self.complex_remove_button)
        actions_row.addWidget(self.complex_load_button)
        actions_row.addWidget(self.complex_save_button)
        actions_row.addWidget(self.complex_compute_button)
        actions_row.addWidget(self.complex_open_output_button)
        actions_row.addWidget(self.complex_view_in_dem_button)
        actions_row.addStretch(1)

        self.complex_source_label = QLabel("Sources: -")
        self.complex_source_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.complex_pairs_table = QTableView()
        self.complex_pairs_table.setModel(self.complex_pairs_model)
        self.complex_pairs_table.setSortingEnabled(False)

        results_tabs = QTabWidget()
        self.complex_summary_table = QTableView()
        self.complex_summary_table.setModel(self.complex_summary_model)
        self.complex_summary_table.setSortingEnabled(True)
        results_tabs.addTab(self.complex_summary_table, "Complex Summary")

        self.complex_members_table = QTableView()
        self.complex_members_table.setModel(self.complex_members_model)
        self.complex_members_table.setSortingEnabled(True)
        results_tabs.addTab(self.complex_members_table, "Members")

        self.complex_topology_table = QTableView()
        self.complex_topology_table.setModel(self.complex_topology_model)
        self.complex_topology_table.setSortingEnabled(True)
        results_tabs.addTab(self.complex_topology_table, "Topology")

        self.complex_topology_stats_table = QTableView()
        self.complex_topology_stats_table.setModel(self.complex_topology_stats_model)
        self.complex_topology_stats_table.setSortingEnabled(True)
        results_tabs.addTab(self.complex_topology_stats_table, "Topology Stats")

        self.complex_log_output = QPlainTextEdit()
        self.complex_log_output.setReadOnly(True)
        self.complex_log_output.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.complex_log_output.setMaximumHeight(140)

        splitter = QSplitter(Qt.Vertical)
        definitions_container = QWidget()
        definitions_layout = QVBoxLayout(definitions_container)
        definitions_layout.addWidget(QLabel("Complex pairs"))
        definitions_layout.addWidget(self.complex_pairs_table)
        splitter.addWidget(definitions_container)
        splitter.addWidget(results_tabs)
        splitter.setSizes([320, 420])

        layout.addWidget(config_group)
        layout.addLayout(actions_row)
        layout.addWidget(self.complex_source_label)
        layout.addWidget(splitter, stretch=1)
        layout.addWidget(self.complex_log_output)

        self.complex_add_update_button.clicked.connect(self._complex_add_or_update_definition)
        self.complex_remove_button.clicked.connect(self._complex_remove_selected_definition)
        self.complex_load_button.clicked.connect(
            lambda: self._complex_load_saved_definitions(show_message=True)
        )
        self.complex_save_button.clicked.connect(self._complex_save_definitions)
        self.complex_compute_button.clicked.connect(
            lambda: self._complex_recompute_outputs(show_message=True)
        )
        self.complex_open_output_button.clicked.connect(self._complex_open_output_dir)
        self.complex_view_in_dem_button.clicked.connect(self._complex_view_in_dem)
        self.complex_open_output_button.clicked.connect(self._complex_open_output_dir)
        self.complex_use_manual_fix_check.toggled.connect(
            lambda _checked: self._complex_recompute_outputs(show_message=False)
        )
        self.complex_pairs_table.selectionModel().selectionChanged.connect(
            lambda _selected, _deselected: self._complex_load_selected_definition_into_form()
        )

        return page

    def _complex_base_path(self) -> Path:
        return Path(self.base_path_edit.text().strip())

    def _complex_dem_output_dir(self) -> Path:
        output_dir = self._complex_base_path() / "output" / "mvp_complex" / "dem"
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _complex_figure_output_dir(self) -> Path:
        output_dir = self._complex_base_path() / "output" / "figures" / "complex_cones"
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    @staticmethod
    def _sanitize_complex_id_for_filename(complex_id: str) -> str:
        safe = re.sub(r"[^0-9A-Za-z_-]+", "_", str(complex_id).strip())
        return safe or "unknown"

    def _save_complex_dem_file(
        self,
        complex_id: str,
        source_paths: list[Path],
    ) -> Path:
        output_dir = self._complex_dem_output_dir()
        safe_id = self._sanitize_complex_id_for_filename(complex_id)
        output_path = output_dir / f"complex_{safe_id}_dem.tif"

        valid_source_paths: list[Path] = []
        for path in source_paths:
            if path.exists() and path not in valid_source_paths:
                valid_source_paths.append(path)
        if not valid_source_paths:
            raise FileNotFoundError("No source DEM files found for complex merge.")

        source_signature = "|".join(str(path.resolve()) for path in valid_source_paths)

        if output_path.exists():
            out_mtime = output_path.stat().st_mtime
            output_matches_sources = False
            try:
                with rasterio.open(output_path) as existing_output:
                    output_matches_sources = (
                        existing_output.tags().get("complex_dem_sources")
                        == source_signature
                    )
            except Exception:  # pylint: disable=broad-exception-caught
                output_matches_sources = False
            source_is_newer = any(
                path.stat().st_mtime > out_mtime for path in valid_source_paths
            )
            if output_matches_sources and not source_is_newer:
                return output_path

        if len(valid_source_paths) == 1:
            with rasterio.open(valid_source_paths[0]) as src:
                data = src.read()
                profile = src.profile.copy()
                profile.update(compress="lzw")
                with rasterio.open(output_path, "w", **profile) as dst:
                    dst.write(data)
                    dst.update_tags(complex_dem_sources=source_signature)
            return output_path

        datasets = [rasterio.open(path) for path in valid_source_paths]
        try:
            mosaic, transform = rio_merge(datasets)
            profile = datasets[0].profile.copy()
            profile.update(
                driver="GTiff",
                height=mosaic.shape[1],
                width=mosaic.shape[2],
                transform=transform,
                count=mosaic.shape[0],
                compress="lzw",
            )
            with rasterio.open(output_path, "w", **profile) as dst:
                dst.write(mosaic)
                dst.update_tags(complex_dem_sources=source_signature)
        finally:
            for ds in datasets:
                ds.close()

        return output_path

    def _resolve_complex_member_dem_paths(self, member_ids: list[str]) -> list[Path]:
        dem_dir = Path(self.dem_overlay_dem_dir_edit.text().strip())
        if not dem_dir.exists():
            return []

        dem_paths: list[Path] = []
        for member_id in member_ids:
            normalized_member_id = self._normalize_cone_id_for_match(member_id)
            for pattern in [
                f"cone_{normalized_member_id}_dem.tif",
                f"cone_{normalized_member_id}_dem.tiff",
                f"cone_{normalized_member_id}_dem.TIF",
                f"cone_{normalized_member_id}_dem.TIFF",
            ]:
                found = list(dem_dir.glob(pattern))
                if found:
                    dem_paths.append(found[0])
                    break
        return dem_paths

    def _complex_append_log(self, text: str) -> None:
        self.complex_log_output.appendPlainText(text)
        self.complex_log_output.verticalScrollBar().setValue(
            self.complex_log_output.verticalScrollBar().maximum()
        )

    def _complex_update_source_label(self) -> None:
        base_path = self._complex_base_path()
        cone_name = (
            "fix_cone_summary.csv"
            if self.complex_use_manual_fix_check.isChecked()
            else "cone_summary.csv"
        )
        self.complex_source_label.setText(
            "Sources: "
            f"{base_path / 'output' / 'analyzer' / cone_name} | "
            f"{base_path / 'output' / 'finder' / 'finder_method.csv'} | "
            f"Definitions: {complex_pairs_path(base_path)}"
        )

    def _complex_load_saved_definitions(self, show_message: bool) -> None:
        self.complex_pairs_df = load_complex_pairs(self._complex_base_path())
        self.complex_pairs_model.set_dataframe(self.complex_pairs_df)
        self.complex_pairs_table.resizeColumnsToContents()
        self._complex_update_source_label()
        if show_message:
            self.statusBar().showMessage("Complex cone definitions loaded.", 4000)

    def _complex_save_definitions(self) -> None:
        path = save_complex_pairs(self._complex_base_path(), self.complex_pairs_df)
        self._complex_update_source_label()
        self._complex_append_log(f"Saved complex definitions: {path}")
        self.statusBar().showMessage("Complex cone definitions saved.", 4000)

    def _complex_add_or_update_definition(self) -> None:
        complex_id = self.complex_id_edit.text().strip()
        member_ids = self.complex_member_ids_edit.text().strip()
        topology_type = self.complex_topology_combo.currentText().strip().lower()
        notes = self.complex_notes_edit.text().strip()
        active = self.complex_active_check.isChecked()

        if not complex_id:
            QMessageBox.information(self, "Complex Cones", "Provide a Complex ID.")
            return
        if not member_ids:
            QMessageBox.information(self, "Complex Cones", "Provide at least one member cone ID.")
            return

        work_df = ensure_pair_columns(self.complex_pairs_df)
        new_row = {
            "complex_id": complex_id,
            "member_ids": member_ids,
            "topology_type": topology_type,
            "notes": notes,
            "active": active,
        }
        existing_mask = work_df["complex_id"].astype(str) == complex_id
        if existing_mask.any():
            for column, value in new_row.items():
                work_df.loc[existing_mask, column] = value
            self._complex_append_log(f"Updated complex definition: {complex_id}")
        else:
            work_df = pd.concat([work_df, pd.DataFrame([new_row])], ignore_index=True)
            self._complex_append_log(f"Added complex definition: {complex_id}")

        self.complex_pairs_df = ensure_pair_columns(work_df)
        self.complex_pairs_model.set_dataframe(self.complex_pairs_df)
        self.complex_pairs_table.resizeColumnsToContents()
        self._complex_save_definitions()
        self._complex_recompute_outputs(show_message=False)

    def _complex_remove_selected_definition(self) -> None:
        selection = self.complex_pairs_table.selectionModel().selectedRows()
        if not selection:
            QMessageBox.information(self, "Complex Cones", "Select a definition row to remove.")
            return

        row_idx = selection[0].row()
        if row_idx < 0 or row_idx >= len(self.complex_pairs_df.index):
            return

        removed_id = str(self.complex_pairs_df.iloc[row_idx]["complex_id"])
        self.complex_pairs_df = self.complex_pairs_df.drop(index=row_idx).reset_index(drop=True)
        self.complex_pairs_model.set_dataframe(self.complex_pairs_df)
        self.complex_pairs_table.resizeColumnsToContents()
        self._complex_save_definitions()
        self._complex_recompute_outputs(show_message=False)
        self._complex_append_log(f"Removed complex definition: {removed_id}")

    def _complex_load_selected_definition_into_form(self) -> None:
        selection = self.complex_pairs_table.selectionModel().selectedRows()
        if not selection:
            return

        row_idx = selection[0].row()
        if row_idx < 0 or row_idx >= len(self.complex_pairs_df.index):
            return

        row = self.complex_pairs_df.iloc[row_idx]
        self.complex_id_edit.setText(str(row.get("complex_id", "")))
        self.complex_member_ids_edit.setText(str(row.get("member_ids", "")))
        self.complex_topology_combo.setCurrentText(str(row.get("topology_type", "complex")))
        self.complex_notes_edit.setText(str(row.get("notes", "")))
        self.complex_active_check.setChecked(bool(row.get("active", True)))

    def _complex_recompute_outputs(self, show_message: bool) -> None:
        self._complex_update_source_label()
        try:
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                outputs = build_complex_outputs(
                    self._complex_base_path(),
                    self.complex_pairs_df,
                    breach_df=self.complex_breach_singles_df,
                    use_manual_fix=self.complex_use_manual_fix_check.isChecked(),
                )
                saved_paths = save_complex_outputs(self._complex_base_path(), outputs)
            for w in caught_warnings:
                self._complex_append_log(f"⚠ {w.category.__name__}: {w.message}")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            self._complex_append_log(f"Complex output computation failed: {exc}")
            if show_message:
                QMessageBox.warning(
                    self, "Complex Cones", f"Complex output computation failed:\n{exc}"
                )
            return

        self.complex_summary_model.set_dataframe(outputs.get("summary", pd.DataFrame()))
        self.complex_members_model.set_dataframe(outputs.get("members", pd.DataFrame()))
        self.complex_topology_model.set_dataframe(outputs.get("topology", pd.DataFrame()))
        self.complex_topology_stats_model.set_dataframe(
            outputs.get("topology_stats", pd.DataFrame())
        )
        self.complex_breach_singles_model.set_dataframe(
            outputs.get("breached_singles", pd.DataFrame())
        )

        self.complex_summary_table.resizeColumnsToContents()
        self.complex_members_table.resizeColumnsToContents()
        self.complex_topology_table.resizeColumnsToContents()
        self.complex_topology_stats_table.resizeColumnsToContents()
        self.complex_breach_singles_table.resizeColumnsToContents()

        summary_path = saved_paths.get("summary")
        if summary_path is not None:
            self._complex_append_log(f"Computed complex outputs in {summary_path.parent}")
        if show_message:
            self.statusBar().showMessage("Complex cone outputs updated.", 4000)

    def _complex_open_output_dir(self) -> None:
        output_dir = complex_output_dir(self._complex_base_path())
        output_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_dir)))

    def _breach_load_saved_singles(self, show_message: bool) -> None:
        self.complex_breach_singles_df = load_breach_singles(self._complex_base_path())
        self.complex_breach_singles_model.set_dataframe(self.complex_breach_singles_df)
        self.complex_breach_singles_table.resizeColumnsToContents()
        self._sync_dem_overlay_topology_controls()
        if show_message:
            self.statusBar().showMessage("Single-cone overrides loaded.", 4000)

    def _breach_save_singles(self) -> None:
        path = save_breach_singles(self._complex_base_path(), self.complex_breach_singles_df)
        self._complex_append_log(f"Saved single-cone overrides: {path}")
        self.statusBar().showMessage("Single-cone overrides saved.", 4000)
        self._complex_recompute_outputs(show_message=False)

    def _complex_view_in_dem(self) -> None:
        selection = self.complex_pairs_table.selectionModel().selectedRows()
        if not selection:
            QMessageBox.information(self, "Complex Cones", "Select a complex pair to visualize.")
            return

        row_idx = selection[0].row()
        if row_idx < 0 or row_idx >= len(self.complex_pairs_df.index):
            return

        row = self.complex_pairs_df.iloc[row_idx]
        complex_id = str(row.get("complex_id", ""))
        member_ids_str = str(row.get("member_ids", ""))
        member_ids = parse_member_ids(member_ids_str)

        if not member_ids or len(member_ids) < 2:
            QMessageBox.information(
                self, "Complex Cones", "Complex pair must have at least 2 member cones."
            )
            return

        first_id = str(member_ids[0])
        dem_paths = self._resolve_complex_member_dem_paths(member_ids)
        if not dem_paths:
            QMessageBox.warning(
                self,
                "Complex Cones",
                f"No cropped DEM files found for complex members: {', '.join(member_ids)}",
            )
            return

        first_dem_path = dem_paths[0]

        try:
            dem_path = self._save_complex_dem_file(complex_id, dem_paths)
            self._complex_append_log(
                f"Saved complex DEM from {len(dem_paths)} source file(s): {dem_path}"
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            dem_path = first_dem_path
            self._complex_append_log(
                f"Complex DEM save failed ({exc}). Falling back to member DEM: {first_dem_path}"
            )

        try:
            finder_points_dict = get_complex_finder_points(
                self._complex_base_path(),
                member_ids,
                use_manual_fix=self.complex_use_manual_fix_check.isChecked(),
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            QMessageBox.warning(self, "Complex Cones", f"Failed to load finder points:\n{exc}")
            return

        transects_gdf = gpd.GeoDataFrame()
        gpkg_path = Path(self.dem_overlay_gpkg_edit.text().strip())
        if gpkg_path.exists():
            try:
                transects_gdf = gpd.read_file(gpkg_path, layer="transects")
                if "cone_id" in transects_gdf.columns:
                    transects_gdf = transects_gdf.copy()
                    transects_gdf["cone_id_norm"] = (
                        transects_gdf["cone_id"].astype(str).str.replace(r"\.0$", "", regex=True)
                    )
                    transects_gdf = transects_gdf[transects_gdf["cone_id_norm"] == first_id]
            except Exception as exc:  # pylint: disable=broad-exception-caught
                QMessageBox.warning(self, "Complex Cones", f"Failed to load transects:\n{exc}")

        hybrid_centers_dict: dict[str, tuple[float, float] | None] = {}
        for idx, member_id in enumerate(member_ids):
            hybrid_centers_dict[str(idx)] = None

        try:
            cone_summary_file = (
                "fix_cone_summary.csv"
                if self.complex_use_manual_fix_check.isChecked()
                else "cone_summary.csv"
            )
            cone_summary_path = (
                self._complex_base_path() / "output" / "analyzer" / cone_summary_file
            )

            if cone_summary_path.exists():
                cone_summary = pd.read_csv(cone_summary_path, sep=";")
                if (
                    "cone_id" in cone_summary.columns
                    and "center_x" in cone_summary.columns
                    and "center_y" in cone_summary.columns
                ):
                    cone_summary["cone_id_norm"] = (
                        cone_summary["cone_id"].astype(str).str.replace(r"\.0$", "", regex=True)
                    )

                    for idx, member_id in enumerate(member_ids):
                        member_row = cone_summary[cone_summary["cone_id_norm"] == member_id]
                        if not member_row.empty:
                            center_x = member_row.iloc[0]["center_x"]
                            center_y = member_row.iloc[0]["center_y"]
                            if pd.notna(center_x) and pd.notna(center_y):
                                hybrid_centers_dict[str(idx)] = (float(center_x), float(center_y))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            pass  # Silently ignore if centers not available

        mode_tag = "manual_fix" if self.complex_use_manual_fix_check.isChecked() else "standard"
        safe_complex_id = self._sanitize_complex_id_for_filename(complex_id)
        preview_png_path = self._complex_figure_output_dir() / (
            f"complex_{safe_complex_id}_dem_overlay_{mode_tag}.png"
        )
        preview_dependencies = [dem_path]
        complex_summary_path = (
            self._complex_base_path() / "output" / "mvp_complex" / "complex_summary.csv"
        )
        if complex_summary_path.exists():
            preview_dependencies.append(complex_summary_path)
        self._complex_append_log(f"Complex DEM preview PNG target: {preview_png_path}")

        dialog = ComplexConeViewDialog(
            complex_id=complex_id,
            member_ids=member_ids,
            dem_path=dem_path,
            finder_points_dict=finder_points_dict,
            transects_gdf=transects_gdf,
            hybrid_centers_dict=hybrid_centers_dict,
            azimuth_deg=float(self.dem_overlay_azimuth_spin.value()),
            altitude_deg=float(self.dem_overlay_altitude_spin.value()),
            use_manual_fix=self.complex_use_manual_fix_check.isChecked(),
            preview_png_path=preview_png_path,
            preview_dependencies=preview_dependencies,
        )
        dialog.exec()



class ComplexConeViewDialog(QDialog):
    """Preview dialog for inspecting complex cone geometry and DEM context."""

    def __init__(
        self,
        complex_id: str,
        member_ids: list[str],
        dem_path: Path,
        finder_points_dict: dict[str, pd.DataFrame],
        transects_gdf: gpd.GeoDataFrame,
        hybrid_centers_dict: dict[str, tuple[float, float] | None],
        azimuth_deg: float,
        altitude_deg: float,
        use_manual_fix: bool,
        preview_png_path: Path | None = None,
        preview_dependencies: list[Path] | None = None,
    ) -> None:
        super().__init__()
        self.complex_id = complex_id
        self.member_ids = member_ids
        self.dem_path = dem_path
        self.finder_points_dict = finder_points_dict
        self.transects_gdf = transects_gdf
        self.hybrid_centers_dict = hybrid_centers_dict
        self.azimuth_deg = azimuth_deg
        self.altitude_deg = altitude_deg
        self.use_manual_fix = use_manual_fix
        self.preview_png_path = preview_png_path
        self.preview_dependencies = preview_dependencies or []
        self.show_convex_hull = False

        member_ids_str = ", ".join(member_ids)
        self.setWindowTitle(f"Complex {complex_id} - Members [{member_ids_str}]")
        self.resize(1050, 900)

        layout = QVBoxLayout(self)

        # Control panel with toggle
        control_layout = QHBoxLayout()
        self.hull_checkbox = QCheckBox("Show Convex Hull")
        self.hull_checkbox.setChecked(False)
        self.hull_checkbox.stateChanged.connect(self._on_hull_toggled)
        control_layout.addWidget(self.hull_checkbox)
        control_layout.addStretch()
        layout.addLayout(control_layout)

        # Canvas for single DEM with both members overlaid
        self.figure = plt.Figure(figsize=(9.2, 8.5), dpi=110)
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

        self._plot_complex_on_dem()

    def _on_hull_toggled(self, state: int) -> None:
        """Handle convex hull checkbox state change."""
        self.show_convex_hull = state == Qt.CheckState.Checked.value
        self._plot_complex_on_dem()

    @staticmethod
    def _compute_hillshade_array(
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

    @staticmethod
    def _split_points(
        points_df: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        if points_df.empty or "type" not in points_df.columns:
            empty = points_df.iloc[0:0].copy()
            return empty, empty, empty, empty

        point_types = points_df["type"].astype(str)
        top_points = points_df[point_types.str.contains("_top", na=False)].copy()
        center_points = points_df[point_types == "C"].copy()
        bottom_points = points_df[point_types.str.contains("_bottom", na=False)].copy()

        near_bottom = bottom_points.iloc[0:0].copy()
        far_bottom = bottom_points.iloc[0:0].copy()
        if not bottom_points.empty:
            cx = pd.to_numeric(center_points.get("x_geo"), errors="coerce").mean()
            cy = pd.to_numeric(center_points.get("y_geo"), errors="coerce").mean()
            if pd.notna(cx) and pd.notna(cy):
                bx = pd.to_numeric(bottom_points.get("x_geo"), errors="coerce")
                by = pd.to_numeric(bottom_points.get("y_geo"), errors="coerce")
                dist = np.sqrt((bx - cx) ** 2 + (by - cy) ** 2)
                sorted_bottom = bottom_points.copy()
                sorted_bottom["_dist"] = dist

                def _axis_from_transect_id(value: object) -> int | None:
                    if not isinstance(value, str):
                        return None
                    try:
                        angle = float(value.split("_")[1].replace("deg", ""))
                        return int(round(angle)) % 180
                    except (ValueError, IndexError):
                        return None

                axis_key = sorted_bottom["transect_id"].astype(str).apply(_axis_from_transect_id)
                axis_key = axis_key.where(
                    axis_key.notna(), sorted_bottom["transect_id"].astype(str)
                )

                dx = bx - float(cx)
                dy = by - float(cy)
                axis_side: list[int] = []
                for idx, key in axis_key.items():
                    if isinstance(key, (int, np.integer)):
                        theta = np.deg2rad(float(key))
                        proj = float(dx.loc[idx]) * np.cos(theta) + float(dy.loc[idx]) * np.sin(
                            theta
                        )
                        axis_side.append(1 if proj >= 0 else -1)
                    else:
                        axis_side.append(1 if float(dx.loc[idx]) >= 0 else -1)

                sorted_bottom["_axis_key"] = axis_key
                sorted_bottom["_axis_side"] = axis_side

                near_idx: list[int] = []
                far_idx: list[int] = []
                for _, grp in sorted_bottom.groupby(["_axis_key", "_axis_side"], sort=False):
                    grp = grp.sort_values("_dist", kind="mergesort")
                    near_count = max(1, len(grp) // 2)
                    near_idx.extend(grp.index[:near_count].tolist())
                    far_idx.extend(grp.index[near_count:].tolist())

                near_bottom = sorted_bottom.loc[near_idx].copy()
                far_bottom = sorted_bottom.loc[far_idx].copy()
            else:
                bottom_types = bottom_points["type"].astype(str)
                near_bottom = bottom_points[bottom_types.isin(["E_bottom", "N_bottom"])].copy()
                far_bottom = bottom_points[bottom_types.isin(["S_bottom", "W_bottom"])].copy()

        return top_points, center_points, near_bottom, far_bottom

    @staticmethod
    def _scatter_points(
        ax, points_df: pd.DataFrame, color: str, marker: str, size: float, zorder: int
    ) -> None:
        if points_df.empty:
            return
        x = pd.to_numeric(points_df.get("x_geo"), errors="coerce")
        y = pd.to_numeric(points_df.get("y_geo"), errors="coerce")
        valid = x.notna() & y.notna()
        if not valid.any():
            return
        ax.scatter(
            x[valid],
            y[valid],
            c=color,
            s=size,
            marker=marker,
            edgecolors="k",
            linewidths=0.4,
            alpha=0.95,
            zorder=zorder,
        )

    def _plot_member(self, ax, points_df: pd.DataFrame, marker: str, zbase: int) -> None:
        top_points, center_points, near_bottom, far_bottom = self._split_points(points_df)
        self._scatter_points(ax, top_points, "#1E40FF", marker, 42, zbase + 1)
        self._scatter_points(ax, near_bottom, "#FDE725", marker, 42, zbase + 1)
        self._scatter_points(ax, far_bottom, "#00B400", marker, 42, zbase + 1)
        self._scatter_points(ax, center_points, "#FF1E1E", marker, 54, zbase + 2)

    @staticmethod
    def _plot_convex_hull(ax, bottom_points: pd.DataFrame) -> None:
        """Plot convex hull of bottom points.

        Args:
            ax: matplotlib axis
            bottom_points: DataFrame with x_geo and y_geo columns
        """
        if bottom_points.empty:
            return

        x = pd.to_numeric(bottom_points.get("x_geo"), errors="coerce")
        y = pd.to_numeric(bottom_points.get("y_geo"), errors="coerce")
        valid = x.notna() & y.notna()

        if not valid.any() or valid.sum() < 3:
            return

        coords = np.column_stack([x[valid], y[valid]])
        shape = MultiPoint(coords).convex_hull

        if hasattr(shape, "exterior"):
            hull_x, hull_y = shape.exterior.xy
            ax.plot(hull_x, hull_y, color="#FF00FF", linewidth=2.0, zorder=7, alpha=0.8)

    def _plot_complex_on_dem(self) -> None:
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        with rasterio.open(self.dem_path) as src:
            dem_band = src.read(1, masked=True)
            dem = np.asarray(dem_band.filled(np.nan), dtype=float)
            bounds = src.bounds
            extent = [bounds.left, bounds.right, bounds.bottom, bounds.top]
            hillshade = self._compute_hillshade_array(
                dem, src.transform, self.azimuth_deg, self.altitude_deg
            )

        ax.imshow(hillshade, cmap="gray", extent=extent, origin="upper")

        # Plot transects (first member only)
        if self.transects_gdf is not None and not self.transects_gdf.empty:
            self.transects_gdf.plot(
                ax=ax,
                color="black",
                linewidth=1.2,
                linestyle="--",
                alpha=0.5,
                zorder=2,
            )

        # Define markers and base z-order for each member
        markers = ["o", "s", "^", "D", "P", "X"]

        # Plot all members overlaid
        type_legend = [
            Line2D(
                [0], [0], color="black", linestyle="--", linewidth=1.2, label="Transects (member 1)"
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor="#1E40FF",
                markeredgecolor="k",
                markersize=8,
                label="Top",
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor="#FF1E1E",
                markeredgecolor="k",
                markersize=9,
                label="Center",
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor="#FDE725",
                markeredgecolor="k",
                markersize=8,
                label="Bottom (near)",
            ),
            Line2D(
                [0],
                [0],
                marker="o",
                color="w",
                markerfacecolor="#00B400",
                markeredgecolor="k",
                markersize=8,
                label="Bottom (far)",
            ),
        ]

        member_legend = []
        for idx, member_id in enumerate(self.member_ids):
            marker = markers[idx % len(markers)]
            points_key = str(idx)
            member_points = self.finder_points_dict.get(points_key, pd.DataFrame())

            zbase = 5 + idx
            self._plot_member(ax, member_points, marker, zbase)

            # Plot convex hull if toggled
            if self.show_convex_hull and not member_points.empty:
                bottom_points = member_points[
                    member_points["type"].astype(str).str.contains("_bottom", na=False)
                ]
                self._plot_convex_hull(ax, bottom_points)

            # Create legend entry for this member
            member_legend.append(
                Line2D(
                    [0],
                    [0],
                    marker=marker,
                    color="w",
                    markerfacecolor="white",
                    markeredgecolor="k",
                    markersize=8,
                    label=f"Member {idx + 1}: {member_id}",
                )
            )

        # Plot crater centers if available
        for idx, member_id in enumerate(self.member_ids):
            center_xy = self.hybrid_centers_dict.get(str(idx))
            if center_xy is not None:
                ax.scatter(
                    [center_xy[0]],
                    [center_xy[1]],
                    c="green",
                    s=80,
                    marker="*",
                    edgecolors="k",
                    linewidths=0.7,
                    zorder=8 + idx,
                    alpha=0.8,
                )

        # Create final legend
        legend_handles = type_legend + member_legend
        if self.show_convex_hull:
            legend_handles.append(
                Line2D([0], [0], color="#FF00FF", linewidth=2.0, label="Convex hull")
            )

        # Add crater centers legend if available
        has_centers = any(
            self.hybrid_centers_dict.get(str(idx)) is not None
            for idx in range(len(self.member_ids))
        )
        if has_centers:
            legend_handles.append(
                Line2D(
                    [0],
                    [0],
                    marker="*",
                    color="w",
                    markerfacecolor="green",
                    markeredgecolor="k",
                    markersize=12,
                    label="Crater centers",
                )
            )

        ax.legend(handles=legend_handles, loc="upper right", fontsize=9)

        mode_label = "manual fix" if self.use_manual_fix else "standard"
        member_ids_str = ", ".join(self.member_ids)
        first_id = self.member_ids[0] if self.member_ids else "?"
        ax.set_title(
            f"Complex {self.complex_id} - DEM of cone {first_id} with all member points "
            f"[Members: {member_ids_str}] [{mode_label}]",
            fontsize=12,
            fontweight="bold",
        )
        ax.set_xlabel("Easting (m)")
        ax.set_ylabel("Northing (m)")
        ax.set_aspect("equal")
        ax.grid(False)

        self.figure.tight_layout()
        self.canvas.draw()

        if self.preview_png_path is not None:
            try:
                should_save = not self.preview_png_path.exists()
                if not should_save:
                    output_mtime = self.preview_png_path.stat().st_mtime
                    for dep in self.preview_dependencies:
                        if dep.exists() and dep.stat().st_mtime > output_mtime:
                            should_save = True
                            break

                if should_save:
                    self.preview_png_path.parent.mkdir(parents=True, exist_ok=True)
                    self.figure.savefig(self.preview_png_path, dpi=220, bbox_inches="tight")
            except Exception:  # pylint: disable=broad-exception-caught
                pass
