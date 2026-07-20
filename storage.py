from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_session (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    finding_name TEXT NOT NULL,
    person_id TEXT NOT NULL,
    person_name TEXT NOT NULL,
    scan_locations TEXT NOT NULL,
    requested_device TEXT NOT NULL,
    actual_provider TEXT,
    threshold REAL NOT NULL,
    detector_size INTEGER NOT NULL,
    min_size_kb INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    scanned_count INTEGER NOT NULL DEFAULT 0,
    match_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    person_id TEXT NOT NULL,
    person_name TEXT NOT NULL,
    finding_name TEXT NOT NULL,
    original_image_path TEXT NOT NULL,
    image_path TEXT NOT NULL,
    crop_path TEXT NOT NULL,
    similarity REAL NOT NULL,
    threshold REAL NOT NULL,
    face_bbox TEXT,
    image_hash TEXT,
    review_status TEXT NOT NULL DEFAULT 'Unreviewed',
    last_action TEXT,
    last_destination_path TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS file_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER,
    operation TEXT NOT NULL,
    source_path TEXT NOT NULL,
    destination_path TEXT NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(match_id) REFERENCES matches(id)
);

CREATE INDEX IF NOT EXISTS idx_matches_similarity ON matches(similarity DESC);
CREATE INDEX IF NOT EXISTS idx_matches_image_path ON matches(image_path);
CREATE INDEX IF NOT EXISTS idx_matches_review_status ON matches(review_status);
"""


def connect_db(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def initialize_session(conn: sqlite3.Connection, session: Dict) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO scan_session (
            id, finding_name, person_id, person_name, scan_locations,
            requested_device, actual_provider, threshold, detector_size,
            min_size_kb, started_at, completed_at, status,
            scanned_count, match_count, error_count
        ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session["finding_name"], session["person_id"], session["person_name"],
            session["scan_locations"], session["requested_device"], session.get("actual_provider"),
            session["threshold"], session["detector_size"], session["min_size_kb"],
            session["started_at"], session.get("completed_at"), session["status"],
            session.get("scanned_count", 0), session.get("match_count", 0), session.get("error_count", 0),
        ),
    )
    conn.commit()


def update_session(conn: sqlite3.Connection, **values) -> None:
    allowed = {
        "actual_provider", "completed_at", "status", "scanned_count", "match_count", "error_count"
    }
    fields = [(key, value) for key, value in values.items() if key in allowed]
    if not fields:
        return
    sql = "UPDATE scan_session SET " + ", ".join(f"{key}=?" for key, _ in fields) + " WHERE id=1"
    conn.execute(sql, [value for _, value in fields])
    conn.commit()


def insert_matches(conn: sqlite3.Connection, rows: Iterable[Dict]) -> List[int]:
    ids: List[int] = []
    for row in rows:
        cursor = conn.execute(
            """
            INSERT INTO matches (
                person_id, person_name, finding_name, original_image_path,
                image_path, crop_path, similarity, threshold, face_bbox,
                image_hash, review_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["person_id"], row["person_name"], row["finding_name"],
                row["original_image_path"], row["image_path"], row["crop_path"],
                row["similarity"], row["threshold"], row.get("face_bbox"),
                row.get("image_hash"), row.get("review_status", "Unreviewed"),
            ),
        )
        ids.append(int(cursor.lastrowid))
    conn.commit()
    return ids


def list_matches(db_path: str | Path, review_status: str | None = None) -> List[Dict]:
    conn = connect_db(db_path)
    try:
        if review_status and review_status != "All":
            rows = conn.execute(
                "SELECT * FROM matches WHERE review_status=? ORDER BY similarity DESC, id DESC",
                (review_status,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM matches ORDER BY similarity DESC, id DESC").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_matches_by_ids(conn: sqlite3.Connection, match_ids: Sequence[int]) -> List[Dict]:
    if not match_ids:
        return []
    placeholders = ",".join("?" for _ in match_ids)
    rows = conn.execute(
        f"SELECT * FROM matches WHERE id IN ({placeholders}) ORDER BY id",
        list(match_ids),
    ).fetchall()
    return [dict(row) for row in rows]


def set_review_status(db_path: str | Path, match_ids: Sequence[int], status: str) -> None:
    if not match_ids:
        return
    conn = connect_db(db_path)
    try:
        placeholders = ",".join("?" for _ in match_ids)
        conn.execute(
            f"UPDATE matches SET review_status=?, updated_at=CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
            [status, *match_ids],
        )
        conn.commit()
    finally:
        conn.close()


def record_file_operation(
    conn: sqlite3.Connection,
    match_id: int,
    operation: str,
    source_path: str,
    destination_path: str,
    status: str,
    error_message: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO file_operations (
            match_id, operation, source_path, destination_path, status, error_message
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (match_id, operation, source_path, destination_path, status, error_message),
    )


def update_paths_after_move(
    conn: sqlite3.Connection,
    old_path: str,
    new_path: str,
    path_column: str,
    operation: str,
) -> None:
    if path_column not in {"image_path", "crop_path"}:
        raise ValueError("Unsupported path column.")
    conn.execute(
        f"""
        UPDATE matches
        SET {path_column}=?, last_action=?, last_destination_path=?, updated_at=CURRENT_TIMESTAMP
        WHERE {path_column}=?
        """,
        (new_path, operation, new_path, old_path),
    )


def mark_copy(conn: sqlite3.Connection, match_id: int, destination_path: str) -> None:
    conn.execute(
        """
        UPDATE matches
        SET last_action='copy', last_destination_path=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
        """,
        (destination_path, match_id),
    )


def export_csv(db_path: str | Path, csv_path: str | Path) -> int:
    conn = connect_db(db_path)
    try:
        rows = conn.execute(
            """
            SELECT id, created_at, person_name, similarity, threshold, review_status,
                   original_image_path, image_path, crop_path, last_action,
                   last_destination_path, image_hash, face_bbox
            FROM matches
            ORDER BY similarity DESC, id DESC
            """
        ).fetchall()
        headers = [column[0] for column in conn.execute(
            """
            SELECT id, created_at, person_name, similarity, threshold, review_status,
                   original_image_path, image_path, crop_path, last_action,
                   last_destination_path, image_hash, face_bbox
            FROM matches LIMIT 0
            """
        ).description]
        path = Path(csv_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            writer.writerows(rows)
        return len(rows)
    finally:
        conn.close()
