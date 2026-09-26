"""The main window: live camera view with overlay, and the recent-events feed."""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..config import Config
from ..core.access_control import AccessControl, AccessEvent
from ..core.camera_worker import CameraWorker
from ..database.db import Database
from ..vision.classifier import TemplateClassifier, TemplateStore, generate_bootstrap_templates
from ..vision.plate_letters import ALL_LABELS
from .logs_view import LogsDialog
from .plates_dialog import PlatesDialog

BOX_COLOR = (0, 220, 60)
ENTRY_COLOR = QColor("#1f8a3d")
EXIT_COLOR = QColor("#b3261e")
UNKNOWN_COLOR = QColor("#5b6472")


def frame_to_pixmap(frame_bgr: np.ndarray, bbox: tuple[int, int, int, int] | None) -> QPixmap:
    frame = frame_bgr.copy()
    if bbox is not None:
        x, y, w, h = bbox
        cv2.rectangle(frame, (x, y), (x + w, y + h), BOX_COLOR, 3)
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    rgb = np.ascontiguousarray(rgb)
    h, w, ch = rgb.shape
    qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg.copy())


class MainWindow(QMainWindow):
    def __init__(self, config: Config, db: Database):
        super().__init__()
        self.config = config
        self.db = db
        self.setWindowTitle(config.app.window_title)
        self.resize(1240, 740)

        self.template_store = TemplateStore(config.paths.templates_dir)
        seeded = generate_bootstrap_templates(self.template_store)
        self.classifier = TemplateClassifier(self.template_store)

        self.access_control = AccessControl(
            db,
            cooldown_seconds=config.recognition.cooldown_seconds,
            save_snapshots=config.paths.save_snapshots,
            snapshots_dir=config.paths.snapshots_dir,
        )

        self.workers: list[CameraWorker] = []
        self._visible_camera_index = 0

        self._build_ui(seeded)
        self._start_workers()

    # ---- UI construction --------------------------------------------------

    def _build_ui(self, seeded_count: int) -> None:
        central = QWidget()
        root_layout = QHBoxLayout(central)

        video_col = QVBoxLayout()
        self.camera_combo = QComboBox()
        for cam in self.config.cameras:
            self.camera_combo.addItem(cam.name)
        self.camera_combo.setVisible(len(self.config.cameras) > 1)
        self.camera_combo.currentIndexChanged.connect(self._on_camera_selected)

        self.video_label = QLabel("در حال اتصال به دوربین...")
        self.video_label.setObjectName("videoLabel")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(640, 440)

        self.camera_status_label = QLabel("")

        video_col.addWidget(self.camera_combo)
        video_col.addWidget(self.video_label, 1)
        video_col.addWidget(self.camera_status_label)

        events_col = QVBoxLayout()
        events_title = QLabel("رویدادهای اخیر")
        events_title.setObjectName("sectionTitle")
        self.events_list = QListWidget()

        manage_btn = QPushButton("مدیریت افراد و پلاک‌ها")
        manage_btn.clicked.connect(self._open_plates_dialog)
        logs_btn = QPushButton("گزارش کامل ورود و خروج")
        logs_btn.clicked.connect(self._open_logs_dialog)

        events_col.addWidget(events_title)
        events_col.addWidget(self.events_list, 1)
        events_col.addWidget(manage_btn)
        events_col.addWidget(logs_btn)

        root_layout.addLayout(video_col, 2)
        root_layout.addLayout(events_col, 1)
        self.setCentralWidget(central)

        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        known = len(self.classifier.known_labels())
        total = len(ALL_LABELS)
        if known == 0:
            status_bar.showMessage(
                "هیچ الگوی کاراکتری موجود نیست؛ برای شروع بازشناسی از ابزار enroll.py استفاده کنید.", 0
            )
        elif known < total:
            status_bar.showMessage(
                f"الگوی {known} از {total} کاراکتر آماده است؛ برای افزایش دقت، نمونه بیشتری با enroll.py ثبت کنید.",
                0,
            )
        else:
            status_bar.showMessage(f"{seeded_count} الگوی اولیه آماده شد. برای دقت بالاتر، نمونه واقعی ثبت کنید.", 8000)

    # ---- camera workers -----------------------------------------------------

    def _start_workers(self) -> None:
        for cam in self.config.cameras:
            worker = CameraWorker(cam, self.classifier, self.config.recognition, self.access_control)
            worker.frame_ready.connect(self._on_frame_ready)
            worker.access_event.connect(self._on_access_event)
            worker.status_changed.connect(self._on_status_changed)
            worker.start()
            self.workers.append(worker)

    def _on_camera_selected(self, index: int) -> None:
        self._visible_camera_index = index

    def _on_frame_ready(self, frame: np.ndarray, bbox) -> None:
        sender = self.sender()
        try:
            idx = self.workers.index(sender)
        except ValueError:
            idx = -1
        if idx != self._visible_camera_index:
            return
        pixmap = frame_to_pixmap(frame, bbox)
        self.video_label.setPixmap(
            pixmap.scaled(self.video_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def _on_access_event(self, event: AccessEvent) -> None:
        item = QListWidgetItem(event.message)
        color = UNKNOWN_COLOR if not event.is_known else (ENTRY_COLOR if event.direction == "entry" else EXIT_COLOR)
        item.setBackground(color)
        item.setForeground(QColor("white"))
        self.events_list.insertItem(0, item)

    def _on_status_changed(self, camera_name: str, text: str) -> None:
        self.camera_status_label.setText(f"{camera_name}: {text}")

    # ---- dialogs -----------------------------------------------------

    def _open_plates_dialog(self) -> None:
        PlatesDialog(self.db, self).exec()

    def _open_logs_dialog(self) -> None:
        LogsDialog(self.db, self).exec()

    # ---- lifecycle -----------------------------------------------------

    def closeEvent(self, event) -> None:
        for worker in self.workers:
            worker.stop()
        for worker in self.workers:
            worker.wait(2000)
        super().closeEvent(event)
