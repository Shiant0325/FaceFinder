from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Iterable, Optional, Sequence, Set

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

DEFAULT_EXCLUDE_DIR_NAMES = {
    "$recycle.bin",
    "system volume information",
    "windows",
    "program files",
    "program files (x86)",
    "programdata",
    "appdata",
    ".git",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "site-packages",
    "__pycache__",
    "output",
    "outputs",
    "findings",
    "matches",
    "downloads",
}


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def is_image_path(path: str | Path, extensions: Optional[Set[str]] = None) -> bool:
    return Path(path).suffix.lower() in (extensions or IMAGE_EXTENSIONS)


def iter_image_files(folder: str | Path) -> Iterable[Path]:
    folder = Path(folder)
    if not folder.exists():
        return
    for root, _, files in os.walk(folder):
        for filename in files:
            path = Path(root) / filename
            if is_image_path(path):
                yield path


def iter_image_files_filtered(
    roots: Sequence[str | Path],
    exclude_dir_names: Optional[Set[str]] = None,
    extensions: Optional[Set[str]] = None,
    min_size_bytes: int = 2048,
    max_files: Optional[int] = None,
) -> Iterable[Path]:
    exclude_names = {x.lower() for x in (exclude_dir_names or DEFAULT_EXCLUDE_DIR_NAMES)}
    extensions = extensions or IMAGE_EXTENSIONS
    yielded = 0

    for root_value in roots:
        root_path = Path(root_value)
        if not root_path.exists():
            continue

        for current_root, dirnames, filenames in os.walk(root_path, topdown=True, followlinks=False):
            dirnames[:] = [d for d in dirnames if d.lower() not in exclude_names]

            for filename in filenames:
                path = Path(current_root) / filename
                if not is_image_path(path, extensions):
                    continue
                try:
                    if min_size_bytes and path.stat().st_size < min_size_bytes:
                        continue
                except OSError:
                    continue

                yield path
                yielded += 1
                if max_files is not None and yielded >= max_files:
                    return


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip()).strip("_")
    return cleaned or "person"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*]+', "_", name).strip() or "file"


def next_finding_folder(base_dir: str | Path) -> Path:
    base = Path(base_dir)
    highest = 0
    pattern = re.compile(r"^Finding\s+(\d+)$", re.IGNORECASE)
    if base.exists() and base.is_dir():
        for child in base.iterdir():
            if child.is_dir():
                match = pattern.match(child.name)
                if match:
                    highest = max(highest, int(match.group(1)))
    return base / f"Finding {highest + 1}"


def read_json(path: str | Path, default):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def write_json(path: str | Path, payload) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_suffix(p.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(p)
