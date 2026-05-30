"""Application entrypoint for MarsCONE MVP Qt UI."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from marscone_mvp.main_window import MainWindow


def main() -> int:
    """Create and run the Qt application event loop."""
    app = QApplication(sys.argv)
    mvp_root = Path(__file__).resolve().parent.parent

    icon_candidates = [
        mvp_root / "assets" / "app_icon.icns",
        mvp_root / "assets" / "app_icon.png",
        mvp_root / "assets" / "app_icon.svg",
        mvp_root / "assets" / "app_icon.ico",
    ]
    for icon_path in icon_candidates:
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))
            break

    window = MainWindow(mvp_root)
    window.show()
    return app.exec()
