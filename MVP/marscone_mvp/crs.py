"""CRS resolution helpers for MVP runtime configuration."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import rasterio


def resolve_crs(state: dict) -> str:
    """Resolve CRS string from state, using manual value or auto-detection."""
    crs_state = state["crs"]
    if crs_state["mode"] == "manual":
        manual_value = crs_state["manual_value"].strip()
        if not manual_value:
            raise ValueError("Manual CRS is empty.")
        return manual_value

    source = crs_state["source"]
    base_path = Path(state["base_path"])
    detector = {
        "dem": _crs_from_dem,
        "masks": _crs_from_masks,
        "points": _crs_from_points,
    }[source]
    return detector(base_path)


def describe_resolved_crs(state: dict) -> str:
    """Return resolved CRS formatted as one compact single-line string."""
    crs_value = resolve_crs(state)
    compact = " ".join(line.strip() for line in str(crs_value).splitlines() if line.strip())
    return compact


def _crs_from_dem(base_path: Path) -> str:
    dem_dir = base_path / "input" / "dem"
    tif_files = sorted(
        list(dem_dir.glob("*.tif"))
        + list(dem_dir.glob("*.tiff"))
        + list(dem_dir.glob("*.TIF"))
        + list(dem_dir.glob("*.TIFF"))
    )
    if not tif_files:
        raise FileNotFoundError(f"No DEM files found in {dem_dir}")

    with rasterio.open(tif_files[0]) as src:
        if src.crs is None:
            raise ValueError(f"DEM has no CRS: {tif_files[0]}")
        return src.crs.to_wkt()


def _crs_from_masks(base_path: Path) -> str:
    return _crs_from_shapefile(base_path / "input" / "crop")


def _crs_from_points(base_path: Path) -> str:
    return _crs_from_shapefile(base_path / "input" / "points")


def _crs_from_shapefile(folder: Path) -> str:
    shp_files = sorted(folder.glob("*.shp"))
    if not shp_files:
        raise FileNotFoundError(f"No shapefiles found in {folder}")

    gdf = gpd.read_file(shp_files[0])
    if gdf.crs is None:
        raise ValueError(f"Shapefile has no CRS: {shp_files[0]}")
    return gdf.crs.to_wkt()
