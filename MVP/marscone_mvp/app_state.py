"""Persistent app state utilities for MarsCONE MVP."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable


STATE_FILE_NAME = "app_state.json"
DEV_MODULE_DIRS = ("generator-py", "finder-py", "analyzer-py")
ROOT_PATH_KEYS = ("dev_root", "base_path", "python_executable")
NESTED_PATH_KEYS = {
    "cross_section": ("profile_dir", "finder_path", "output_dir"),
    "dem_overlay": (
        "dem_dir",
        "gpkg_path",
        "output_dir",
        "centers_hybrid_path",
    ),
}


def _first_existing(candidates: list[Path]) -> Path:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _first_valid_dev_root(candidates: list[Path]) -> Path:
    """Pick the first existing folder that contains all MarsCONE module dirs."""
    for candidate in candidates:
        if not candidate.exists():
            continue
        if all((candidate / child).exists() for child in DEV_MODULE_DIRS):
            return candidate
    return _first_existing(candidates)


def _resolve_state_path(value: str, mvp_root: Path) -> str:
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path)
    return str((mvp_root / path).resolve())


def _to_portable_state_path(value: str, mvp_root: Path) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute():
        return value
    try:
        return path.resolve().relative_to(mvp_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _rewrite_dataset_compare_sources(
    sources_text: str,
    mvp_root: Path,
    mapper: Callable[[str, Path], str],
) -> str:
    rewritten_lines: list[str] = []
    for raw_line in sources_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ";" not in line:
            rewritten_lines.append(raw_line)
            continue

        label, raw_path = line.split(";", 1)
        raw_path = raw_path.strip()
        if raw_path:
            mapped_path = mapper(raw_path, mvp_root)
            rewritten_lines.append(f"{label.strip()};{mapped_path}")
        else:
            rewritten_lines.append(raw_line)
    return "\n".join(rewritten_lines)


def _map_state_paths_in_place(
    state: dict,
    mvp_root: Path,
    mapper: Callable[[str, Path], str],
) -> None:
    for key in ROOT_PATH_KEYS:
        value = state.get(key)
        if isinstance(value, str) and value.strip():
            state[key] = mapper(value.strip(), mvp_root)

    for section, keys in NESTED_PATH_KEYS.items():
        section_dict = state.get(section, {})
        if not isinstance(section_dict, dict):
            continue
        for key in keys:
            value = section_dict.get(key)
            if isinstance(value, str) and value.strip():
                section_dict[key] = mapper(value.strip(), mvp_root)

    dataset_compare = state.get("dataset_compare", {})
    if not isinstance(dataset_compare, dict):
        return

    sources_text = dataset_compare.get("sources_text")
    if isinstance(sources_text, str) and sources_text.strip():
        dataset_compare["sources_text"] = _rewrite_dataset_compare_sources(
            sources_text,
            mvp_root,
            mapper,
        )


def _resolve_state_paths_in_place(state: dict, mvp_root: Path) -> None:
    _map_state_paths_in_place(state, mvp_root, _resolve_state_path)


def _make_state_paths_portable(state: dict, mvp_root: Path) -> dict:
    portable_state = json.loads(json.dumps(state))
    _map_state_paths_in_place(portable_state, mvp_root, _to_portable_state_path)

    return portable_state


def _fallback_missing_core_paths(state: dict, defaults: dict) -> None:
    for key in ["dev_root", "base_path", "python_executable"]:
        value = state.get(key)
        if not isinstance(value, str) or not value.strip() or not Path(value).exists():
            state[key] = defaults[key]


def default_state(mvp_root: Path) -> dict:
    """Return default UI state for first run in the given MVP root."""
    dev_root = _first_valid_dev_root([mvp_root.parent / "dev", mvp_root / "dev"])
    default_base = _first_existing([dev_root / "data" / "test_set"])
    return {
        "dev_root": str(dev_root),
        "base_path": str(default_base),
        "python_executable": sys.executable,
        "crs": {
            "mode": "auto",
            "source": "dem",
            "manual_value": (
                "+proj=eqc +lat_ts=45 +lat_0=0 +lon_0=29.03 +x_0=0 +y_0=0 "
                "+R=3386150.7470034 +units=m +no_defs=True"
            ),
            "ignore_celestial_body": True,
        },
        "generator": {
            "mode": "auto",
            "transect_length": 200,
            "profile_resolution": 1,
            "buffer_width": 200,
            "transect_angle_step": 45,
        },
        "finder": {
            "smoothing_enabled": False,
            "smoothing_window_m": 120.0,
            "smoothing_polyorder": 2,
            "bottom_edge_guard_frac": 0.12,
        },
        "analyzer": {
            "shape_threshold": 1.0,
            "buffer_distance": 1.0,
            "quality_preset": "terrestrial",
            "quality_thresholds": {
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
            "use_manual_fix": False,
            "export_geojson": False,
            "export_summary_gpkg": True,
        },
        "cross_section": {
            "profile_dir": str(default_base / "output" / "generator" / "profiles" / "whole"),
            "finder_path": str(default_base / "output" / "finder" / "finder_method.csv"),
            "output_dir": str(default_base / "output" / "figures" / "cross_sections"),
            "cone_ids": "",
            "dpi": 300,
            "angle_tolerance_deg": 1e-3,
        },
        "dem_overlay": {
            "dem_dir": str(default_base / "output" / "generator" / "dem" / "cropped"),
            "gpkg_path": str(default_base / "db" / "database.gpkg"),
            "output_dir": str(default_base / "output" / "figures" / "dem_overlay"),
            "cone_ids": "",
            "use_manual_fix": False,
            "dpi": 220,
            "azimuth_deg": 315,
            "altitude_deg": 45,
            "centers_hybrid_path": str(
                default_base / "output" / "analyzer" / "shapes" / "centers_hybrid.gpkg"
            ),
        },
        "dataset_compare": {
            "sources_text": "",
            "colors_text": "",
            "x_metric": "Wco",
            "y_metric": "WCR_WCO_ratio",
            "use_manual_fix": False,
            "embedding_method": "PCA",
            "embedding_level": "Dataset level",
            "scatter_point_size": 28,
            "scatter_marker": "o",
            "embedding_point_size": 90,
            "embedding_marker": "o",
            "show_hulls": False,
            "hull_style": "Fill + outline",
            "hull_alpha": 0.14,
            "show_reference_rows": False,
        },
    }


def load_state(mvp_root: Path) -> dict:
    """Load persisted state and merge it with defaults for backward compatibility."""
    state = default_state(mvp_root)
    defaults = default_state(mvp_root)
    state_path = mvp_root / STATE_FILE_NAME
    if not state_path.exists():
        return state

    try:
        with open(state_path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return state

    _deep_update(state, loaded)
    _resolve_state_paths_in_place(state, mvp_root)
    _fallback_missing_core_paths(state, defaults)
    return state


def save_state(mvp_root: Path, state: dict) -> None:
    """Persist UI state using relative paths when possible."""
    state_path = mvp_root / STATE_FILE_NAME
    portable_state = _make_state_paths_portable(state, mvp_root)
    with open(state_path, "w", encoding="utf-8") as handle:
        json.dump(portable_state, handle, indent=2)


def _deep_update(target: dict, source: dict) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value
