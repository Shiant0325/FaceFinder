from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from storage import (
    connect_db,
    get_matches_by_ids,
    mark_copy,
    record_file_operation,
    update_paths_after_move,
)
from utils import ensure_dir, safe_filename


def collision_safe_path(destination: Path) -> Path:
    if not destination.exists():
        return destination
    index = 2
    while True:
        candidate = destination.with_name(f"{destination.stem}_{index}{destination.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def root_label(root: str | Path) -> str:
    value = str(root).rstrip("\\/")
    drive = Path(value).drive.replace(":", "")
    if drive:
        return safe_filename(f"Drive_{drive}")
    return safe_filename(Path(value).name or "Root")


def destination_for(
    source: Path,
    destination_root: Path,
    scan_roots: Sequence[str],
    preserve_structure: bool,
    subfolder: str,
) -> Path:
    base = ensure_dir(destination_root / subfolder)
    if not preserve_structure:
        return collision_safe_path(base / source.name)

    for root_value in scan_roots:
        root = Path(root_value)
        try:
            relative = source.resolve().relative_to(root.resolve())
            return collision_safe_path(base / root_label(root) / relative)
        except (ValueError, OSError):
            continue
    return collision_safe_path(base / "Other" / source.name)


def preview_operations(
    db_path: str | Path,
    match_ids: Sequence[int],
    destination_root: str | Path,
    mode: str,
    scan_roots: Sequence[str],
    preserve_structure: bool,
    include_crops: bool,
) -> List[Dict]:
    conn = connect_db(db_path)
    try:
        matches = get_matches_by_ids(conn, match_ids)
    finally:
        conn.close()

    operations: List[Dict] = []
    original_groups: Dict[str, List[int]] = {}
    crop_groups: Dict[str, List[int]] = {}
    destination_root = Path(destination_root)
    reserved_destinations: set[str] = set()

    for match in matches:
        original_groups.setdefault(str(match["image_path"]), []).append(int(match["id"]))
        if include_crops:
            crop_groups.setdefault(str(match["crop_path"]), []).append(int(match["id"]))

    def reserve(path: Path) -> Path:
        candidate = path
        index = 2
        while str(candidate).lower() in reserved_destinations:
            candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
            index += 1
        reserved_destinations.add(str(candidate).lower())
        return candidate

    for source_value, grouped_ids in original_groups.items():
        source = Path(source_value)
        destination = reserve(destination_for(
            source, destination_root, scan_roots, preserve_structure, "originals"
        ))
        operations.append({
            "match_ids": grouped_ids,
            "kind": "original",
            "mode": mode,
            "source": str(source),
            "destination": str(destination),
            "exists": source.exists(),
        })

    for source_value, grouped_ids in crop_groups.items():
        source = Path(source_value)
        destination = reserve(destination_for(
            source, destination_root, [], False, "crops"
        ))
        operations.append({
            "match_ids": grouped_ids,
            "kind": "crop",
            "mode": mode,
            "source": str(source),
            "destination": str(destination),
            "exists": source.exists(),
        })
    return operations


def execute_operations(db_path: str | Path, operations: Iterable[Dict]) -> Dict[str, int]:
    conn = connect_db(db_path)
    stats = {"success": 0, "missing": 0, "failed": 0}
    try:
        for operation in operations:
            source = Path(operation["source"])
            destination = Path(operation["destination"])
            if destination.exists():
                destination = collision_safe_path(destination)
                operation["destination"] = str(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            match_ids = [int(value) for value in operation.get("match_ids", [])]
            mode = operation["mode"].lower()
            kind = operation["kind"]

            if not source.exists():
                stats["missing"] += 1
                for match_id in match_ids:
                    record_file_operation(
                        conn, match_id, mode, str(source), str(destination), "missing",
                        "Source file does not exist."
                    )
                continue

            try:
                if mode == "move":
                    shutil.move(str(source), str(destination))
                    update_paths_after_move(
                        conn,
                        str(source),
                        str(destination),
                        "image_path" if kind == "original" else "crop_path",
                        "move",
                    )
                else:
                    shutil.copy2(source, destination)
                    for match_id in match_ids:
                        mark_copy(conn, match_id, str(destination))

                for match_id in match_ids:
                    record_file_operation(conn, match_id, mode, str(source), str(destination), "success")
                stats["success"] += 1
            except Exception as exc:
                for match_id in match_ids:
                    record_file_operation(
                        conn, match_id, mode, str(source), str(destination), "failed", str(exc)
                    )
                stats["failed"] += 1
        conn.commit()
        return stats
    finally:
        conn.close()

