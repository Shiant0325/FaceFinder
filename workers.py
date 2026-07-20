from __future__ import annotations

import json
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Sequence

from PySide6.QtCore import QThread, Signal

from file_organizer import execute_operations
from storage import connect_db, export_csv, initialize_session, insert_matches, update_session
from utils import DEFAULT_EXCLUDE_DIR_NAMES, ensure_dir, iter_image_files_filtered, write_json


class DeviceTestWorker(QThread):
    completed = Signal(dict)
    failed = Signal(str)

    def __init__(self, device_mode: str, det_size: int = 320):
        super().__init__()
        self.device_mode = device_mode
        self.det_size = det_size

    def run(self) -> None:
        stage = "starting test"
        try:
            stage = "importing FaceEngine"
            from face_engine import FaceEngine

            stage = "loading ONNX Runtime and InsightFace models"
            started = time.perf_counter()
            engine = FaceEngine(
                device_mode=self.device_mode,
                det_size=(self.det_size, self.det_size),
            )

            stage = "collecting provider diagnostics"
            diagnostics = engine.diagnostics()
            diagnostics["load_seconds"] = time.perf_counter() - started

            stage = "running test inference"
            import numpy as np
            inference_started = time.perf_counter()
            engine.get_faces(np.zeros((self.det_size, self.det_size, 3), dtype=np.uint8))
            diagnostics["inference_test"] = "passed"
            diagnostics["inference_seconds"] = time.perf_counter() - inference_started
            self.completed.emit(diagnostics)
        except Exception:
            self.failed.emit(
                f"Stage: {stage}\n"
                f"Mode: {self.device_mode}\n\n"
                f"{traceback.format_exc()}"
            )


class ReferenceWorker(QThread):
    progress = Signal(str)
    completed = Signal(dict)
    failed = Signal(str)

    def __init__(
        self,
        reference_dir: str,
        output_path: str,
        device_mode: str,
        det_size: int,
    ):
        super().__init__()
        self.reference_dir = reference_dir
        self.output_path = output_path
        self.device_mode = device_mode
        self.det_size = det_size

    def run(self) -> None:
        try:
            self.progress.emit("Loading face recognition model...")
            from face_engine import FaceEngine

            engine = FaceEngine(
                device_mode=self.device_mode,
                det_size=(self.det_size, self.det_size),
            )
            self.progress.emit("Detecting faces in reference images...")
            count = engine.build_reference_embedding(self.reference_dir, self.output_path)
            self.completed.emit({
                "count": count,
                "output_path": self.output_path,
                "actual_provider": engine.actual_provider,
                "diagnostics": engine.diagnostics(),
            })
        except Exception as exc:
            self.failed.emit(str(exc))


class ScanWorker(QThread):
    status = Signal(str)
    provider_ready = Signal(dict)
    progress = Signal(dict)
    match_found = Signal(dict)
    completed = Signal(dict)
    failed = Signal(str)

    def __init__(
        self,
        person: Dict,
        roots: Sequence[str],
        finding_dir: str,
        device_mode: str,
        threshold: float,
        det_size: int,
        min_size_kb: int,
        max_files: int | None,
        extra_exclusions: Sequence[str] | None = None,
    ):
        super().__init__()
        self.person = person
        self.roots = list(roots)
        self.finding_dir = Path(finding_dir)
        self.device_mode = device_mode
        self.threshold = threshold
        self.det_size = det_size
        self.min_size_kb = min_size_kb
        self.max_files = max_files
        self.extra_exclusions = list(extra_exclusions or [])

        self._stop_requested = False
        self._paused = False
        self._condition = threading.Condition()

    def request_stop(self) -> None:
        with self._condition:
            self._stop_requested = True
            self._paused = False
            self._condition.notify_all()

    def pause(self) -> None:
        with self._condition:
            self._paused = True
        self.status.emit("Paused")

    def resume(self) -> None:
        with self._condition:
            self._paused = False
            self._condition.notify_all()
        self.status.emit("Scanning")

    def _wait_if_paused(self) -> bool:
        with self._condition:
            while self._paused and not self._stop_requested:
                self._condition.wait(timeout=0.5)
            return self._stop_requested

    def run(self) -> None:
        conn = None
        scanned_count = 0
        match_count = 0
        error_count = 0
        pending_rows: List[Dict] = []
        started_perf = time.perf_counter()
        started_at = datetime.now().isoformat(timespec="seconds")
        finding_name = self.finding_dir.name

        try:
            ensure_dir(self.finding_dir)
            crops_dir = ensure_dir(self.finding_dir / "matches" / "crops")
            db_path = self.finding_dir / "results.sqlite"
            scan_info_path = self.finding_dir / "scan_info.json"

            self.status.emit("Loading face recognition model...")
            from face_engine import FaceEngine

            engine = FaceEngine(
                device_mode=self.device_mode,
                det_size=(self.det_size, self.det_size),
            )
            reference = engine.load_reference(self.person["embedding_path"])
            self.provider_ready.emit(engine.diagnostics())

            conn = connect_db(db_path)
            session = {
                "finding_name": finding_name,
                "person_id": self.person["id"],
                "person_name": self.person["name"],
                "scan_locations": json.dumps(self.roots),
                "requested_device": self.device_mode,
                "actual_provider": engine.actual_provider,
                "threshold": self.threshold,
                "detector_size": self.det_size,
                "min_size_kb": self.min_size_kb,
                "started_at": started_at,
                "completed_at": None,
                "status": "running",
                "scanned_count": 0,
                "match_count": 0,
                "error_count": 0,
            }
            initialize_session(conn, session)
            write_json(scan_info_path, {
                **session,
                "scan_locations": self.roots,
                "database": str(db_path),
                "matches_directory": str(crops_dir),
                "device_diagnostics": engine.diagnostics(),
            })

            exclusions = set(DEFAULT_EXCLUDE_DIR_NAMES)
            exclusions.update(value.lower() for value in self.extra_exclusions if value)
            exclusions.add(self.finding_dir.parent.name.lower())
            exclusions.add(self.finding_dir.name.lower())
            iterator = iter_image_files_filtered(
                roots=self.roots,
                exclude_dir_names=exclusions,
                min_size_bytes=self.min_size_kb * 1024,
                max_files=self.max_files,
            )

            self.status.emit("Scanning")
            for image_path in iterator:
                if self._stop_requested or self._wait_if_paused():
                    break

                scanned_count += 1
                try:
                    rows = engine.scan_image(
                        reference_embedding=reference,
                        image_path=image_path,
                        threshold=self.threshold,
                        matches_dir=crops_dir,
                        person_id=self.person["id"],
                        person_name=self.person["name"],
                        finding_name=finding_name,
                    )
                except Exception:
                    error_count += 1
                    rows = []

                if rows:
                    ids = insert_matches(conn, rows)
                    for row, match_id in zip(rows, ids):
                        row["id"] = match_id
                        match_count += 1
                        self.match_found.emit(row)

                elapsed = max(0.001, time.perf_counter() - started_perf)
                if scanned_count == 1 or scanned_count % 10 == 0 or rows:
                    payload = {
                        "current_file": str(image_path),
                        "scanned_count": scanned_count,
                        "match_count": match_count,
                        "error_count": error_count,
                        "speed": scanned_count / elapsed,
                        "elapsed_seconds": elapsed,
                    }
                    self.progress.emit(payload)

                if scanned_count % 100 == 0:
                    update_session(
                        conn,
                        scanned_count=scanned_count,
                        match_count=match_count,
                        error_count=error_count,
                    )

            final_status = "stopped" if self._stop_requested else "completed"
            completed_at = datetime.now().isoformat(timespec="seconds")
            update_session(
                conn,
                completed_at=completed_at,
                status=final_status,
                scanned_count=scanned_count,
                match_count=match_count,
                error_count=error_count,
            )
            info = {
                "finding_name": finding_name,
                "person_id": self.person["id"],
                "person_name": self.person["name"],
                "scan_locations": self.roots,
                "requested_device": self.device_mode,
                "actual_provider": engine.actual_provider,
                "threshold": self.threshold,
                "detector_size": self.det_size,
                "min_size_kb": self.min_size_kb,
                "started_at": started_at,
                "completed_at": completed_at,
                "status": final_status,
                "scanned_count": scanned_count,
                "match_count": match_count,
                "error_count": error_count,
                "database": str(db_path),
                "matches_directory": str(crops_dir),
                "device_diagnostics": engine.diagnostics(),
            }
            csv_path = self.finding_dir / "results.csv"
            export_csv(db_path, csv_path)
            info["csv"] = str(csv_path)
            write_json(scan_info_path, info)
            self.completed.emit(info)
        except Exception as exc:
            if conn is not None:
                try:
                    update_session(
                        conn,
                        completed_at=datetime.now().isoformat(timespec="seconds"),
                        status="failed",
                        scanned_count=scanned_count,
                        match_count=match_count,
                        error_count=error_count + 1,
                    )
                except Exception:
                    pass
            self.failed.emit(str(exc))
        finally:
            if conn is not None:
                conn.close()


class FileOperationWorker(QThread):
    completed = Signal(dict)
    failed = Signal(str)

    def __init__(self, db_path: str, operations: List[Dict]):
        super().__init__()
        self.db_path = db_path
        self.operations = operations

    def run(self) -> None:
        try:
            self.completed.emit(execute_operations(self.db_path, self.operations))
        except Exception as exc:
            self.failed.emit(str(exc))
