"""Mixin for the ManualFixMixin section of MainWindow."""
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




class ManualFixMixin:
    """Mixin — mixed into MainWindow via multiple inheritance."""

    def _build_manual_fix_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        info_group = QGroupBox("Manual Fix")
        info_layout = QGridLayout(info_group)
        self.manual_fix_source_label = QLabel("Source: current Cross-section preview")
        self.manual_fix_target_label = QLabel("Cone/axis: -")
        self.manual_fix_file_label = QLabel("Overrides file: -")
        info_layout.addWidget(self.manual_fix_source_label, 0, 0, 1, 2)
        info_layout.addWidget(self.manual_fix_target_label, 1, 0, 1, 2)
        info_layout.addWidget(self.manual_fix_file_label, 2, 0, 1, 2)

        actions_row = QHBoxLayout()
        self.manual_fix_load_current_button = QPushButton("Load from Cross-section")
        self.manual_fix_read_saved_button = QPushButton("Read saved fixes")
        self.manual_fix_save_button = QPushButton("Save fixes")
        self.manual_fix_clear_saved_button = QPushButton("Clear saved fixes")
        actions_row.addWidget(self.manual_fix_load_current_button)
        actions_row.addWidget(self.manual_fix_read_saved_button)
        actions_row.addWidget(self.manual_fix_save_button)
        actions_row.addWidget(self.manual_fix_clear_saved_button)
        actions_row.addStretch(1)

        self.manual_fix_load_current_button.clicked.connect(
            self._manual_fix_load_from_current_cross_section
        )
        self.manual_fix_read_saved_button.clicked.connect(self._manual_fix_read_saved_for_current)
        self.manual_fix_save_button.clicked.connect(self._manual_fix_save_current)
        self.manual_fix_clear_saved_button.clicked.connect(self._manual_fix_clear_saved_for_current)

        reminder_label = QLabel(
            "Note: after saving or clearing Manual Fix points, rerun Analyzer to refresh metrics "
            "and graphs."
        )
        reminder_label.setWordWrap(True)

        self.manual_fix_figure, self.manual_fix_axes = plt.subplots(figsize=(12, 5.2))
        self.manual_fix_canvas = FigureCanvas(self.manual_fix_figure)
        self.manual_fix_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        sliders_group = QGroupBox("Point sliders (x along profile)")
        sliders_layout = QGridLayout(sliders_group)

        for row_idx, (slot_key, slot_label, _color) in enumerate(MANUAL_FIX_SLOTS):
            label = QLabel(slot_label)
            slider = QSlider(Qt.Horizontal)
            slider.setEnabled(False)
            slider.setSingleStep(1)
            slider.setPageStep(5)
            value_label = QLabel("-")
            slider.valueChanged.connect(
                lambda _value, key=slot_key: self._manual_fix_on_slider_changed(key)
            )
            sliders_layout.addWidget(label, row_idx, 0)
            sliders_layout.addWidget(slider, row_idx, 1)
            sliders_layout.addWidget(value_label, row_idx, 2)
            self.manual_fix_sliders[slot_key] = slider
            self.manual_fix_value_labels[slot_key] = value_label

        layout.addWidget(info_group)
        layout.addLayout(actions_row)
        layout.addWidget(reminder_label)
        layout.addWidget(self.manual_fix_canvas, stretch=1)
        layout.addWidget(sliders_group)
        return page

    def _manual_fix_overrides_path(self) -> Path:
        output_dir = Path(self.cs_output_dir_edit.text().strip())
        return output_dir / "manual_point_overrides.csv"

    def _manual_fix_load_from_current_cross_section(self) -> None:
        if not self.cross_section_images:
            self._refresh_cross_section_preview(reset_to_first=True)

        if not self.cross_section_images:
            QMessageBox.information(
                self, "Manual Fix", "No cross-section PNG found in output directory."
            )
            return

        self.cross_section_image_index = max(self.cross_section_image_index, 0)

        image_path = self.cross_section_images[self.cross_section_image_index]
        parsed = self._extract_cone_axis_from_cross_section_name(image_path.name)
        if parsed is None:
            QMessageBox.information(
                self,
                "Manual Fix",
                f"Could not parse cone/axis from file name: {image_path.name}",
            )
            return

        cone_id, axis_deg = parsed
        model = self._manual_fix_build_model(cone_id, axis_deg)
        if model is None:
            return

        self.manual_fix_current_cone_id = cone_id
        self.manual_fix_current_axis_deg = axis_deg
        self.manual_fix_combined_profile = model["combined_profile"]
        self.manual_fix_profile_a_plot = model["profile_a_plot"]
        self.manual_fix_profile_b_plot = model["profile_b_plot"]
        self.manual_fix_slot_indices = model["slot_indices"]
        self.manual_fix_slot_targets = model["slot_targets"]
        self.manual_fix_profiles_by_transect = model["profiles_by_transect"]
        self.manual_fix_points_by_transect = model["points_by_transect"]

        self.manual_fix_slider_sync_in_progress = True
        try:
            max_index = max(len(self.manual_fix_combined_profile) - 1, 0)
            for slot_key, _slot_label, _color in MANUAL_FIX_SLOTS:
                slider = self.manual_fix_sliders[slot_key]
                slider.setEnabled(max_index > 0)
                slider.setRange(0, max_index)
                slider.setValue(int(self.manual_fix_slot_indices.get(slot_key, 0)))
        finally:
            self.manual_fix_slider_sync_in_progress = False

        self.manual_fix_target_label.setText(f"Cone/axis: cone {cone_id}, axis {axis_deg:.0f} deg")
        self.manual_fix_file_label.setText(f"Overrides file: {self._manual_fix_overrides_path()}")
        self._manual_fix_update_value_labels()
        self._manual_fix_draw_plot()
        self.statusBar().showMessage("Manual Fix: loaded current cross-section.", 4000)

    def _manual_fix_build_model(self, cone_id: str, axis_deg: float) -> dict | None:
        finder_path = Path(self.cs_finder_path_edit.text().strip())
        profile_dir = Path(self.cs_profile_dir_edit.text().strip())

        if not finder_path.exists():
            QMessageBox.warning(self, "Manual Fix", f"Finder CSV not found:\n{finder_path}")
            return None
        if not profile_dir.exists():
            QMessageBox.warning(self, "Manual Fix", f"Profile directory not found:\n{profile_dir}")
            return None

        finder_df = pd.read_csv(finder_path, sep=";")
        if finder_df.empty:
            QMessageBox.information(self, "Manual Fix", "Finder CSV is empty.")
            return None

        finder_df = finder_df.copy()
        finder_df["cone_id_norm"] = (
            finder_df["cone_id"].astype(str).str.replace(r"\.0$", "", regex=True)
        )
        finder_df = finder_df[finder_df["cone_id_norm"] == str(cone_id)]
        if finder_df.empty:
            QMessageBox.information(self, "Manual Fix", f"No finder points for cone {cone_id}.")
            return None

        finder_df["angle_deg"] = finder_df["orientation"].apply(parse_deg)
        transects = finder_df.groupby("transect_id")["angle_deg"].first().to_dict()

        if not transects:
            QMessageBox.information(self, "Manual Fix", "No transects found for selected cone.")
            return None

        axis_mod = axis_deg % 180.0
        transect_a = min(
            transects,
            key=lambda tid: min(
                abs((transects[tid] % 180.0) - axis_mod),
                180.0 - abs((transects[tid] % 180.0) - axis_mod),
            ),
        )
        angle_a = float(transects[transect_a])

        complement = (angle_a + 180.0) % 360.0
        candidates = [tid for tid in transects if tid != transect_a]
        if not candidates:
            QMessageBox.information(self, "Manual Fix", "No opposite transect found for axis pair.")
            return None

        transect_b = min(
            candidates,
            key=lambda tid: min(
                abs(float(transects[tid]) - complement),
                360.0 - abs(float(transects[tid]) - complement),
            ),
        )

        profile_a_path = profile_dir / f"profile_{transect_a}.csv"
        profile_b_path = profile_dir / f"profile_{transect_b}.csv"
        if not profile_a_path.exists() or not profile_b_path.exists():
            QMessageBox.warning(
                self,
                "Manual Fix",
                f"Missing profile file(s):\n{profile_a_path}\n{profile_b_path}",
            )
            return None

        prof_a = pd.read_csv(profile_a_path, sep=";")
        prof_b = pd.read_csv(profile_b_path, sep=";")

        pts_a = finder_df[finder_df["transect_id"] == transect_a].copy()
        pts_b = finder_df[finder_df["transect_id"] == transect_b].copy()
        pts_a = attach_distance_to_finder_points(prof_a, pts_a)
        pts_b = attach_distance_to_finder_points(prof_b, pts_b)

        center_a = pts_a[pts_a["type"] == "C"]
        center_b = pts_b[pts_b["type"] == "C"]
        if center_a.empty or center_b.empty:
            QMessageBox.information(
                self, "Manual Fix", "Center point C is missing in one of transects."
            )
            return None

        ca_dist = float(center_a["distance"].iloc[0])
        cb_dist = float(center_b["distance"].iloc[0])

        x_min = float(prof_a["distance"].min())
        x_max = float(prof_a["distance"].max())
        center_target = 0.5 * (x_min + x_max)

        prof_a_x = prof_a["distance"] - ca_dist + center_target
        prof_b_x = cb_dist - prof_b["distance"] + center_target

        prof_a_samples = prof_a.copy()
        prof_a_samples["x_plot"] = prof_a_x
        prof_a_samples["transect_id"] = str(transect_a)
        prof_b_samples = prof_b.copy()
        prof_b_samples["x_plot"] = prof_b_x
        prof_b_samples["transect_id"] = str(transect_b)

        pts_a["x_plot"] = pts_a["distance"] - ca_dist + center_target
        pts_b["x_plot"] = cb_dist - pts_b["distance"] + center_target
        all_pts = pd.concat([pts_a, pts_b], ignore_index=True)

        c_x = float(pts_a.loc[pts_a["type"] == "C", "x_plot"].iloc[0])

        tops = all_pts[all_pts["type"].str.contains("_top", na=False)].copy().sort_values("x_plot")
        top_left = tops.iloc[0] if len(tops) >= 1 else None
        top_right = tops.iloc[-1] if len(tops) >= 2 else None

        bottoms = all_pts[all_pts["type"].str.contains("_bottom", na=False)].copy()
        bottom_left_near = bottom_right_near = None
        bottom_left_far = bottom_right_far = None

        if not bottoms.empty:
            left = bottoms[bottoms["x_plot"] < c_x].copy()
            if not left.empty:
                left_sorted = left.iloc[(left["x_plot"] - c_x).abs().argsort()]
                bottom_left_near = left_sorted.iloc[0]
                if len(left_sorted) > 1:
                    bottom_left_far = left_sorted.iloc[1]

            right = bottoms[bottoms["x_plot"] >= c_x].copy()
            if not right.empty:
                right_sorted = right.iloc[(right["x_plot"] - c_x).abs().argsort()]
                bottom_right_near = right_sorted.iloc[0]
                if len(right_sorted) > 1:
                    bottom_right_far = right_sorted.iloc[1]

        combined_profile = (
            pd.concat(
                [
                    pd.DataFrame({"x_plot": prof_a_x, "elevation": prof_a["elevation"]}),
                    pd.DataFrame({"x_plot": prof_b_x, "elevation": prof_b["elevation"]}),
                ],
                ignore_index=True,
            )
            .sort_values("x_plot", kind="mergesort")
            .reset_index(drop=True)
        )

        def nearest_index(x_value: float) -> int:
            return int((combined_profile["x_plot"] - x_value).abs().idxmin())

        center_index = nearest_index(c_x)

        center_point = pts_a.loc[pts_a["type"] == "C"].iloc[0]

        def _target_from_row(point_row: pd.Series | None) -> dict[str, str]:
            base_row = point_row if point_row is not None else center_point
            return {
                "transect_id": str(base_row["transect_id"]),
                "type": str(base_row["type"]),
            }

        slot_indices = {
            "left_far_bottom": (
                nearest_index(float(bottom_left_far["x_plot"]))
                if bottom_left_far is not None
                else center_index
            ),
            "left_near_bottom": (
                nearest_index(float(bottom_left_near["x_plot"]))
                if bottom_left_near is not None
                else center_index
            ),
            "left_top": (
                nearest_index(float(top_left["x_plot"])) if top_left is not None else center_index
            ),
            "center": center_index,
            "right_top": (
                nearest_index(float(top_right["x_plot"])) if top_right is not None else center_index
            ),
            "right_near_bottom": (
                nearest_index(float(bottom_right_near["x_plot"]))
                if bottom_right_near is not None
                else center_index
            ),
            "right_far_bottom": (
                nearest_index(float(bottom_right_far["x_plot"]))
                if bottom_right_far is not None
                else center_index
            ),
        }

        slot_targets = {
            "left_far_bottom": _target_from_row(bottom_left_far),
            "left_near_bottom": _target_from_row(bottom_left_near),
            "left_top": _target_from_row(top_left),
            "center": _target_from_row(center_point),
            "right_top": _target_from_row(top_right),
            "right_near_bottom": _target_from_row(bottom_right_near),
            "right_far_bottom": _target_from_row(bottom_right_far),
        }

        return {
            "combined_profile": combined_profile,
            "profile_a_plot": (prof_a_x.to_numpy(), prof_a["elevation"].to_numpy()),
            "profile_b_plot": (prof_b_x.to_numpy(), prof_b["elevation"].to_numpy()),
            "slot_indices": slot_indices,
            "slot_targets": slot_targets,
            "profiles_by_transect": {
                str(transect_a): prof_a_samples,
                str(transect_b): prof_b_samples,
            },
            "points_by_transect": {
                str(transect_a): pts_a.copy(),
                str(transect_b): pts_b.copy(),
            },
        }

    def _manual_fix_update_value_labels(self) -> None:
        if self.manual_fix_combined_profile is None or self.manual_fix_combined_profile.empty:
            for value_label in self.manual_fix_value_labels.values():
                value_label.setText("-")
            return

        for slot_key, _slot_label, _color in MANUAL_FIX_SLOTS:
            idx = int(self.manual_fix_slot_indices.get(slot_key, 0))
            idx = max(0, min(idx, len(self.manual_fix_combined_profile) - 1))
            row = self.manual_fix_combined_profile.iloc[idx]
            self.manual_fix_value_labels[slot_key].setText(
                f"x={float(row['x_plot']):.2f} m, z={float(row['elevation']):.2f} m"
            )

    def _manual_fix_draw_plot(self) -> None:
        self.manual_fix_axes.clear()

        if self.manual_fix_combined_profile is None or self.manual_fix_combined_profile.empty:
            self.manual_fix_axes.text(
                0.5, 0.5, "No Manual Fix data loaded.", ha="center", va="center"
            )
            self.manual_fix_axes.set_axis_off()
            self.manual_fix_canvas.draw_idle()
            return

        self.manual_fix_axes.set_axis_on()
        if self.manual_fix_profile_a_plot is not None:
            x_a, z_a = self.manual_fix_profile_a_plot
            self.manual_fix_axes.plot(x_a, z_a, "k-", linewidth=1.4, label="Transect A")
        if self.manual_fix_profile_b_plot is not None:
            x_b, z_b = self.manual_fix_profile_b_plot
            self.manual_fix_axes.plot(x_b, z_b, "k--", linewidth=1.4, label="Transect B")

        for slot_key, slot_label, color in MANUAL_FIX_SLOTS:
            idx = int(self.manual_fix_slot_indices.get(slot_key, 0))
            idx = max(0, min(idx, len(self.manual_fix_combined_profile) - 1))
            row = self.manual_fix_combined_profile.iloc[idx]
            self.manual_fix_axes.scatter(
                float(row["x_plot"]),
                float(row["elevation"]),
                s=80,
                color=color,
                edgecolors="k",
                zorder=5,
                label=slot_label,
            )

        self.manual_fix_axes.set_xlabel("Distance (m)")
        self.manual_fix_axes.set_ylabel("Elevation (m)")
        if (
            self.manual_fix_current_cone_id is not None
            and self.manual_fix_current_axis_deg is not None
        ):
            self.manual_fix_axes.set_title(
                "Manual Fix - cone "
                f"{self.manual_fix_current_cone_id} "
                f"(axis ~ {self.manual_fix_current_axis_deg:.0f} deg)"
            )
        self.manual_fix_axes.grid(True, alpha=0.3)

        handles, labels = self.manual_fix_axes.get_legend_handles_labels()
        unique = {}
        for handle, label in zip(handles, labels):
            if label not in unique:
                unique[label] = handle
        self.manual_fix_axes.legend(unique.values(), unique.keys(), loc="upper right", fontsize=8)

        self.manual_fix_figure.tight_layout()
        self.manual_fix_canvas.draw_idle()

    def _manual_fix_on_slider_changed(self, slot_key: str) -> None:
        if self.manual_fix_slider_sync_in_progress:
            return
        if self.manual_fix_combined_profile is None or self.manual_fix_combined_profile.empty:
            return

        slider = self.manual_fix_sliders[slot_key]
        self.manual_fix_slot_indices[slot_key] = int(slider.value())
        self._manual_fix_update_value_labels()
        self._manual_fix_draw_plot()

    def _manual_fix_read_saved_for_current(self) -> None:
        if self.manual_fix_current_cone_id is None or self.manual_fix_current_axis_deg is None:
            QMessageBox.information(self, "Manual Fix", "Load a cross-section first.")
            return

        overrides_path = self._manual_fix_overrides_path()
        if not overrides_path.exists():
            QMessageBox.information(
                self, "Manual Fix", f"Overrides file not found:\n{overrides_path}"
            )
            return

        overrides_df = pd.read_csv(overrides_path, sep=";")
        if overrides_df.empty:
            QMessageBox.information(self, "Manual Fix", "Overrides file is empty.")
            return

        mask = (overrides_df["cone_id"].astype(str) == str(self.manual_fix_current_cone_id)) & (
            pd.to_numeric(overrides_df["axis_deg"], errors="coerce").round(3)
            == round(float(self.manual_fix_current_axis_deg), 3)
        )
        selected = overrides_df[mask]
        if selected.empty:
            QMessageBox.information(self, "Manual Fix", "No saved fixes for current cone/axis.")
            return

        if self.manual_fix_combined_profile is None or self.manual_fix_combined_profile.empty:
            return

        max_index = len(self.manual_fix_combined_profile) - 1
        self.manual_fix_slider_sync_in_progress = True
        try:
            for _, row in selected.iterrows():
                slot_key = str(row.get("slot", ""))
                if slot_key not in self.manual_fix_sliders:
                    continue
                idx_value = pd.to_numeric(row.get("sample_idx"), errors="coerce")
                if pd.isna(idx_value):
                    continue
                idx = int(idx_value)
                idx = max(0, min(idx, max_index))
                self.manual_fix_slot_indices[slot_key] = idx
                self.manual_fix_sliders[slot_key].setValue(idx)
        finally:
            self.manual_fix_slider_sync_in_progress = False

        self._manual_fix_update_value_labels()
        self._manual_fix_draw_plot()
        self.statusBar().showMessage("Manual Fix: saved overrides loaded.", 4000)

    def _manual_fix_save_current(self) -> None:
        if self.manual_fix_current_cone_id is None or self.manual_fix_current_axis_deg is None:
            QMessageBox.information(self, "Manual Fix", "Load a cross-section first.")
            return
        if self.manual_fix_combined_profile is None or self.manual_fix_combined_profile.empty:
            QMessageBox.information(self, "Manual Fix", "No profile data to save.")
            return
        if not self.manual_fix_slot_targets or not self.manual_fix_profiles_by_transect:
            QMessageBox.information(
                self, "Manual Fix", "No point target mapping loaded. Reload current cross-section."
            )
            return

        output_dir = Path(self.cs_output_dir_edit.text().strip())
        output_dir.mkdir(parents=True, exist_ok=True)
        overrides_path = self._manual_fix_overrides_path()

        rows = []
        timestamp = pd.Timestamp.utcnow().isoformat()

        center_idx = int(self.manual_fix_slot_indices.get("center", 0))
        center_idx = max(0, min(center_idx, len(self.manual_fix_combined_profile) - 1))
        center_x = float(self.manual_fix_combined_profile.iloc[center_idx]["x_plot"])

        def _build_slot_targets(slot_key: str, slot_x: float) -> list[dict[str, str]]:
            if slot_key == "center":
                return [
                    {"transect_id": str(transect_id), "type": "C"}
                    for transect_id in self.manual_fix_profiles_by_transect.keys()
                ]

            targets: list[dict[str, str]] = []
            is_left = slot_key.startswith("left_")
            is_right = slot_key.startswith("right_")
            is_top = "top" in slot_key
            is_bottom = "bottom" in slot_key
            is_near = "near" in slot_key

            if self.manual_fix_points_by_transect:
                for transect_id, points_df in self.manual_fix_points_by_transect.items():
                    if points_df is None or points_df.empty:
                        continue

                    candidates = points_df.copy()
                    point_types = candidates["type"].astype(str)
                    if is_top:
                        candidates = candidates[point_types.str.contains("_top", na=False)]
                    elif is_bottom:
                        candidates = candidates[point_types.str.contains("_bottom", na=False)]

                    if candidates.empty:
                        continue

                    if is_bottom and (is_left or is_right):
                        side_candidates = (
                            candidates[candidates["x_plot"] < center_x]
                            if is_left
                            else candidates[candidates["x_plot"] >= center_x]
                        )
                        if not side_candidates.empty:
                            candidates = side_candidates

                    if candidates.empty:
                        continue

                    if is_top and (is_left or is_right):
                        ordered = candidates.sort_values("x_plot", kind="mergesort")
                        pick_row = ordered.iloc[0] if is_left else ordered.iloc[-1]
                    elif is_bottom:
                        candidates = candidates.copy()
                        candidates["dist_to_center"] = (candidates["x_plot"] - center_x).abs()
                        pick_row = (
                            candidates.sort_values("dist_to_center", kind="mergesort").iloc[0]
                            if is_near
                            else candidates.sort_values("dist_to_center", kind="mergesort").iloc[-1]
                        )
                    else:
                        pick_row = candidates.iloc[
                            (candidates["x_plot"] - slot_x).abs().argsort()
                        ].iloc[0]

                    targets.append(
                        {
                            "transect_id": str(transect_id),
                            "type": str(pick_row["type"]),
                        }
                    )

            if targets:
                return targets

            target = self.manual_fix_slot_targets.get(slot_key)
            if target:
                return [
                    {
                        "transect_id": str(target.get("transect_id", "")),
                        "type": str(target.get("type", "")),
                    }
                ]
            return []

        for slot_key, _slot_label, _color in MANUAL_FIX_SLOTS:
            idx = int(self.manual_fix_slot_indices.get(slot_key, 0))
            idx = max(0, min(idx, len(self.manual_fix_combined_profile) - 1))
            row = self.manual_fix_combined_profile.iloc[idx]
            target_entries = _build_slot_targets(slot_key, float(row["x_plot"]))

            for target_entry in target_entries:
                target_transect = target_entry["transect_id"]
                target_type = target_entry["type"]
                profile_samples = self.manual_fix_profiles_by_transect.get(target_transect)
                if profile_samples is None or profile_samples.empty:
                    continue

                nearest_profile_idx = int(
                    (profile_samples["x_plot"] - float(row["x_plot"])).abs().idxmin()
                )
                nearest_profile_row = profile_samples.loc[nearest_profile_idx]
                rows.append(
                    {
                        "cone_id": str(self.manual_fix_current_cone_id),
                        "axis_deg": float(self.manual_fix_current_axis_deg),
                        "slot": slot_key,
                        "sample_idx": idx,
                        "transect_id": target_transect,
                        "type": target_type,
                        "x_geo": float(nearest_profile_row["x_geo"]),
                        "y_geo": float(nearest_profile_row["y_geo"]),
                        "x_plot": float(row["x_plot"]),
                        "elevation": float(nearest_profile_row["elevation"]),
                        "updated_at_utc": timestamp,
                    }
                )

        new_df = pd.DataFrame(rows)
        if overrides_path.exists():
            old_df = pd.read_csv(overrides_path, sep=";")
            if not old_df.empty:
                old_df = old_df[
                    ~(
                        (old_df["cone_id"].astype(str) == str(self.manual_fix_current_cone_id))
                        & (
                            pd.to_numeric(old_df["axis_deg"], errors="coerce").round(3)
                            == round(float(self.manual_fix_current_axis_deg), 3)
                        )
                    )
                ]
                new_df = pd.concat([old_df, new_df], ignore_index=True)

        new_df.to_csv(overrides_path, sep=";", index=False)
        self.manual_fix_file_label.setText(f"Overrides file: {overrides_path}")
        self.statusBar().showMessage(
            "Manual Fix saved. Rerun Analyzer to refresh metrics and graphs.",
            7000,
        )

    def _manual_fix_clear_saved_for_current(self) -> None:
        if self.manual_fix_current_cone_id is None or self.manual_fix_current_axis_deg is None:
            QMessageBox.information(self, "Manual Fix", "Load a cross-section first.")
            return

        overrides_path = self._manual_fix_overrides_path()
        if not overrides_path.exists():
            QMessageBox.information(self, "Manual Fix", "Overrides file does not exist.")
            return

        df = pd.read_csv(overrides_path, sep=";")
        if df.empty:
            QMessageBox.information(self, "Manual Fix", "Overrides file is already empty.")
            return

        before = len(df)
        df = df[
            ~(
                (df["cone_id"].astype(str) == str(self.manual_fix_current_cone_id))
                & (
                    pd.to_numeric(df["axis_deg"], errors="coerce").round(3)
                    == round(float(self.manual_fix_current_axis_deg), 3)
                )
            )
        ]
        removed = before - len(df)
        df.to_csv(overrides_path, sep=";", index=False)
        self.statusBar().showMessage(
            "Manual Fix: removed "
            f"{removed} saved row(s). Rerun Analyzer to refresh metrics and graphs.",
            7000,
        )

