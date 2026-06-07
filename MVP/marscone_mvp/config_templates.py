"""Build runtime config dictionaries for Generator, Finder and Analyzer."""

from __future__ import annotations

from marscone_mvp.crs import resolve_crs


def build_generator_config(state: dict) -> dict:
    """Return Generator config derived from current UI state."""
    generator = state["generator"]
    crs = resolve_crs(state)
    return {
        "paths": {
            "base": state["base_path"],
            "input": {
                "masks": "input/crop",
                "dem": "input/dem",
                "points": "input/points",
            },
            "output": {
                "dem_cropped": "output/generator/dem/cropped",
                "dem_slope": "output/generator/dem/slope",
                "profiles_whole": "output/generator/profiles/whole",
                "profiles_cropped": "output/generator/profiles/cropped",
            },
            "db": "db/database.gpkg",
        },
        "db_layers": {
            "points": "points",
            "transects": "transects",
            "profiles": "profiles",
            "buffers": "buffers",
            "masks": "cones",
        },
        "crs": crs,
        "parameters": {
            "transect_length": generator["transect_length"],
            "profile_resolution": generator["profile_resolution"],
            "buffer_width": generator["buffer_width"],
            "mode": generator["mode"],
            "transect_angle_step": generator["transect_angle_step"],
        },
    }


def build_finder_config(state: dict) -> dict:
    """Return Finder config derived from current UI state."""
    finder = state["finder"]
    return {
        "paths": {
            "base": state["base_path"],
            "db": "db/database.gpkg",
            "output": {
                "results_csv": "output/finder/finder_method.csv",
            },
        },
        "db_layers": {
            "profiles": "profiles",
            "points": "points",
        },
        "smoothing": {
            "enabled": finder.get("smoothing_enabled", False),
            "window_m": finder.get("smoothing_window_m", 120.0),
            "polyorder": finder.get("smoothing_polyorder", 2),
        },
        "detection": {
            "bottom_edge_guard_frac": finder.get("bottom_edge_guard_frac", 0.12),
        },
    }


def build_analyzer_config(state: dict) -> dict:
    """Return Analyzer config derived from current UI state."""
    analyzer = state["analyzer"]
    crs = resolve_crs(state)
    return {
        "paths": {
            "base": state["base_path"],
            "input": {
                "profiles": "output/generator/profiles/whole",
                "points": "output/finder",
                "centers": "input/points",
            },
            "output": {
                "shapes": "output/analyzer/shapes",
                "csv": "output/analyzer/results.csv",
            },
            "db": "db/database.gpkg",
        },
        "csv": {
            "sep": ";",
        },
        "shape": {
            "crs": crs,
        },
        "classification": {
            "shape_threshold": analyzer["shape_threshold"],
        },
        "quality": {
            "preset": analyzer.get("quality_preset", "terrestrial"),
            "thresholds": analyzer.get("quality_thresholds", {}),
        },
        "manual_fix": {
            "enabled": analyzer.get("use_manual_fix", False),
            "overrides_csv": "output/figures/cross_sections/manual_point_overrides.csv",
        },
        "selected_profiles": [],
        "export_geojson": analyzer["export_geojson"],
        "export_summary_gpkg": analyzer["export_summary_gpkg"],
    }


def build_all_configs(state: dict) -> dict:
    """Build configs for all pipeline modules in one mapping."""
    return {
        "generator": build_generator_config(state),
        "finder": build_finder_config(state),
        "analyzer": build_analyzer_config(state),
    }
