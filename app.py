from __future__ import annotations

import os
import sys

from portable_paths import app_root, install_root, model_root

DATA_ROOT = app_root()
INSTALL_ROOT = install_root()
os.environ.setdefault("FACEFINDER_INSTALL_DIR", str(INSTALL_ROOT))
os.environ.setdefault("FACEFINDER_DATA_DIR", str(DATA_ROOT))
os.environ.setdefault("FACEFINDER_MODEL_DIR", str(model_root()))
os.environ.setdefault("INSIGHTFACE_HOME", str(model_root()))

from PySide6.QtWidgets import QApplication

from ui import MainWindow, STYLE_SHEET


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("FaceFinder")
    app.setOrganizationName("FaceFinder")
    app.setStyleSheet(STYLE_SHEET)

    window = MainWindow(DATA_ROOT)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
