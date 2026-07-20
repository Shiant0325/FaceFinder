from __future__ import annotations

import ctypes
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

INSTALL_ROOT = Path(__file__).resolve().parent
if str(INSTALL_ROOT) not in sys.path:
    sys.path.insert(0, str(INSTALL_ROOT))
os.chdir(INSTALL_ROOT)

local_app_data = Path(os.getenv("LOCALAPPDATA", str(INSTALL_ROOT)))
data_root = local_app_data / "FaceFinder"
data_root.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("FACEFINDER_INSTALL_DIR", str(INSTALL_ROOT))
os.environ.setdefault("FACEFINDER_DATA_DIR", str(data_root))
os.environ.setdefault("FACEFINDER_MODEL_DIR", str(INSTALL_ROOT / "data" / "insightface"))
os.environ.setdefault("INSIGHTFACE_HOME", str(INSTALL_ROOT / "data" / "insightface"))


def show_error(message: str) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(0, message, "FaceFinder Error", 0x10)
    except Exception:
        pass


try:
    from app import main

    raise SystemExit(main())
except SystemExit:
    raise
except Exception:
    crash_dir = data_root / "logs"
    crash_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = crash_dir / f"crash_{stamp}.log"
    details = traceback.format_exc()
    log_path.write_text(details, encoding="utf-8")
    show_error(
        "FaceFinder could not start.\n\n"
        f"A diagnostic log was saved here:\n{log_path}\n\n"
        "Run FaceFinder Diagnostics from the Start Menu for the full console error."
    )
    raise
