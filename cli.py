from __future__ import annotations

import argparse
import json
from pathlib import Path

from file_organizer import execute_operations, preview_operations
from storage import connect_db, export_csv
from utils import read_json


def all_match_ids(db_path: str | Path, review_status: str | None = None) -> list[int]:
    conn = connect_db(db_path)
    try:
        if review_status:
            rows = conn.execute(
                "SELECT id FROM matches WHERE review_status=? ORDER BY id",
                (review_status,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT id FROM matches ORDER BY id").fetchall()
        return [int(row[0]) for row in rows]
    finally:
        conn.close()


def cmd_organize(args) -> None:
    db_path = Path(args.db).resolve()
    finding_dir = db_path.parent
    info = read_json(finding_dir / "scan_info.json", {})
    scan_roots = info.get("scan_locations", [])
    ids = all_match_ids(db_path, args.review_status)
    if not ids:
        print("No matching database rows were found.")
        return

    operations = preview_operations(
        db_path=db_path,
        match_ids=ids,
        destination_root=args.destination,
        mode=args.mode,
        scan_roots=scan_roots,
        preserve_structure=args.preserve_structure,
        include_crops=args.include_crops,
    )

    print(f"Rows selected: {len(ids)}")
    print(f"Unique file operations: {len(operations)}")
    for operation in operations:
        state = "READY" if operation["exists"] else "MISSING"
        print(f"[{state}] {operation['kind']} {operation['source']}")
        print(f"         -> {operation['destination']}")

    if args.dry_run:
        print("\nDry run only. No files were changed.")
        return

    if args.mode == "move" and not args.yes:
        confirmation = input("\nMOVE removes originals from source locations. Type MOVE to continue: ")
        if confirmation.strip() != "MOVE":
            print("Cancelled.")
            return

    stats = execute_operations(db_path, operations)
    print("\nComplete:")
    print(json.dumps(stats, indent=2))


def cmd_export(args) -> None:
    count = export_csv(args.db, args.csv)
    print(f"Exported {count} rows to {args.csv}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FaceFinder PC utility commands")
    sub = parser.add_subparsers(dest="command", required=True)

    organize = sub.add_parser("organize-results", help="Copy or move all matched original images")
    organize.add_argument("--db", required=True, help="Path to a Finding N/results.sqlite database")
    organize.add_argument("--destination", required=True, help="Custom destination folder")
    organize.add_argument("--mode", choices=["copy", "move"], default="copy")
    organize.add_argument(
        "--review-status",
        choices=["Unreviewed", "Confirmed", "False Match"],
        help="Optionally process only one review status",
    )
    organize.add_argument("--preserve-structure", action="store_true")
    organize.add_argument("--include-crops", action="store_true")
    organize.add_argument("--dry-run", action="store_true")
    organize.add_argument("--yes", action="store_true", help="Skip the MOVE text confirmation")
    organize.set_defaults(func=cmd_organize)

    export = sub.add_parser("export-csv", help="Export a Finding database to CSV")
    export.add_argument("--db", required=True)
    export.add_argument("--csv", required=True)
    export.set_defaults(func=cmd_export)
    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    arguments.func(arguments)
