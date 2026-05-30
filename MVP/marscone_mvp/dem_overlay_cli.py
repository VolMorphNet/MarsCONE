"""CLI entrypoint for DEM overlay figure generation."""

# pylint: disable=duplicate-code

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from marscone_mvp.dem_overlay import DemOverlayConfig, run_dem_overlays


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the DEM overlay CLI."""
    parser = argparse.ArgumentParser(
        description="Generate DEM hillshade overlays with points and transects from GeoPackage."
    )
    parser.add_argument("--dem-dir", required=True)
    parser.add_argument("--gpkg-path", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--cone-ids", default="")
    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument("--azimuth", type=float, default=315.0)
    parser.add_argument("--altitude", type=float, default=45.0)
    parser.add_argument("--centers-hybrid-path", default="")
    parser.add_argument("--use-manual-fix", action="store_true")
    return parser.parse_args()


def main() -> int:
    """Run DEM overlay generation and return process exit code."""
    args = parse_args()

    raw = args.cone_ids.strip().lower()
    if raw in {"", "all", "*"}:
        cone_ids = []
    else:
        cone_ids = [item.strip() for item in args.cone_ids.split(",") if item.strip()]

    config = DemOverlayConfig(
        dem_dir=Path(args.dem_dir),
        gpkg_path=Path(args.gpkg_path),
        output_dir=Path(args.output_dir),
        selected_cone_ids=cone_ids,
        dpi=args.dpi,
        azimuth_deg=args.azimuth,
        altitude_deg=args.altitude,
        centers_hybrid_path=Path(args.centers_hybrid_path) if args.centers_hybrid_path else None,
        use_manual_fix_metrics=bool(args.use_manual_fix),
    )

    try:
        run_dem_overlays(config, log=print)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"DEM overlay generation failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
