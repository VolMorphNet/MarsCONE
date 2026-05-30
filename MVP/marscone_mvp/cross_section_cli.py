"""CLI entrypoint for generating cross-section plots and metrics."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from marscone_mvp.cross_section import CrossSectionConfig, run_cross_sections


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the cross-section CLI."""
    parser = argparse.ArgumentParser(description="Generate cross-section plots and metrics.")
    parser.add_argument("--profile-dir", required=True)
    parser.add_argument("--finder-path", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--cone-ids", default="")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--angle-tolerance", type=float, default=1e-3)
    return parser.parse_args()


def main() -> int:
    """Run cross-section generation and return process exit code."""
    args = parse_args()

    raw = args.cone_ids.strip().lower()
    if raw in {"", "all", "*"}:
        cone_ids = []
    else:
        cone_ids = [item.strip() for item in args.cone_ids.split(",") if item.strip()]

    config = CrossSectionConfig(
        profile_dir=Path(args.profile_dir),
        finder_path=Path(args.finder_path),
        output_dir=Path(args.output_dir),
        selected_cone_ids=cone_ids,
        dpi=args.dpi,
        angle_pair_tolerance_deg=args.angle_tolerance,
    )

    try:
        run_cross_sections(config, log=print)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"Cross-section generation failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
