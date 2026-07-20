from __future__ import annotations

import os
import sys
from pathlib import Path


def install_root() -> Path:
    """Return the read-only application installation directory."""
    override = os.getenv("FACEFINDER_INSTALL_DIR")
    if override:
        return Path(override).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def app_root() -> Path:
    """Return the writable per-user data directory.

    Portable/source launches default to the installation folder. The installed
    edition sets FACEFINDER_DATA_DIR to LocalAppData\\FaceFinder.
    """
    override = os.getenv("FACEFINDER_DATA_DIR") or os.getenv("FACEFINDER_APP_DIR")
    if override:
        path = Path(override).resolve()
    else:
        path = install_root()
    path.mkdir(parents=True, exist_ok=True)
    return path


def runtime_root() -> Path:
    return install_root() / "runtime"


def model_root() -> Path:
    override = os.getenv("FACEFINDER_MODEL_DIR")
    path = Path(override).resolve() if override else install_root() / "data" / "insightface"
    path.mkdir(parents=True, exist_ok=True)
    return path
