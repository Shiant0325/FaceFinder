from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, QUrl, QSize
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QStackedWidget,
    QScrollArea,
    QSizePolicy,
)

from device_monitor import get_system_metrics
from portable_paths import install_root
from file_organizer import preview_operations
from person_store import PersonStore
from settings_store import SettingsStore
from storage import export_csv, list_matches, set_review_status
from utils import next_finding_folder, read_json
from workers import DeviceTestWorker, FileOperationWorker, ReferenceWorker, ScanWorker




def make_combo_box() -> QComboBox:
    """Create a combo box whose popup remains readable on Windows/Qt themes."""
    combo = QComboBox()
    combo.setMaxVisibleItems(12)
    combo.setMinimumHeight(40)
    combo.view().setTextElideMode(Qt.TextElideMode.ElideRight)
    combo.view().setStyleSheet(
        "QAbstractItemView { background: #FFFFFF; color: #0F172A; "
        "border: 1px solid #CBD5E1; outline: 0; padding: 4px; }"
        "QAbstractItemView::item { color: #0F172A; background: #FFFFFF; "
        "min-height: 30px; padding: 6px 10px; }"
        "QAbstractItemView::item:hover, QAbstractItemView::item:selected { "
        "background: #E8F0FF; color: #0F172A; }"
    )
    return combo


def configure_form(form: QFormLayout) -> None:
    """Keep labels visible and fields usable at narrow window widths."""
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    form.setFormAlignment(Qt.AlignmentFlag.AlignTop)


def configure_spin_box(spin: QAbstractSpinBox) -> None:
    """Avoid clipped native stepper buttons seen on some Windows scale factors."""
    spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    spin.setMinimumHeight(40)


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def reveal_path(path_value: str, select_file: bool = False) -> None:
    path = Path(path_value)
    if sys.platform.startswith("win"):
        try:
            if select_file and path.exists():
                subprocess.Popen(["explorer", "/select,", str(path)])
            else:
                os.startfile(str(path if path.is_dir() else path.parent))  # type: ignore[attr-defined]
            return
        except Exception:
            pass
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path if path.is_dir() else path.parent)))


def open_file(path_value: str) -> None:
    path = Path(path_value)
    if not path.exists():
        QMessageBox.warning(None, "File Missing", f"The file no longer exists:\n{path}")
        return
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def set_button_role(button: QPushButton, role: str) -> QPushButton:
    button.setProperty("role", role)
    button.style().unpolish(button)
    button.style().polish(button)
    return button


def make_card(object_name: str = "card") -> QFrame:
    card = QFrame()
    card.setObjectName(object_name)
    return card


class DashboardPage(QWidget):
    def __init__(self, main_window: "MainWindow"):
        super().__init__()
        self.main_window = main_window

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        hero = make_card("heroCard")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(26, 22, 26, 22)
        hero_text = QVBoxLayout()
        title = QLabel("Find the photos that matter")
        title.setObjectName("heroTitle")
        subtitle = QLabel(
            "Create a reference profile, scan selected PC locations, review face matches, "
            "then copy or move the confirmed originals safely."
        )
        subtitle.setObjectName("heroSubtitle")
        subtitle.setWordWrap(True)
        hero_text.addWidget(title)
        hero_text.addWidget(subtitle)
        hero_text.addStretch()
        hero_layout.addLayout(hero_text, 1)
        start = set_button_role(QPushButton("Start a new scan"), "primary")
        start.setMinimumWidth(170)
        start.clicked.connect(lambda: main_window.switch_page(2))
        hero_layout.addWidget(start, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(hero)

        stats = QHBoxLayout()
        stats.setSpacing(14)
        self.people_value = self._stat_card(stats, "Reference people", "0", "Profiles ready for matching", "blue")
        self.runs_value = self._stat_card(stats, "Finding runs", "0", "Separate saved scan sessions", "violet")
        self.matches_value = self._stat_card(stats, "Total matches", "0", "Across completed findings", "green")
        self.engine_value = self._stat_card(stats, "Processing engine", "Ready", "GPU-first with CPU fallback", "amber")
        root.addLayout(stats)

        lower = QHBoxLayout()
        lower.setSpacing(14)

        quick = make_card()
        quick_layout = QVBoxLayout(quick)
        quick_layout.setContentsMargins(22, 20, 22, 20)
        quick_title = QLabel("Quick actions")
        quick_title.setObjectName("cardTitle")
        quick_layout.addWidget(quick_title)
        quick_layout.addWidget(QLabel("Everything needed for the complete workflow."))
        add_person = set_button_role(QPushButton("Add a reference person"), "secondary")
        new_scan = set_button_role(QPushButton("Configure a new scan"), "secondary")
        review = set_button_role(QPushButton("Review saved findings"), "secondary")
        hardware = set_button_role(QPushButton("Check CPU / GPU setup"), "secondary")
        add_person.clicked.connect(lambda: main_window.switch_page(1))
        new_scan.clicked.connect(lambda: main_window.switch_page(2))
        review.clicked.connect(lambda: main_window.switch_page(3))
        hardware.clicked.connect(lambda: main_window.switch_page(4))
        for button in (add_person, new_scan, review, hardware):
            button.setMinimumHeight(42)
            quick_layout.addWidget(button)
        quick_layout.addStretch()
        lower.addWidget(quick, 1)

        recent = make_card()
        recent_layout = QVBoxLayout(recent)
        recent_layout.setContentsMargins(22, 20, 22, 20)
        recent_title = QLabel("Recent finding runs")
        recent_title.setObjectName("cardTitle")
        recent_layout.addWidget(recent_title)
        self.recent_list = QListWidget()
        self.recent_list.setObjectName("recentList")
        self.recent_list.setMinimumHeight(220)
        recent_layout.addWidget(self.recent_list, 1)
        lower.addWidget(recent, 2)
        root.addLayout(lower, 1)

        self.refresh()

    def _stat_card(self, target: QHBoxLayout, label: str, value: str, caption: str, accent: str) -> QLabel:
        card = make_card("statCard")
        card.setProperty("accent", accent)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        label_widget = QLabel(label.upper())
        label_widget.setObjectName("statLabel")
        value_widget = QLabel(value)
        value_widget.setObjectName("statValue")
        caption_widget = QLabel(caption)
        caption_widget.setObjectName("statCaption")
        caption_widget.setWordWrap(True)
        layout.addWidget(label_widget)
        layout.addWidget(value_widget)
        layout.addWidget(caption_widget)
        target.addWidget(card, 1)
        return value_widget

    def refresh(self) -> None:
        people = self.main_window.person_store.list_people()
        base = Path(self.main_window.settings.get("output_base") or self.main_window.app_dir / "Findings")
        runs = []
        total_matches = 0
        if base.exists():
            runs = [p for p in base.iterdir() if p.is_dir() and p.name.lower().startswith("finding ")]
            runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            for folder in runs:
                info = read_json(folder / "scan_info.json", {})
                try:
                    total_matches += int(info.get("match_count", 0) or 0)
                except (TypeError, ValueError):
                    pass
        self.people_value.setText(str(len(people)))
        self.runs_value.setText(str(len(runs)))
        self.matches_value.setText(str(total_matches))
        provider = getattr(self.main_window, "current_provider", "Not initialized")
        self.engine_value.setText("GPU" if provider == "CUDAExecutionProvider" else ("CPU" if provider == "CPUExecutionProvider" else "Ready"))

        self.recent_list.clear()
        if not runs:
            item = QListWidgetItem("No scan runs yet\nYour first completed run will appear here.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.recent_list.addItem(item)
            return
        for folder in runs[:6]:
            info = read_json(folder / "scan_info.json", {})
            status = str(info.get("status", "Unknown")).title()
            matches = info.get("match_count", 0)
            person = info.get("reference_person", "Reference person")
            self.recent_list.addItem(f"{folder.name}   •   {status}\n{person}   ·   {matches} matches")


class SetupWizard(QDialog):
    def __init__(self, main_window: "MainWindow"):
        super().__init__(main_window)
        self.main_window = main_window
        self.worker: Optional[DeviceTestWorker] = None
        self.setWindowTitle("FaceFinder setup")
        self.setModal(True)
        self.resize(790, 590)
        self.setObjectName("setupDialog")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        banner = QFrame()
        banner.setObjectName("setupBanner")
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(26, 22, 26, 22)
        badge = QLabel("FF")
        badge.setObjectName("setupBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(52, 52)
        banner_layout.addWidget(badge)
        banner_text = QVBoxLayout()
        title = QLabel("Set up processing")
        title.setObjectName("setupTitle")
        subtitle = QLabel("Choose how FaceFinder should use your hardware. Automatic mode is recommended.")
        subtitle.setObjectName("setupSubtitle")
        subtitle.setWordWrap(True)
        banner_text.addWidget(title)
        banner_text.addWidget(subtitle)
        banner_layout.addLayout(banner_text, 1)
        root.addWidget(banner)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(26, 22, 26, 22)
        body_layout.setSpacing(16)

        mode_card = make_card()
        mode_layout = QVBoxLayout(mode_card)
        mode_layout.setContentsMargins(20, 18, 20, 18)
        mode_title = QLabel("Processing mode")
        mode_title.setObjectName("cardTitle")
        mode_layout.addWidget(mode_title)
        mode_layout.addWidget(QLabel("GPU-first uses NVIDIA CUDA when it is genuinely active and falls back to CPU only if needed."))
        self.mode_combo = make_combo_box()
        self.mode_combo.addItem("Automatic — GPU first, CPU fallback", "auto")
        self.mode_combo.addItem("NVIDIA GPU only — CUDA required", "gpu")
        self.mode_combo.addItem("CPU only", "cpu")
        index = self.mode_combo.findData(self.main_window.settings.get("device_mode", "auto"))
        self.mode_combo.setCurrentIndex(max(0, index))
        self.mode_combo.setMinimumHeight(40)
        mode_layout.addWidget(self.mode_combo)
        body_layout.addWidget(mode_card)

        actions = QHBoxLayout()
        self.test_button = set_button_role(QPushButton("Run engine test"), "primary")
        self.gpu_setup_button = set_button_role(QPushButton("Repair GPU runtime"), "secondary")
        self.cpu_setup_button = set_button_role(QPushButton("Switch runtime to CPU"), "secondary")
        for button in (self.test_button, self.gpu_setup_button, self.cpu_setup_button):
            button.setMinimumHeight(40)
            actions.addWidget(button)
        body_layout.addLayout(actions)

        result_card = make_card()
        result_layout = QVBoxLayout(result_card)
        result_layout.setContentsMargins(18, 16, 18, 16)
        result_title = QLabel("Diagnostics")
        result_title.setObjectName("cardTitle")
        result_layout.addWidget(result_title)
        self.output = QPlainTextEdit()
        self.output.setObjectName("diagnosticOutput")
        self.output.setReadOnly(True)
        self.output.setPlainText(
            "Run the engine test to confirm the provider actually used by InsightFace. "
            "The first test can take longer while the model is initialized."
        )
        result_layout.addWidget(self.output, 1)
        body_layout.addWidget(result_card, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        cancel = set_button_role(QPushButton("Cancel"), "secondary")
        save = set_button_role(QPushButton("Save and continue"), "primary")
        cancel.setMinimumWidth(100)
        save.setMinimumWidth(155)
        footer.addWidget(cancel)
        footer.addWidget(save)
        body_layout.addLayout(footer)
        root.addWidget(body, 1)

        self.test_button.clicked.connect(self.run_test)
        self.gpu_setup_button.clicked.connect(lambda: self.main_window.launch_setup_script("gpu"))
        self.cpu_setup_button.clicked.connect(lambda: self.main_window.launch_setup_script("cpu"))
        save.clicked.connect(self.accept_setup)
        cancel.clicked.connect(self.reject)

    def run_test(self) -> None:
        self.test_button.setEnabled(False)
        self.output.setPlainText("Loading ONNX Runtime and InsightFace models...\n")
        self.worker = DeviceTestWorker(self.mode_combo.currentData(), 320)
        self.worker.completed.connect(self.test_completed)
        self.worker.failed.connect(self.test_failed)
        self.worker.start()

    def test_completed(self, diagnostics: Dict) -> None:
        self.test_button.setEnabled(True)
        self.output.setPlainText(json.dumps(diagnostics, indent=2))
        self.main_window.set_actual_provider(diagnostics.get("actual_provider", "Unknown"))

    def test_failed(self, message: str) -> None:
        self.test_button.setEnabled(True)
        self.output.setPlainText(f"Test failed:\n\n{message}")

    def accept_setup(self) -> None:
        mode = self.mode_combo.currentData()
        self.main_window.settings.update(device_mode=mode, setup_completed=True)
        self.main_window.device_page.set_mode(mode)
        self.main_window.scan_page.set_mode(mode)
        self.accept()


class ReferencePage(QWidget):
    def __init__(self, main_window: "MainWindow"):
        super().__init__()
        self.main_window = main_window
        self.store = main_window.person_store
        self.worker: Optional[ReferenceWorker] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        page_header = QHBoxLayout()
        header_text = QVBoxLayout()
        title = QLabel("Build a reference profile")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Create a reusable face profile from several clear photos.")
        subtitle.setObjectName("pageSubtitle")
        header_text.addWidget(title)
        header_text.addWidget(subtitle)
        page_header.addLayout(header_text)
        page_header.addStretch()
        self.add_person_button = set_button_role(QPushButton("+  Add person"), "primary")
        self.add_person_button.setMinimumWidth(135)
        page_header.addWidget(self.add_person_button, 0, Qt.AlignmentFlag.AlignBottom)
        root.addLayout(page_header)

        content = QHBoxLayout()
        content.setSpacing(16)

        people_card = make_card()
        people_card.setMinimumWidth(310)
        people_layout = QVBoxLayout(people_card)
        people_layout.setContentsMargins(18, 18, 18, 18)
        people_title = QLabel("People")
        people_title.setObjectName("cardTitle")
        people_layout.addWidget(people_title)
        self.person_list = QListWidget()
        self.person_list.setObjectName("personList")
        self.person_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.person_list.setSpacing(4)
        people_layout.addWidget(self.person_list, 1)
        self.delete_person_button = set_button_role(QPushButton("Delete selected person"), "dangerGhost")
        people_layout.addWidget(self.delete_person_button)
        content.addWidget(people_card, 1)

        details = QVBoxLayout()
        details.setSpacing(16)

        profile_card = make_card()
        profile_layout = QHBoxLayout(profile_card)
        profile_layout.setContentsMargins(20, 18, 20, 18)
        self.avatar_label = QLabel("?")
        self.avatar_label.setObjectName("avatar")
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_label.setFixedSize(64, 64)
        profile_layout.addWidget(self.avatar_label)
        profile_text = QVBoxLayout()
        self.person_heading = QLabel("Select or add a person")
        self.person_heading.setObjectName("cardTitleLarge")
        self.person_meta = QLabel("Add 3–5 clear photos with varied angles and lighting.")
        self.person_meta.setObjectName("mutedText")
        self.person_meta.setWordWrap(True)
        profile_text.addWidget(self.person_heading)
        profile_text.addWidget(self.person_meta)
        profile_layout.addLayout(profile_text, 1)
        details.addWidget(profile_card)

        images_card = make_card()
        images_layout = QVBoxLayout(images_card)
        images_layout.setContentsMargins(18, 18, 18, 18)
        images_header = QHBoxLayout()
        images_title = QLabel("Reference images")
        images_title.setObjectName("cardTitle")
        self.add_images_button = set_button_role(QPushButton("Add images"), "secondary")
        self.remove_image_button = set_button_role(QPushButton("Remove selected"), "secondary")
        images_header.addWidget(images_title)
        images_header.addStretch()
        images_header.addWidget(self.add_images_button)
        images_header.addWidget(self.remove_image_button)
        images_layout.addLayout(images_header)
        self.image_list = QListWidget()
        self.image_list.setObjectName("imageGallery")
        self.image_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.image_list.setIconSize(QSize(132, 132))
        self.image_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.image_list.setSpacing(12)
        images_layout.addWidget(self.image_list, 1)
        details.addWidget(images_card, 1)

        vector_card = make_card()
        vector_layout = QHBoxLayout(vector_card)
        vector_layout.setContentsMargins(18, 16, 18, 16)
        vector_text = QVBoxLayout()
        vector_title = QLabel("Face vector")
        vector_title.setObjectName("cardTitle")
        self.vector_status = QLabel("No person selected")
        self.vector_status.setObjectName("mutedText")
        vector_text.addWidget(vector_title)
        vector_text.addWidget(self.vector_status)
        self.generate_button = set_button_role(QPushButton("Generate / regenerate vector"), "success")
        vector_layout.addLayout(vector_text, 1)
        vector_layout.addWidget(self.generate_button)
        details.addWidget(vector_card)

        content.addLayout(details, 3)
        root.addLayout(content, 1)

        self.add_person_button.clicked.connect(self.add_person)
        self.delete_person_button.clicked.connect(self.delete_person)
        self.person_list.currentItemChanged.connect(self.person_changed)
        self.add_images_button.clicked.connect(self.add_images)
        self.remove_image_button.clicked.connect(self.remove_image)
        self.generate_button.clicked.connect(self.generate_vector)
        self.refresh()

    def refresh(self, select_id: Optional[str] = None) -> None:
        self.person_list.clear()
        people = self.store.list_people()
        selected_row = -1
        for row, person in enumerate(people):
            state = "Vector Ready" if person["embedding_ready"] else "Vector Missing"
            item = QListWidgetItem(f"{person['name']}\n{state} · {person['reference_count']} photos")
            item.setData(Qt.ItemDataRole.UserRole, person["id"])
            self.person_list.addItem(item)
            if select_id and person["id"] == select_id:
                selected_row = row
        if selected_row >= 0:
            self.person_list.setCurrentRow(selected_row)
        elif self.person_list.count() > 0:
            self.person_list.setCurrentRow(0)
        else:
            self.clear_person_view()
        self.main_window.scan_page.refresh_people()

    def current_person_id(self) -> Optional[str]:
        item = self.person_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def current_person(self) -> Optional[Dict]:
        person_id = self.current_person_id()
        return self.store.get_person(person_id) if person_id else None

    def clear_person_view(self) -> None:
        self.person_heading.setText("Select or add a person")
        if hasattr(self, "avatar_label"):
            self.avatar_label.setText("?")
        if hasattr(self, "person_meta"):
            self.person_meta.setText("Add 3–5 clear photos with varied angles and lighting.")
        self.image_list.clear()
        self.vector_status.setText("No person selected")

    def person_changed(self, current, previous) -> None:
        person = self.current_person()
        if not person:
            self.clear_person_view()
            return
        self.person_heading.setText(person["name"])
        if hasattr(self, "avatar_label"):
            initials = "".join(part[0] for part in person["name"].split()[:2] if part).upper() or "?"
            self.avatar_label.setText(initials)
        self.image_list.clear()
        images = self.store.reference_images(person["id"])
        for image_path in images:
            item = QListWidgetItem(QIcon(str(image_path)), image_path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(image_path))
            self.image_list.addItem(item)
        embedding = Path(person["embedding_path"])
        ready = embedding.exists()
        if hasattr(self, "person_meta"):
            self.person_meta.setText(
                f"{len(images)} reference photos · " + ("Vector ready" if ready else "Vector not generated")
            )
        self.vector_status.setText(
            f"Ready · {embedding.name}" if ready else "Vector has not been generated"
        )

    def add_person(self) -> None:
        name, accepted = QInputDialog.getText(self, "Add Reference Person", "Person name")
        if not accepted or not name.strip():
            return
        try:
            person = self.store.create_person(name)
            self.refresh(person["id"])
        except Exception as exc:
            QMessageBox.critical(self, "Could Not Add Person", str(exc))

    def delete_person(self) -> None:
        person = self.current_person()
        if not person:
            return
        answer = QMessageBox.question(
            self,
            "Delete Person",
            f"Delete {person['name']} and all stored reference images/vector data?",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.store.delete_person(person["id"])
            self.refresh()

    def add_images(self) -> None:
        person = self.current_person()
        if not person:
            QMessageBox.information(self, "Reference Person", "Add or select a person first.")
            return
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Reference Images",
            "",
            "Images (*.jpg *.jpeg *.png *.webp *.bmp)",
        )
        if files:
            self.store.add_reference_images(person["id"], files)
            self.refresh(person["id"])

    def remove_image(self) -> None:
        person = self.current_person()
        item = self.image_list.currentItem()
        if person and item:
            self.store.remove_reference_image(person["id"], item.data(Qt.ItemDataRole.UserRole))
            self.person_changed(None, None)

    def generate_vector(self) -> None:
        person = self.current_person()
        if not person:
            QMessageBox.information(self, "Reference Person", "Add or select a person first.")
            return
        images = self.store.reference_images(person["id"])
        if not images:
            QMessageBox.warning(self, "Reference Images", "Add at least one clear reference image.")
            return

        self.generate_button.setEnabled(False)
        self.vector_status.setText("Generating vector data...")
        self.worker = ReferenceWorker(
            str(self.store.reference_dir(person["id"])),
            str(self.store.embedding_path(person["id"])),
            self.main_window.settings.get("device_mode", "auto"),
            int(self.main_window.settings.get("detector_size", 320)),
        )
        self.worker.progress.connect(self.vector_status.setText)
        self.worker.completed.connect(lambda result: self.vector_completed(person["id"], result))
        self.worker.failed.connect(self.vector_failed)
        self.worker.start()

    def vector_completed(self, person_id: str, result: Dict) -> None:
        self.generate_button.setEnabled(True)
        self.vector_status.setText(
            f"Vector ready · {result['count']} usable photos · {result['actual_provider']}"
        )
        self.main_window.set_actual_provider(result["actual_provider"])
        self.refresh(person_id)

    def vector_failed(self, message: str) -> None:
        self.generate_button.setEnabled(True)
        self.vector_status.setText("Vector generation failed")
        QMessageBox.critical(self, "Vector Generation Failed", message)


class ScanPage(QWidget):
    def __init__(self, main_window: "MainWindow"):
        super().__init__()
        self.main_window = main_window
        self.worker: Optional[ScanWorker] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        header = QVBoxLayout()
        title = QLabel("Configure scan")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Choose a reference person and the exact folders or drives to search.")
        subtitle.setObjectName("pageSubtitle")
        header.addWidget(title)
        header.addWidget(subtitle)
        root.addLayout(header)

        top = QHBoxLayout()
        top.setSpacing(16)

        configuration = make_card()
        configuration_layout = QVBoxLayout(configuration)
        configuration_layout.setContentsMargins(20, 18, 20, 18)
        configuration_layout.addWidget(self._section_label("1  Scan configuration"))
        config_form = QFormLayout()
        configure_form(config_form)
        config_form.setHorizontalSpacing(18)
        config_form.setVerticalSpacing(12)
        self.person_combo = make_combo_box()
        self.device_combo = make_combo_box()
        self.device_combo.addItem("Automatic — GPU first", "auto")
        self.device_combo.addItem("NVIDIA GPU only", "gpu")
        self.device_combo.addItem("CPU only", "cpu")
        self.det_size_combo = make_combo_box()
        self.det_size_combo.addItem("160 — Fast", 160)
        self.det_size_combo.addItem("320 — Balanced", 320)
        self.det_size_combo.addItem("640 — Accurate", 640)
        self.threshold_spin = QDoubleSpinBox()
        configure_spin_box(self.threshold_spin)
        self.threshold_spin.setRange(0.20, 0.95)
        self.threshold_spin.setSingleStep(0.01)
        self.threshold_spin.setDecimals(2)
        self.threshold_spin.setValue(float(main_window.settings.get("threshold", 0.50)))
        self.min_size_spin = QSpinBox()
        configure_spin_box(self.min_size_spin)
        self.min_size_spin.setRange(0, 102400)
        self.min_size_spin.setValue(int(main_window.settings.get("min_size_kb", 8)))
        self.min_size_spin.setSuffix(" KB")
        self.max_files_spin = QSpinBox()
        configure_spin_box(self.max_files_spin)
        self.max_files_spin.setRange(0, 100_000_000)
        self.max_files_spin.setSpecialValueText("No limit")
        self.max_files_spin.setValue(0)
        config_form.addRow("Reference person", self.person_combo)
        config_form.addRow("Processing device", self.device_combo)
        config_form.addRow("Detection preset", self.det_size_combo)
        config_form.addRow("Similarity threshold", self.threshold_spin)
        config_form.addRow("Minimum image size", self.min_size_spin)
        config_form.addRow("Maximum files", self.max_files_spin)
        for field in (
            self.person_combo, self.device_combo, self.det_size_combo,
            self.threshold_spin, self.min_size_spin, self.max_files_spin,
        ):
            label = config_form.labelForField(field)
            if label is not None:
                label.setObjectName("formLabel")
                label.setMinimumWidth(135)
        configuration_layout.addLayout(config_form)
        configuration_layout.addStretch()
        top.addWidget(configuration, 1)

        locations = make_card()
        locations_layout = QVBoxLayout(locations)
        locations_layout.setContentsMargins(20, 18, 20, 18)
        locations_layout.addWidget(self._section_label("2  Locations to scan"))
        hint = QLabel("Add one or more folders or whole drives. Common system and development folders are skipped automatically.")
        hint.setObjectName("mutedText")
        hint.setWordWrap(True)
        locations_layout.addWidget(hint)
        self.locations_list = QListWidget()
        self.locations_list.setObjectName("locationList")
        locations_layout.addWidget(self.locations_list, 1)
        location_buttons = QHBoxLayout()
        self.add_location_button = set_button_role(QPushButton("+  Add folder or drive"), "secondary")
        self.remove_location_button = set_button_role(QPushButton("Remove"), "dangerGhost")
        location_buttons.addWidget(self.add_location_button)
        location_buttons.addWidget(self.remove_location_button)
        location_buttons.addStretch()
        locations_layout.addLayout(location_buttons)
        top.addWidget(locations, 1)
        root.addLayout(top, 1)

        output = make_card()
        output_layout = QGridLayout(output)
        output_layout.setContentsMargins(20, 16, 20, 16)
        output_layout.setHorizontalSpacing(12)
        self.output_edit = QLineEdit()
        default_base = main_window.settings.get("output_base") or str(main_window.app_dir / "Findings")
        self.output_edit.setText(default_base)
        self.output_browse_button = set_button_role(QPushButton("Browse"), "secondary")
        self.next_finding_label = QLabel()
        self.next_finding_label.setObjectName("findingPill")
        output_layout.addWidget(self._section_label("3  Run output"), 0, 0, 1, 3)
        output_layout.addWidget(QLabel("Base location"), 1, 0)
        output_layout.addWidget(self.output_edit, 1, 1)
        output_layout.addWidget(self.output_browse_button, 1, 2)
        output_layout.addWidget(QLabel("Next run"), 2, 0)
        output_layout.addWidget(self.next_finding_label, 2, 1, 1, 2)
        root.addWidget(output)

        live = make_card()
        live_layout = QVBoxLayout(live)
        live_layout.setContentsMargins(20, 16, 20, 18)
        live_header = QHBoxLayout()
        live_header.addWidget(self._section_label("Live scan"))
        live_header.addStretch()
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("statusPill")
        live_header.addWidget(self.status_label)
        live_layout.addLayout(live_header)
        self.provider_label = QLabel("Actual provider: Not initialized")
        self.provider_label.setObjectName("mutedText")
        self.current_file_label = QLabel("Current file: —")
        self.current_file_label.setObjectName("currentFile")
        self.current_file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        live_layout.addWidget(self.provider_label)
        live_layout.addWidget(self.current_file_label)

        metrics = QHBoxLayout()
        self.scanned_label = self._metric_box(metrics, "Scanned", "0")
        self.matches_label = self._metric_box(metrics, "Matches", "0")
        self.errors_label = self._metric_box(metrics, "Errors", "0")
        self.speed_label = self._metric_box(metrics, "Speed", "0.00 images/sec")
        self.elapsed_label = self._metric_box(metrics, "Elapsed", "00:00:00")
        live_layout.addLayout(metrics)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        live_layout.addWidget(self.progress_bar)

        controls = QHBoxLayout()
        self.start_button = set_button_role(QPushButton("Start scan"), "primary")
        self.pause_button = set_button_role(QPushButton("Pause"), "warning")
        self.resume_button = set_button_role(QPushButton("Resume"), "success")
        self.stop_button = set_button_role(QPushButton("Stop"), "danger")
        self.pause_button.setEnabled(False)
        self.resume_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        controls.addWidget(self.start_button)
        controls.addWidget(self.pause_button)
        controls.addWidget(self.resume_button)
        controls.addWidget(self.stop_button)
        controls.addStretch()
        live_layout.addLayout(controls)
        root.addWidget(live)

        self.add_location_button.clicked.connect(self.add_location)
        self.remove_location_button.clicked.connect(self.remove_location)
        self.output_browse_button.clicked.connect(self.browse_output)
        self.output_edit.textChanged.connect(self.update_next_finding)
        self.start_button.clicked.connect(self.start_scan)
        self.pause_button.clicked.connect(self.pause_scan)
        self.resume_button.clicked.connect(self.resume_scan)
        self.stop_button.clicked.connect(self.stop_scan)
        self.device_combo.currentIndexChanged.connect(self.device_changed)
        self.det_size_combo.currentIndexChanged.connect(self.det_size_changed)

        self.refresh_people()
        self.set_mode(main_window.settings.get("device_mode", "auto"))
        det_index = self.det_size_combo.findData(int(main_window.settings.get("detector_size", 320)))
        self.det_size_combo.setCurrentIndex(max(0, det_index))
        self.update_next_finding()

    def _section_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("cardTitle")
        return label

    def _metric_box(self, target: QHBoxLayout, title: str, value: str) -> QLabel:
        box = QFrame()
        box.setObjectName("miniMetric")
        box.setMinimumHeight(76)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)
        title_label = QLabel(title.upper())
        title_label.setObjectName("miniMetricTitle")
        value_label = QLabel(value)
        value_label.setObjectName("miniMetricValue")
        value_label.setMinimumHeight(22)
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        target.addWidget(box, 1)
        return value_label

    def refresh_people(self) -> None:
        current = self.person_combo.currentData()
        self.person_combo.clear()
        for person in self.main_window.person_store.list_people():
            suffix = "" if person["embedding_ready"] else " — vector missing"
            self.person_combo.addItem(person["name"] + suffix, person["id"])
        if current:
            index = self.person_combo.findData(current)
            if index >= 0:
                self.person_combo.setCurrentIndex(index)

    def set_mode(self, mode: str) -> None:
        index = self.device_combo.findData(mode)
        self.device_combo.setCurrentIndex(max(0, index))

    def device_changed(self) -> None:
        self.main_window.settings.set("device_mode", self.device_combo.currentData())
        device_page = getattr(self.main_window, "device_page", None)
        if device_page is not None and hasattr(device_page, "mode_combo"):
            device_page.set_mode(self.device_combo.currentData())

    def det_size_changed(self) -> None:
        self.main_window.settings.set("detector_size", self.det_size_combo.currentData())

    def add_location(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Folder or Drive")
        if folder and not self.find_location(folder):
            self.locations_list.addItem(folder)

    def find_location(self, value: str) -> bool:
        return any(self.locations_list.item(i).text() == value for i in range(self.locations_list.count()))

    def remove_location(self) -> None:
        for item in self.locations_list.selectedItems():
            self.locations_list.takeItem(self.locations_list.row(item))

    def browse_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Findings Base Folder", self.output_edit.text())
        if folder:
            self.output_edit.setText(folder)

    def update_next_finding(self) -> None:
        base = self.output_edit.text().strip()
        if base:
            self.next_finding_label.setText(str(next_finding_folder(base)))
        else:
            self.next_finding_label.setText("Choose an output base location")

    def selected_roots(self) -> List[str]:
        return [self.locations_list.item(i).text() for i in range(self.locations_list.count())]

    def start_scan(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        person_id = self.person_combo.currentData()
        if not person_id:
            QMessageBox.warning(self, "Reference Person", "Add a reference person and generate vector data first.")
            return
        person = self.main_window.person_store.get_person(person_id)
        if not Path(person["embedding_path"]).exists():
            QMessageBox.warning(self, "Face Vector Missing", "Generate face vector data for the selected person first.")
            return
        roots = self.selected_roots()
        if not roots:
            QMessageBox.warning(self, "Scan Locations", "Add at least one folder or drive to scan.")
            return
        base = self.output_edit.text().strip()
        if not base:
            QMessageBox.warning(self, "Output Location", "Choose a base location for findings.")
            return

        finding_dir = next_finding_folder(base)
        self.main_window.settings.update(
            output_base=base,
            device_mode=self.device_combo.currentData(),
            detector_size=self.det_size_combo.currentData(),
            threshold=self.threshold_spin.value(),
            min_size_kb=self.min_size_spin.value(),
        )
        self.main_window.current_finding_dir = finding_dir
        self.main_window.current_db_path = finding_dir / "results.sqlite"
        self.main_window.findings_page.prepare_live_finding(finding_dir)

        self.worker = ScanWorker(
            person=person,
            roots=roots,
            finding_dir=str(finding_dir),
            device_mode=self.device_combo.currentData(),
            threshold=self.threshold_spin.value(),
            det_size=self.det_size_combo.currentData(),
            min_size_kb=self.min_size_spin.value(),
            max_files=self.max_files_spin.value() or None,
            extra_exclusions=[self.main_window.app_dir.name, Path(base).name],
        )
        self.worker.status.connect(self.scan_status)
        self.worker.provider_ready.connect(self.provider_ready)
        self.worker.progress.connect(self.scan_progress)
        self.worker.match_found.connect(self.main_window.findings_page.add_live_match)
        self.worker.completed.connect(self.scan_completed)
        self.worker.failed.connect(self.scan_failed)

        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.resume_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.progress_bar.setRange(0, 0)
        self.worker.start()

    def pause_scan(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.pause()
            self.pause_button.setEnabled(False)
            self.resume_button.setEnabled(True)

    def resume_scan(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.resume()
            self.pause_button.setEnabled(True)
            self.resume_button.setEnabled(False)

    def stop_scan(self) -> None:
        if self.worker and self.worker.isRunning():
            self.status_label.setText("Stopping safely after current image...")
            self.worker.request_stop()
            self.stop_button.setEnabled(False)

    def scan_status(self, value: str) -> None:
        self.status_label.setText(f"Status: {value}")

    def provider_ready(self, diagnostics: Dict) -> None:
        provider = diagnostics.get("actual_provider", "Unknown")
        self.provider_label.setText(f"Actual provider: {provider}")
        self.main_window.set_actual_provider(provider)

    def scan_progress(self, payload: Dict) -> None:
        self.current_file_label.setText(f"Current file: {payload['current_file']}")
        self.scanned_label.setText(f"Scanned: {payload['scanned_count']:,}")
        self.matches_label.setText(f"Matches: {payload['match_count']:,}")
        self.errors_label.setText(f"Errors: {payload['error_count']:,}")
        self.speed_label.setText(f"Speed: {payload['speed']:.2f} images/sec")
        self.elapsed_label.setText(f"Elapsed: {format_duration(payload['elapsed_seconds'])}")

    def scan_completed(self, info: Dict) -> None:
        self.reset_controls()
        self.status_label.setText(f"Status: {info['status'].title()}")
        self.update_next_finding()
        self.main_window.findings_page.refresh_findings(select_name=info["finding_name"])
        QMessageBox.information(
            self,
            "Scan Finished",
            f"{info['finding_name']}\n\n"
            f"Images scanned: {info['scanned_count']:,}\n"
            f"Matches found: {info['match_count']:,}\n"
            f"Errors skipped: {info['error_count']:,}\n"
            f"Status: {info['status']}",
        )

    def scan_failed(self, message: str) -> None:
        self.reset_controls()
        self.status_label.setText("Status: Failed")
        QMessageBox.critical(self, "Scan Failed", message)

    def reset_controls(self) -> None:
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.resume_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)


class FindingsPage(QWidget):
    def __init__(self, main_window: "MainWindow"):
        super().__init__()
        self.main_window = main_window
        self.current_db_path: Optional[Path] = None
        self.current_finding_dir: Optional[Path] = None
        self.file_worker: Optional[FileOperationWorker] = None
        self.preview_cache: List[Dict] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        header = QVBoxLayout()
        title = QLabel("Review and organize matches")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Review cropped matches, confirm the correct ones, then copy or move the original images.")
        subtitle.setObjectName("pageSubtitle")
        header.addWidget(title)
        header.addWidget(subtitle)
        root.addLayout(header)

        toolbar_card = make_card()
        toolbar = QHBoxLayout(toolbar_card)
        toolbar.setContentsMargins(18, 14, 18, 14)
        self.finding_combo = make_combo_box()
        self.finding_combo.setMinimumWidth(320)
        self.filter_combo = make_combo_box()
        self.filter_combo.addItems(["All", "Unreviewed", "Confirmed", "False Match"])
        self.refresh_button = set_button_role(QPushButton("Refresh"), "secondary")
        self.export_button = set_button_role(QPushButton("Export CSV"), "secondary")
        toolbar.addWidget(QLabel("Finding run"))
        toolbar.addWidget(self.finding_combo, 1)
        toolbar.addWidget(QLabel("Filter"))
        toolbar.addWidget(self.filter_combo)
        toolbar.addWidget(self.refresh_button)
        toolbar.addWidget(self.export_button)
        root.addWidget(toolbar_card)

        table_card = make_card()
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(14, 14, 14, 14)
        table_header = QHBoxLayout()
        table_title = QLabel("Matched faces")
        table_title.setObjectName("cardTitle")
        table_header.addWidget(table_title)
        table_header.addStretch()
        self.select_all_button = set_button_role(QPushButton("Select all"), "secondary")
        self.clear_selection_button = set_button_role(QPushButton("Clear"), "secondary")
        self.confirm_button = set_button_role(QPushButton("Confirm"), "success")
        self.false_button = set_button_role(QPushButton("False match"), "dangerGhost")
        self.open_image_button = set_button_role(QPushButton("Open image"), "secondary")
        self.open_folder_button = set_button_role(QPushButton("Open folder"), "secondary")
        for button in (self.select_all_button, self.clear_selection_button, self.confirm_button, self.false_button, self.open_image_button, self.open_folder_button):
            table_header.addWidget(button)
        table_layout.addLayout(table_header)

        self.table = QTableWidget(0, 6)
        self.table.setObjectName("findingsTable")
        self.table.setHorizontalHeaderLabels([
            "Select", "Face crop", "Similarity", "Review status", "Original / current image", "Last action"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(110)
        header_widget = self.table.horizontalHeader()
        header_widget.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header_widget.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header_widget.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header_widget.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header_widget.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header_widget.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        table_layout.addWidget(self.table, 1)
        root.addWidget(table_card, 1)

        organizer = make_card()
        organizer_grid = QGridLayout(organizer)
        organizer_grid.setContentsMargins(20, 16, 20, 16)
        organizer_grid.setHorizontalSpacing(12)
        organizer_title = QLabel("Copy or move selected originals")
        organizer_title.setObjectName("cardTitle")
        self.destination_edit = QLineEdit(main_window.settings.get("last_destination", ""))
        self.destination_button = set_button_role(QPushButton("Browse"), "secondary")
        self.mode_combo = make_combo_box()
        self.mode_combo.addItem("Copy — keep originals", "copy")
        self.mode_combo.addItem("Move — remove originals after success", "move")
        self.preserve_check = QCheckBox("Preserve source folder structure")
        self.preserve_check.setChecked(True)
        self.include_crops_check = QCheckBox("Also process cropped face images")
        self.preview_button = set_button_role(QPushButton("Preview operation"), "secondary")
        self.execute_button = set_button_role(QPushButton("Execute"), "primary")
        organizer_grid.addWidget(organizer_title, 0, 0, 1, 4)
        organizer_grid.addWidget(QLabel("Destination"), 1, 0)
        organizer_grid.addWidget(self.destination_edit, 1, 1, 1, 2)
        organizer_grid.addWidget(self.destination_button, 1, 3)
        organizer_grid.addWidget(QLabel("Operation"), 2, 0)
        organizer_grid.addWidget(self.mode_combo, 2, 1)
        organizer_grid.addWidget(self.preserve_check, 2, 2)
        organizer_grid.addWidget(self.include_crops_check, 2, 3)
        organizer_grid.addWidget(self.preview_button, 3, 2)
        organizer_grid.addWidget(self.execute_button, 3, 3)
        root.addWidget(organizer)

        self.finding_combo.currentIndexChanged.connect(self.load_selected_finding)
        self.filter_combo.currentTextChanged.connect(self.load_matches)
        self.refresh_button.clicked.connect(lambda: self.refresh_findings())
        self.export_button.clicked.connect(self.export_current_csv)
        self.select_all_button.clicked.connect(lambda: self.set_all_checks(True))
        self.clear_selection_button.clicked.connect(lambda: self.set_all_checks(False))
        self.confirm_button.clicked.connect(lambda: self.update_review("Confirmed"))
        self.false_button.clicked.connect(lambda: self.update_review("False Match"))
        self.open_image_button.clicked.connect(self.open_selected_image)
        self.open_folder_button.clicked.connect(self.open_selected_folder)
        self.destination_button.clicked.connect(self.browse_destination)
        self.preview_button.clicked.connect(self.preview_file_action)
        self.execute_button.clicked.connect(self.execute_file_action)
        self.refresh_findings()

    def findings_base(self) -> Path:
        return Path(self.main_window.scan_page.output_edit.text().strip() or self.main_window.app_dir / "Findings")

    def refresh_findings(self, select_name: Optional[str] = None) -> None:
        current_name = select_name or self.finding_combo.currentText()
        self.finding_combo.blockSignals(True)
        self.finding_combo.clear()
        base = self.findings_base()
        folders = []
        if base.exists():
            folders = [p for p in base.iterdir() if p.is_dir() and p.name.lower().startswith("finding ")]
            folders.sort(key=lambda p: int(p.name.split()[-1]) if p.name.split()[-1].isdigit() else 0)
        for folder in folders:
            info = read_json(folder / "scan_info.json", {})
            status = info.get("status", "unknown")
            matches = info.get("match_count", "?")
            self.finding_combo.addItem(f"{folder.name} — {status} — {matches} matches", str(folder))
        self.finding_combo.blockSignals(False)

        if current_name:
            for index in range(self.finding_combo.count()):
                folder = Path(self.finding_combo.itemData(index))
                if folder.name == current_name or self.finding_combo.itemText(index) == current_name:
                    self.finding_combo.setCurrentIndex(index)
                    break
        if self.finding_combo.count():
            self.load_selected_finding()
        else:
            self.current_db_path = None
            self.current_finding_dir = None
            self.table.setRowCount(0)

    def prepare_live_finding(self, finding_dir: Path) -> None:
        self.current_finding_dir = finding_dir
        self.current_db_path = finding_dir / "results.sqlite"
        self.table.setRowCount(0)

    def load_selected_finding(self) -> None:
        value = self.finding_combo.currentData()
        if not value:
            return
        self.current_finding_dir = Path(value)
        self.current_db_path = self.current_finding_dir / "results.sqlite"
        self.load_matches()

    def load_matches(self) -> None:
        self.table.setRowCount(0)
        if not self.current_db_path or not self.current_db_path.exists():
            return
        rows = list_matches(self.current_db_path, self.filter_combo.currentText())
        for row in rows:
            self.append_match_row(row)

    def add_live_match(self, row: Dict) -> None:
        if self.current_db_path == self.main_window.current_db_path:
            self.append_match_row(row, insert_at_top=True)

    def append_match_row(self, match: Dict, insert_at_top: bool = False) -> None:
        row_index = 0 if insert_at_top else self.table.rowCount()
        self.table.insertRow(row_index)

        checkbox = QTableWidgetItem()
        checkbox.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
        checkbox.setCheckState(Qt.CheckState.Unchecked)
        checkbox.setData(Qt.ItemDataRole.UserRole, int(match["id"]))
        self.table.setItem(row_index, 0, checkbox)

        crop_label = QLabel()
        crop_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        crop_path = str(match.get("crop_path", ""))
        pixmap = QPixmap(crop_path)
        if not pixmap.isNull():
            crop_label.setPixmap(pixmap.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            crop_label.setText("Crop missing")
        crop_label.setProperty("crop_path", crop_path)
        self.table.setCellWidget(row_index, 1, crop_label)

        similarity = QTableWidgetItem(f"{float(match['similarity']):.3f}")
        similarity.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row_index, 2, similarity)
        self.table.setItem(row_index, 3, QTableWidgetItem(str(match.get("review_status", "Unreviewed"))))

        original = str(match.get("original_image_path", ""))
        current = str(match.get("image_path", ""))
        path_text = current if original == current else f"Current: {current}\nOriginal: {original}"
        path_item = QTableWidgetItem(path_text)
        path_item.setData(Qt.ItemDataRole.UserRole, current)
        self.table.setItem(row_index, 4, path_item)
        action = match.get("last_action") or "—"
        destination = match.get("last_destination_path")
        self.table.setItem(row_index, 5, QTableWidgetItem(
            f"{action}\n{destination}" if destination else str(action)
        ))

    def checked_ids(self) -> List[int]:
        ids = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                ids.append(int(item.data(Qt.ItemDataRole.UserRole)))
        return ids

    def selected_row(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def set_all_checks(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(state)

    def update_review(self, status: str) -> None:
        ids = self.checked_ids()
        if not ids or not self.current_db_path:
            QMessageBox.information(self, "Select Findings", "Select one or more findings first.")
            return
        set_review_status(self.current_db_path, ids, status)
        self.load_matches()

    def open_selected_image(self) -> None:
        row = self.selected_row()
        if row >= 0:
            open_file(self.table.item(row, 4).data(Qt.ItemDataRole.UserRole))

    def open_selected_folder(self) -> None:
        row = self.selected_row()
        if row >= 0:
            reveal_path(self.table.item(row, 4).data(Qt.ItemDataRole.UserRole), select_file=True)

    def browse_destination(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Copy / Move Destination", self.destination_edit.text())
        if folder:
            self.destination_edit.setText(folder)
            self.main_window.settings.set("last_destination", folder)

    def scan_roots(self) -> List[str]:
        if not self.current_finding_dir:
            return []
        info = read_json(self.current_finding_dir / "scan_info.json", {})
        return info.get("scan_locations", [])

    def preview_file_action(self) -> None:
        self.preview_cache = []
        ids = self.checked_ids()
        destination = self.destination_edit.text().strip()
        if not self.current_db_path or not ids:
            QMessageBox.information(self, "Select Findings", "Select one or more findings first.")
            return
        if not destination:
            QMessageBox.warning(self, "Destination", "Choose a copy/move destination.")
            return
        self.preview_cache = preview_operations(
            self.current_db_path,
            ids,
            destination,
            self.mode_combo.currentData(),
            self.scan_roots(),
            self.preserve_check.isChecked(),
            self.include_crops_check.isChecked(),
        )
        existing = sum(1 for item in self.preview_cache if item["exists"])
        missing = len(self.preview_cache) - existing
        sample = "\n".join(
            f"{item['kind']}: {item['source']}\n  → {item['destination']}"
            for item in self.preview_cache[:6]
        )
        QMessageBox.information(
            self,
            "Operation Preview",
            f"Mode: {self.mode_combo.currentData().upper()}\n"
            f"Files ready: {existing}\nMissing: {missing}\n\n{sample}"
            + ("\n\n…more files omitted" if len(self.preview_cache) > 6 else ""),
        )

    def execute_file_action(self) -> None:
        self.preview_file_action()
        if not self.preview_cache or not self.current_db_path:
            return
        mode = self.mode_combo.currentData()
        if mode == "move":
            question = (
                "MOVE removes files from their original locations.\n\n"
                f"Proceed with {len(self.preview_cache)} planned file operations?"
            )
        else:
            question = f"Proceed with {len(self.preview_cache)} copy operations?"
        if QMessageBox.question(self, "Confirm File Operation", question) != QMessageBox.StandardButton.Yes:
            return

        self.execute_button.setEnabled(False)
        self.file_worker = FileOperationWorker(str(self.current_db_path), self.preview_cache)
        self.file_worker.completed.connect(self.file_action_completed)
        self.file_worker.failed.connect(self.file_action_failed)
        self.file_worker.start()

    def file_action_completed(self, stats: Dict) -> None:
        self.execute_button.setEnabled(True)
        self.load_matches()
        QMessageBox.information(
            self,
            "File Operation Complete",
            f"Successful: {stats['success']}\nMissing: {stats['missing']}\nFailed: {stats['failed']}",
        )

    def file_action_failed(self, message: str) -> None:
        self.execute_button.setEnabled(True)
        QMessageBox.critical(self, "File Operation Failed", message)

    def export_current_csv(self) -> None:
        if not self.current_db_path or not self.current_db_path.exists():
            return
        default = str(self.current_finding_dir / "results.csv") if self.current_finding_dir else "results.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Export Findings CSV", default, "CSV Files (*.csv)")
        if path:
            count = export_csv(self.current_db_path, path)
            QMessageBox.information(self, "CSV Export", f"Exported {count} rows to:\n{path}")


class DeviceSetupPage(QWidget):
    def __init__(self, main_window: "MainWindow"):
        super().__init__()
        self.main_window = main_window
        self.worker: Optional[DeviceTestWorker] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        title = QLabel("Processing hardware")
        title.setObjectName("pageTitle")
        subtitle = QLabel("Confirm the provider actually used by every InsightFace model and repair only the private portable runtime when needed.")
        subtitle.setObjectName("pageSubtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        cards = QHBoxLayout()
        cards.setSpacing(16)
        mode_card = make_card()
        mode_layout = QVBoxLayout(mode_card)
        mode_layout.setContentsMargins(22, 20, 22, 20)
        mode_title = QLabel("Default processing mode")
        mode_title.setObjectName("cardTitle")
        mode_layout.addWidget(mode_title)
        mode_layout.addWidget(QLabel("Automatic is recommended for portable use across different PCs."))
        self.mode_combo = make_combo_box()
        self.mode_combo.addItem("Automatic — GPU first, CPU fallback", "auto")
        self.mode_combo.addItem("NVIDIA GPU only — CUDA required", "gpu")
        self.mode_combo.addItem("CPU only", "cpu")
        self.mode_combo.setMinimumHeight(42)
        mode_layout.addWidget(self.mode_combo)
        mode_layout.addStretch()
        cards.addWidget(mode_card, 1)

        action_card = make_card()
        action_layout = QVBoxLayout(action_card)
        action_layout.setContentsMargins(22, 20, 22, 20)
        action_title = QLabel("Runtime tools")
        action_title.setObjectName("cardTitle")
        action_layout.addWidget(action_title)
        self.test_button = set_button_role(QPushButton("Run complete engine test"), "primary")
        self.gpu_setup_button = set_button_role(QPushButton("Repair portable GPU runtime"), "secondary")
        self.cpu_setup_button = set_button_role(QPushButton("Switch portable runtime to CPU"), "secondary")
        for button in (self.test_button, self.gpu_setup_button, self.cpu_setup_button):
            button.setMinimumHeight(42)
            action_layout.addWidget(button)
        cards.addWidget(action_card, 1)
        root.addLayout(cards)

        diagnostics_card = make_card()
        diagnostics_layout = QVBoxLayout(diagnostics_card)
        diagnostics_layout.setContentsMargins(20, 18, 20, 18)
        diagnostics_title = QLabel("Engine diagnostics")
        diagnostics_title.setObjectName("cardTitle")
        diagnostics_layout.addWidget(diagnostics_title)
        self.diagnostics = QPlainTextEdit()
        self.diagnostics.setObjectName("diagnosticOutput")
        self.diagnostics.setReadOnly(True)
        self.diagnostics.setPlainText("Run the test to confirm the actual execution provider used by the loaded InsightFace models.")
        diagnostics_layout.addWidget(self.diagnostics, 1)
        root.addWidget(diagnostics_card, 1)

        self.mode_combo.currentIndexChanged.connect(self.mode_changed)
        self.test_button.clicked.connect(self.run_test)
        self.gpu_setup_button.clicked.connect(lambda: self.main_window.launch_setup_script("gpu"))
        self.cpu_setup_button.clicked.connect(lambda: self.main_window.launch_setup_script("cpu"))
        self.set_mode(main_window.settings.get("device_mode", "auto"))

    def set_mode(self, mode: str) -> None:
        index = self.mode_combo.findData(mode)
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(max(0, index))
        self.mode_combo.blockSignals(False)

    def mode_changed(self) -> None:
        mode = self.mode_combo.currentData()
        self.main_window.settings.set("device_mode", mode)
        scan_page = getattr(self.main_window, "scan_page", None)
        if scan_page is not None and hasattr(scan_page, "device_combo"):
            scan_page.set_mode(mode)

    def run_test(self) -> None:
        self.test_button.setEnabled(False)
        self.diagnostics.setPlainText("Testing selected mode and loading InsightFace models...")
        self.worker = DeviceTestWorker(self.mode_combo.currentData(), 320)
        self.worker.completed.connect(self.test_completed)
        self.worker.failed.connect(self.test_failed)
        self.worker.start()

    def test_completed(self, diagnostics: Dict) -> None:
        self.test_button.setEnabled(True)
        self.diagnostics.setPlainText(json.dumps(diagnostics, indent=2))
        self.main_window.set_actual_provider(diagnostics.get("actual_provider", "Unknown"))

    def test_failed(self, message: str) -> None:
        self.test_button.setEnabled(True)
        self.diagnostics.setPlainText(f"Engine test failed:\n\n{message}")


class MainWindow(QMainWindow):
    def __init__(self, app_dir: Path):
        super().__init__()
        self.app_dir = app_dir
        self.install_dir = install_root()
        self.data_dir = self.app_dir / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings = SettingsStore(self.data_dir / "settings.json")
        self.person_store = PersonStore(self.data_dir)
        self.current_provider = "Not initialized"
        self.current_finding_dir: Optional[Path] = None
        self.current_db_path: Optional[Path] = None

        self.setWindowTitle("FaceFinder PC")
        self.resize(1480, 920)
        self.setMinimumSize(1180, 760)

        central = QWidget()
        central.setObjectName("appRoot")
        shell = QHBoxLayout(central)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        self.setCentralWidget(central)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(246)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 20, 18, 18)
        side.setSpacing(8)

        brand = QHBoxLayout()
        logo = QLabel("FF")
        logo.setObjectName("brandLogo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedSize(44, 44)
        brand_text = QVBoxLayout()
        brand_title = QLabel("FaceFinder")
        brand_title.setObjectName("brandTitle")
        brand_subtitle = QLabel("PC Portable")
        brand_subtitle.setObjectName("brandSubtitle")
        brand_text.addWidget(brand_title)
        brand_text.addWidget(brand_subtitle)
        brand.addWidget(logo)
        brand.addLayout(brand_text, 1)
        side.addLayout(brand)
        side.addSpacing(22)

        nav_label = QLabel("WORKSPACE")
        nav_label.setObjectName("navSection")
        side.addWidget(nav_label)
        nav_items = [
            ("Overview", "Your FaceFinder workspace"),
            ("Reference people", "Profiles and face vectors"),
            ("New scan", "Select people and folders"),
            ("Findings", "Review, copy and move"),
            ("CPU / GPU", "Hardware and diagnostics"),
        ]
        self.nav_buttons: List[QPushButton] = []
        for index, (text, tooltip) in enumerate(nav_items):
            button = QPushButton(text)
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setToolTip(tooltip)
            button.setMinimumHeight(44)
            button.clicked.connect(lambda checked=False, i=index: self.switch_page(i))
            self.nav_buttons.append(button)
            side.addWidget(button)
        side.addStretch()

        portable_card = QFrame()
        portable_card.setObjectName("portableCard")
        portable_layout = QVBoxLayout(portable_card)
        portable_layout.setContentsMargins(14, 13, 14, 13)
        portable_title = QLabel("PORTABLE STATUS")
        portable_title.setObjectName("portableTitle")
        self.sidebar_engine = QLabel("●  Engine not initialized")
        self.sidebar_engine.setObjectName("sidebarEngine")
        self.sidebar_engine.setWordWrap(True)
        portable_hint = QLabel("Profiles and findings are stored in your Windows user data folder.")
        portable_hint.setObjectName("portableHint")
        portable_hint.setWordWrap(True)
        portable_layout.addWidget(portable_title)
        portable_layout.addWidget(self.sidebar_engine)
        portable_layout.addWidget(portable_hint)
        side.addWidget(portable_card)
        shell.addWidget(sidebar)

        content = QWidget()
        content.setObjectName("contentArea")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(26, 18, 26, 24)
        content_layout.setSpacing(16)

        topbar = QHBoxLayout()
        topbar_text = QVBoxLayout()
        self.topbar_title = QLabel("Overview")
        self.topbar_title.setObjectName("topbarTitle")
        self.topbar_subtitle = QLabel("Your FaceFinder workspace")
        self.topbar_subtitle.setObjectName("topbarSubtitle")
        topbar_text.addWidget(self.topbar_title)
        topbar_text.addWidget(self.topbar_subtitle)
        topbar.addLayout(topbar_text)
        topbar.addStretch()
        self.engine_label = QLabel("Engine not initialized")
        self.engine_label.setObjectName("engineChip")
        topbar.addWidget(self.engine_label, 0, Qt.AlignmentFlag.AlignVCenter)
        content_layout.addLayout(topbar)

        metrics = QHBoxLayout()
        metrics.setSpacing(12)
        self.gpu_label, self.gpu_progress = self._hardware_card(metrics, "GPU", "Detecting…", "gpu")
        self.cpu_label, self.cpu_progress = self._hardware_card(metrics, "CPU", "—", "cpu")
        self.ram_label, self.ram_progress = self._hardware_card(metrics, "RAM", "—", "ram")
        self.provider_label_header, self.provider_progress = self._hardware_card(metrics, "ACTIVE PROVIDER", "Not initialized", "provider")
        content_layout.addLayout(metrics)

        self.stack = QStackedWidget()
        self.stack.setObjectName("pageStack")
        content_layout.addWidget(self.stack, 1)
        shell.addWidget(content, 1)

        self.device_page = None
        self.scan_page = ScanPage(self)
        self.device_page = DeviceSetupPage(self)
        self.findings_page = FindingsPage(self)
        self.reference_page = ReferencePage(self)
        self.dashboard_page = DashboardPage(self)

        self.page_scroll_areas: List[QScrollArea] = []
        for page in (self.dashboard_page, self.reference_page, self.scan_page, self.findings_page, self.device_page):
            scroll = QScrollArea()
            scroll.setObjectName("pageScroll")
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setWidget(page)
            self.page_scroll_areas.append(scroll)
            self.stack.addWidget(scroll)

        self.page_meta = [
            ("Overview", "Your FaceFinder workspace"),
            ("Reference people", "Profiles and face vectors"),
            ("New scan", "Select people and folders"),
            ("Findings", "Review, copy and move"),
            ("CPU / GPU", "Hardware and diagnostics"),
        ]
        self.switch_page(0)

        self.monitor_timer = QTimer(self)
        self.monitor_timer.timeout.connect(self.update_metrics)
        self.monitor_timer.start(1000)
        self.update_metrics()

        if not self.settings.get("setup_completed", False):
            QTimer.singleShot(300, self.show_setup_wizard)

    def _hardware_card(self, target: QHBoxLayout, title: str, value: str, kind: str):
        card = QFrame()
        card.setObjectName("hardwareCard")
        card.setProperty("kind", kind)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        title_label = QLabel(title)
        title_label.setObjectName("hardwareTitle")
        value_label = QLabel(value)
        value_label.setObjectName("hardwareValue")
        value_label.setWordWrap(True)
        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(0)
        progress.setTextVisible(False)
        progress.setObjectName("hardwareProgress")
        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addWidget(progress)
        target.addWidget(card, 1)
        return value_label, progress

    def switch_page(self, index: int) -> None:
        if index < 0 or index >= self.stack.count():
            return
        self.stack.setCurrentIndex(index)
        title, subtitle = self.page_meta[index]
        self.topbar_title.setText(title)
        self.topbar_subtitle.setText(subtitle)
        for position, button in enumerate(self.nav_buttons):
            button.setChecked(position == index)
        if index == 0:
            self.dashboard_page.refresh()
        elif index == 3:
            self.findings_page.refresh_findings()

    def set_actual_provider(self, provider: str) -> None:
        self.current_provider = provider
        if provider == "CUDAExecutionProvider":
            text = "GPU active · CUDA"
            self.engine_label.setProperty("state", "success")
            self.sidebar_engine.setText("●  GPU active\nCUDAExecutionProvider")
            self.sidebar_engine.setProperty("state", "success")
        elif provider == "CPUExecutionProvider":
            text = "CPU active"
            self.engine_label.setProperty("state", "cpu")
            self.sidebar_engine.setText("●  CPU active\nCPUExecutionProvider")
            self.sidebar_engine.setProperty("state", "cpu")
        else:
            text = str(provider or "Not initialized")
            self.engine_label.setProperty("state", "neutral")
            self.sidebar_engine.setText(f"●  {text}")
            self.sidebar_engine.setProperty("state", "neutral")
        self.engine_label.setText(text)
        self.provider_label_header.setText(str(provider))
        self.provider_progress.setValue(100 if provider in {"CUDAExecutionProvider", "CPUExecutionProvider"} else 0)
        for widget in (self.engine_label, self.sidebar_engine):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        if hasattr(self, "dashboard_page"):
            self.dashboard_page.refresh()

    def update_metrics(self) -> None:
        metrics = get_system_metrics()
        cpu = metrics.get("cpu_percent")
        ram_used = metrics.get("ram_used_gb")
        ram_total = metrics.get("ram_total_gb")
        self.cpu_label.setText(f"{cpu:.0f}% usage" if cpu is not None else "Telemetry unavailable")
        self.cpu_progress.setValue(int(cpu or 0))
        if ram_used is not None and ram_total is not None:
            ram_percent = int((ram_used / ram_total) * 100) if ram_total else 0
            self.ram_label.setText(f"{ram_used:.1f} / {ram_total:.1f} GB")
            self.ram_progress.setValue(max(0, min(100, ram_percent)))
        else:
            self.ram_label.setText("Telemetry unavailable")
            self.ram_progress.setValue(0)

        if metrics.get("gpu_available"):
            temp = metrics.get("gpu_temperature")
            temp_text = f" · {temp:.0f}°C" if temp is not None else ""
            percent = int(metrics.get("gpu_percent", 0) or 0)
            self.gpu_label.setText(
                f"{percent}% · {metrics.get('vram_used_gb', 0):.1f}/{metrics.get('vram_total_gb', 0):.1f} GB{temp_text}"
            )
            self.gpu_label.setToolTip(str(metrics.get("gpu_name", "NVIDIA GPU")))
            self.gpu_progress.setValue(percent)
        else:
            self.gpu_label.setText("NVIDIA telemetry unavailable")
            self.gpu_progress.setValue(0)

    def show_setup_wizard(self) -> None:
        SetupWizard(self).exec()

    def launch_setup_script(self, mode: str) -> None:
        script = self.install_dir / ("setup_gpu.ps1" if mode == "gpu" else "setup_cpu.ps1")
        if not script.exists():
            QMessageBox.critical(self, "Setup Script Missing", str(script))
            return
        answer = QMessageBox.question(
            self,
            "Repair Portable Runtime",
            "FaceFinder will close, then PowerShell will update only the private runtime "
            "inside this portable folder. Your persons and Findings will not be changed. Continue?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            subprocess.Popen([
                "powershell.exe", "-NoExit", "-ExecutionPolicy", "Bypass", "-File", str(script)
            ], cwd=str(self.install_dir))
            QApplication.quit()
        except Exception as exc:
            QMessageBox.critical(self, "Could Not Start Repair", str(exc))

    def closeEvent(self, event) -> None:
        worker = self.scan_page.worker
        if worker and worker.isRunning():
            answer = QMessageBox.question(
                self,
                "Scan Is Running",
                "Stop the active scan safely and close FaceFinder?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            worker.request_stop()
            worker.wait(10_000)
        event.accept()


STYLE_SHEET = """
* { font-family: "Segoe UI"; font-size: 10pt; }
QMainWindow, QWidget#appRoot { background: #F4F7FB; color: #0F172A; }
QWidget#contentArea { background: #F4F7FB; }
QStackedWidget#pageStack { background: transparent; }

QFrame#sidebar { background: #0B1220; border: none; }
QLabel#brandLogo, QLabel#setupBadge {
    background: #2563EB; color: white; border-radius: 12px; font-size: 14pt; font-weight: 800;
}
QLabel#brandTitle { color: #F8FAFC; font-size: 15pt; font-weight: 750; }
QLabel#brandSubtitle { color: #7F8DA3; font-size: 9pt; }
QLabel#navSection { color: #64748B; font-size: 8pt; font-weight: 700; letter-spacing: 1px; margin: 4px 8px 6px 8px; }
QPushButton#navButton {
    background: transparent; color: #AAB7CA; border: none; border-radius: 9px;
    padding: 10px 14px; text-align: left; font-weight: 600;
}
QPushButton#navButton:hover { background: #152033; color: #F8FAFC; }
QPushButton#navButton:checked { background: #2563EB; color: white; }
QFrame#portableCard { background: #111C2E; border: 1px solid #213047; border-radius: 12px; }
QLabel#portableTitle { color: #64748B; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }
QLabel#sidebarEngine { color: #CBD5E1; font-weight: 650; }
QLabel#sidebarEngine[state="success"] { color: #4ADE80; }
QLabel#sidebarEngine[state="cpu"] { color: #C4B5FD; }
QLabel#portableHint { color: #718096; font-size: 8.5pt; }

QLabel#topbarTitle { color: #0F172A; font-size: 17pt; font-weight: 750; }
QLabel#topbarSubtitle, QLabel#pageSubtitle, QLabel#mutedText { color: #64748B; }
QLabel#pageTitle { color: #0F172A; font-size: 22pt; font-weight: 760; }
QLabel#cardTitle { color: #0F172A; font-size: 12pt; font-weight: 700; }
QLabel#cardTitleLarge { color: #0F172A; font-size: 16pt; font-weight: 750; }
QLabel#heroTitle { color: white; font-size: 22pt; font-weight: 760; }
QLabel#heroSubtitle { color: #DCE8FF; font-size: 10.5pt; }

QFrame#card, QFrame#statCard, QFrame#hardwareCard, QFrame#miniMetric {
    background: white; border: 1px solid #E3E9F2; border-radius: 12px;
}
QFrame#heroCard { background: #1E4FD7; border: none; border-radius: 15px; }
QFrame#statCard[accent="blue"] { border-top: 3px solid #2563EB; }
QFrame#statCard[accent="violet"] { border-top: 3px solid #7C3AED; }
QFrame#statCard[accent="green"] { border-top: 3px solid #16A34A; }
QFrame#statCard[accent="amber"] { border-top: 3px solid #F59E0B; }
QLabel#statLabel, QLabel#hardwareTitle, QLabel#miniMetricTitle {
    color: #7A879A; font-size: 8pt; font-weight: 700; letter-spacing: .7px;
}
QLabel#statValue { color: #0F172A; font-size: 23pt; font-weight: 760; }
QLabel#statCaption { color: #64748B; font-size: 8.7pt; }
QLabel#hardwareValue { color: #1E293B; font-size: 10pt; font-weight: 650; }
QLabel#miniMetricValue { color: #0F172A; font-size: 12pt; font-weight: 730; }

QLabel#engineChip, QLabel#statusPill, QLabel#findingPill {
    background: #EEF2F7; color: #475569; border: 1px solid #DDE4EE; border-radius: 14px;
    padding: 6px 11px; font-weight: 650;
}
QLabel#engineChip[state="success"] { background: #EAF8EF; color: #15803D; border-color: #B9E9C8; }
QLabel#engineChip[state="cpu"] { background: #F2ECFF; color: #6D28D9; border-color: #D9C8FF; }
QLabel#statusPill { background: #EEF6FF; color: #1D4ED8; border-color: #CFE0FF; }
QLabel#findingPill { background: #F2ECFF; color: #6D28D9; border-color: #DCCFFF; }
QLabel#avatar { background: #E8F0FF; color: #2563EB; border: 1px solid #C7D8FF; border-radius: 32px; font-size: 16pt; font-weight: 800; }
QLabel#currentFile { background: #F8FAFC; color: #475569; border: 1px solid #E5EAF2; border-radius: 8px; padding: 9px 11px; }

QPushButton {
    min-height: 36px; background: white; color: #334155; border: 1px solid #D8E0EB;
    border-radius: 8px; padding: 7px 14px; font-weight: 650;
}
QPushButton:hover { background: #F8FAFC; border-color: #B8C5D8; }
QPushButton:pressed { background: #EEF2F7; }
QPushButton:disabled { background: #EEF2F6; color: #9AA7B8; border-color: #E2E8F0; }
QPushButton[role="primary"] { background: #2563EB; color: white; border-color: #2563EB; }
QPushButton[role="primary"]:hover { background: #1D4ED8; border-color: #1D4ED8; }
QPushButton[role="success"] { background: #16A34A; color: white; border-color: #16A34A; }
QPushButton[role="success"]:hover { background: #15803D; }
QPushButton[role="warning"] { background: #F59E0B; color: white; border-color: #F59E0B; }
QPushButton[role="warning"]:hover { background: #D97706; }
QPushButton[role="danger"] { background: #DC2626; color: white; border-color: #DC2626; }
QPushButton[role="danger"]:hover { background: #B91C1C; }
QPushButton[role="dangerGhost"] { background: #FFF7F7; color: #B91C1C; border-color: #F3CACA; }
QPushButton[role="dangerGhost"]:hover { background: #FEECEC; }
QPushButton[role="secondary"] { background: white; color: #334155; border-color: #D8E0EB; }

QLabel#formLabel { color: #334155; background: transparent; font-weight: 650; padding-right: 8px; }
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {
    background: #FFFFFF; color: #0F172A; border: 1px solid #CBD5E1; border-radius: 8px;
    padding: 7px 10px; min-height: 24px; selection-background-color: #2563EB;
}
QComboBox { padding-right: 34px; }
QSpinBox, QDoubleSpinBox { padding-right: 10px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QPlainTextEdit:focus {
    border: 1px solid #2563EB;
}
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; border: none; width: 30px; }
QComboBox::down-arrow { width: 9px; height: 9px; }
QComboBox QAbstractItemView {
    background: #FFFFFF; color: #0F172A; border: 1px solid #CBD5E1; outline: 0; padding: 4px;
    selection-background-color: #E8F0FF; selection-color: #0F172A;
}
QComboBox QAbstractItemView::item { color: #0F172A; background: #FFFFFF; min-height: 30px; padding: 6px 10px; }
QComboBox QAbstractItemView::item:hover, QComboBox QAbstractItemView::item:selected { background: #E8F0FF; color: #0F172A; }
QCheckBox { color: #475569; spacing: 7px; }
QCheckBox::indicator { width: 17px; height: 17px; }
QCheckBox::indicator:checked { background: #2563EB; border: 1px solid #2563EB; border-radius: 4px; }
QCheckBox::indicator:unchecked { background: white; border: 1px solid #B7C2D2; border-radius: 4px; }

QListWidget, QTableWidget {
    background: white; color: #1E293B; border: 1px solid #E1E7F0; border-radius: 9px;
    outline: none; padding: 4px; selection-background-color: #E8F0FF; selection-color: #0F172A;
}
QListWidget::item { border-radius: 8px; padding: 10px; margin: 2px; }
QListWidget::item:hover { background: #F4F7FB; }
QListWidget::item:selected { background: #E8F0FF; color: #1D4ED8; }
QListWidget#imageGallery::item { background: #F8FAFC; border: 1px solid #E3E9F2; padding: 8px; }
QListWidget#recentList { border: none; background: transparent; }
QListWidget#recentList::item { border-bottom: 1px solid #EDF1F6; border-radius: 0; padding: 11px 4px; }
QTableWidget { gridline-color: #E9EEF5; alternate-background-color: #FAFCFF; }
QHeaderView::section { background: #F2F5F9; color: #526176; padding: 10px 8px; border: none; border-bottom: 1px solid #DDE5EF; font-weight: 700; }

QProgressBar { background: #E9EEF5; border: none; border-radius: 4px; min-height: 7px; max-height: 7px; }
QProgressBar::chunk { background: #2563EB; border-radius: 4px; }
QFrame#hardwareCard[kind="gpu"] QProgressBar::chunk { background: #16A34A; }
QFrame#hardwareCard[kind="cpu"] QProgressBar::chunk { background: #7C3AED; }
QFrame#hardwareCard[kind="ram"] QProgressBar::chunk { background: #0EA5E9; }
QFrame#hardwareCard[kind="provider"] QProgressBar::chunk { background: #F59E0B; }

QScrollArea#pageScroll { background: transparent; border: none; }
QScrollArea#pageScroll > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #C7D2E2; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #9EACC0; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #C7D2E2; border-radius: 4px; min-width: 30px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QDialog#setupDialog { background: #F4F7FB; }
QFrame#setupBanner { background: #0F172A; border: none; }
QLabel#setupTitle { color: white; font-size: 20pt; font-weight: 760; }
QLabel#setupSubtitle { color: #AAB7CA; }
QPlainTextEdit#diagnosticOutput { background: #0E1726; color: #D6E0EF; border: 1px solid #24344D; font-family: "Cascadia Mono", "Consolas"; }
QToolTip { background: #0F172A; color: white; border: none; padding: 5px; }
"""
