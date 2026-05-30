"""Qt main window for the MarsCONE MVP application.

All tab logic lives in marscone_mvp/tabs/*.py mixin classes.
MainWindow inherits from all of them via multiple inheritance.
"""
# pylint: disable=too-many-instance-attributes

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from PySide6.QtCore import QProcess, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QSlider,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from marscone_mvp.app_state import load_state, save_state
from marscone_mvp.pipeline import PipelineRunner
from marscone_mvp.table_model import DataFrameTableModel
from marscone_mvp.tabs.shared_helpers import SharedHelpersMixin
from marscone_mvp.tabs.app_tab import AppTabMixin
from marscone_mvp.tabs.cross_section_tab import CrossSectionMixin
from marscone_mvp.tabs.manual_fix_tab import ManualFixMixin
from marscone_mvp.tabs.dem_overlay_tab import DemOverlayMixin
from marscone_mvp.tabs.complex_cones_tab import ComplexConesMixin
from marscone_mvp.tabs.elevation_explorer_tab import ElevationExplorerMixin
from marscone_mvp.tabs.graphs_tab import GraphsMixin
from marscone_mvp.tabs.dataset_compare_tab import DatasetCompareMixin

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


# pylint: disable=too-many-ancestors
class MainWindow(
    QMainWindow,
    SharedHelpersMixin,
    AppTabMixin,
    CrossSectionMixin,
    ManualFixMixin,
    DemOverlayMixin,
    ComplexConesMixin,
    ElevationExplorerMixin,
    GraphsMixin,
    DatasetCompareMixin,
):
    """Main application window for configuring, running, and reviewing MVP workflows."""

    def __init__(self, mvp_root: Path) -> None:
        super().__init__()
        self.mvp_root = mvp_root
        self._state_loaded = False
        self.state = load_state(self.mvp_root)
        self.runner = PipelineRunner(self.mvp_root)
        self._init_view_state()
        self._init_table_models()

        self.setWindowTitle("MarsCONE MVP")
        self.resize(1280, 860)

        self._build_ui()
        self._bind_runner_signals()
        self._apply_state_to_form()
        self._state_loaded = True

    def _init_view_state(self) -> None:
        self.cross_section_process: QProcess | None = None
        self.cross_section_images: list[Path] = []
        self.cross_section_image_index: int = -1
        self.cross_section_current_pixmap: QPixmap | None = None
        self.dem_overlay_process: QProcess | None = None
        self.dem_overlay_images: list[Path] = []
        self.dem_overlay_image_index: int = -1
        self.dem_overlay_current_pixmap: QPixmap | None = None
        self.dem_overlay_context_current_pixmap: QPixmap | None = None
        self.dem_overlay_area_preview_base_pixmap: QPixmap | None = None
        self.dem_overlay_area_preview_bounds: tuple[float, float, float, float] | None = None
        self.dem_overlay_area_preview_centers: dict[str, tuple[float, float]] = {}
        self.manual_fix_combined_profile: pd.DataFrame | None = None
        self.manual_fix_profile_a_plot: tuple[np.ndarray, np.ndarray] | None = None
        self.manual_fix_profile_b_plot: tuple[np.ndarray, np.ndarray] | None = None
        self.manual_fix_slot_indices: dict[str, int] = {}
        self.manual_fix_sliders: dict[str, QSlider] = {}
        self.manual_fix_value_labels: dict[str, QLabel] = {}
        self.manual_fix_slot_targets: dict[str, dict[str, str]] = {}
        self.manual_fix_profiles_by_transect: dict[str, pd.DataFrame] = {}
        self.manual_fix_points_by_transect: dict[str, pd.DataFrame] = {}
        self.manual_fix_current_cone_id: str | None = None
        self.manual_fix_current_axis_deg: float | None = None
        self.manual_fix_slider_sync_in_progress = False

    def _init_table_models(self) -> None:
        self.results_model = DataFrameTableModel()
        self.complex_pairs_df = pd.DataFrame()  # DataFrame for complex pairs
        self.complex_pairs_model = DataFrameTableModel()  # Model for complex pairs
        self.complex_summary_model = DataFrameTableModel(
            float_precision=2
        )  # Model for complex summary
        self.complex_members_model = DataFrameTableModel(
            float_precision=2
        )  # Model for complex members
        self.complex_topology_model = DataFrameTableModel()  # Model for complex topology
        self.complex_topology_stats_model = DataFrameTableModel(
            float_precision=2
        )  # Model for complex topology stats
        self.complex_breach_singles_df = pd.DataFrame()  # DataFrame for breach singles
        self.complex_breach_singles_model = DataFrameTableModel()  # Model for breach singles
        self.breached_saved_points_df = pd.DataFrame()
        self.breached_saved_points_model = DataFrameTableModel(float_precision=2)
        self.breached_center_xy: tuple[float, float] | None = None
        self.breached_profile_distances: np.ndarray | None = None
        self.breached_profile_elevations: np.ndarray | None = None
        self.breached_profile_selected_index: int | None = None
        self.breached_map_snapshot: dict | None = None
        self.breached_saved_table_sync_in_progress = False
        self.breached_suggested_angle_deg: float | None = None
        self.breached_suggested_index: int | None = None
        self.breached_angle_sync_in_progress = False

    def _build_ui(self) -> None:
        self.tabs = QTabWidget()

        # ── Tab 0: App ─────────────────────────────────────────────
        app_page = QWidget()
        app_layout = QVBoxLayout(app_page)
        app_layout.addWidget(self._build_project_group())
        app_layout.addWidget(self._build_parameters_group())
        app_layout.addLayout(self._build_actions_row())
        app_layout.addWidget(self._build_results_group(), stretch=2)

        bottom_splitter = QSplitter(Qt.Horizontal)
        bottom_splitter.addWidget(self._build_input_diagnostics_group())
        bottom_splitter.addWidget(self._build_logs_group())
        bottom_splitter.setSizes([600, 300])  # initial widths in px
        app_layout.addWidget(bottom_splitter, stretch=1)

        # ── Tab 1: Cross-section ───────────────────────────────────
        self.tabs.addTab(app_page, "App")
        self.tabs.addTab(self._build_crosssection_page(), "Cross-section")
        self.tabs.addTab(self._build_manual_fix_page(), "Manual Fix")
        self.tabs.addTab(self._build_dem_overlay_page(), "DEM overlay")
        self.tabs.addTab(self._build_complex_cones_page(), "Complex Cones")
        self.tabs.addTab(self._build_breached_cones_page(), "Elevation Explorer")
        self.tabs.addTab(self._build_graphs_page(), "Graphs")
        self.tabs.addTab(self._build_graphs_dataset_compare_tab(), "Dataset compare")

        self.setCentralWidget(self.tabs)
        self.setStatusBar(QStatusBar())

    def closeEvent(self, event) -> None:  # type: ignore[override]
        try:
            self.state = self._collect_state_from_form()
            save_state(self.mvp_root, self.state)
        except Exception:  # pylint: disable=broad-exception-caught
            # Never block closing the window because of a state write problem.
            pass
        super().closeEvent(event)
