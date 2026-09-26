#!/usr/bin/env python3
"""Enrollment tool: label real characters from real plate photos.

This is the actual path to high accuracy (see the README): point it at a
handful of photos or crops of plates seen by the real camera, and for every
segmented character it shows you the crop (and the current classifier's
best guess, once one exists) and asks for the correct label. A handful of
enrolled examples per label, from the real camera and lighting, typically
does far more for accuracy than the synthetic bootstrap templates alone.

Usage:
    python tools/enroll.py path/to/photo.jpg
    python tools/enroll.py path/to/folder/          # every image in it
    python tools/enroll.py --config path/to/config.yaml photo1.jpg photo2.jpg
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QImage, QPixmap  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from anpr_app.config import load_config  # noqa: E402
from anpr_app.gui.style import apply_app_style  # noqa: E402
from anpr_app.vision.classifier import TemplateClassifier, TemplateStore  # noqa: E402
from anpr_app.vision.detector import PlateDetector  # noqa: E402
from anpr_app.vision.plate_letters import ALL_LABELS, DIGITS, LETTERS  # noqa: E402
from anpr_app.vision.segmenter import CharacterSegmenter  # noqa: E402

IMAGE_EXTENSIONS = ("*.jpg", "*.jpeg", "*.png", "*.bmp")


def collect_images(raw_paths: list[str]) -> list[Path]:
    images: list[Path] = []
    for raw in raw_paths:
        path = Path(raw)
        if path.is_dir():
            for pattern in IMAGE_EXTENSIONS:
                images.extend(sorted(path.glob(pattern)))
        elif path.is_file():
            images.append(path)
    return images


def to_pixmap(image: np.ndarray, max_width: int, max_height: int | None = None) -> QPixmap:
    if image.ndim == 2:
        image = np.ascontiguousarray(image)
        h, w = image.shape
        qimg = QImage(image.data, w, h, w, QImage.Format_Grayscale8)
    else:
        rgb = np.ascontiguousarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
    pixmap = QPixmap.fromImage(qimg.copy())
    if max_height:
        return pixmap.scaled(max_width, max_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return pixmap.scaledToWidth(max_width, Qt.SmoothTransformation)


class EnrollWindow(QMainWindow):
    def __init__(self, store: TemplateStore, classifier: TemplateClassifier | None, image_paths: list[Path]):
        super().__init__()
        self.store = store
        self.classifier = classifier
        self.image_paths = image_paths
        self.image_idx = 0
        self.chars = []
        self.char_idx = 0
        self.enrolled_count = 0

        self.setWindowTitle("ابزار ثبت نمونه کاراکتر پلاک")
        self.resize(560, 560)

        self.plate_label = QLabel()
        self.plate_label.setAlignment(Qt.AlignCenter)
        self.info_label = QLabel()
        self.info_label.setAlignment(Qt.AlignCenter)

        self.char_label = QLabel()
        self.char_label.setFixedSize(160, 220)
        self.char_label.setAlignment(Qt.AlignCenter)
        self.char_label.setStyleSheet("background:#000; border:2px solid #33445c;")

        self.suggestion_label = QLabel()
        self.suggestion_label.setAlignment(Qt.AlignCenter)

        self.label_input = QLineEdit()
        self.label_input.setPlaceholderText("برچسب درست را وارد کنید (راهنما پایین صفحه) و Enter بزنید")
        self.label_input.returnPressed.connect(self._submit_label)

        submit_btn = QPushButton("ثبت و بعدی")
        submit_btn.clicked.connect(self._submit_label)
        skip_char_btn = QPushButton("رد شدن از این کاراکتر")
        skip_char_btn.clicked.connect(self._next_char)
        skip_plate_btn = QPushButton("رد شدن از این تصویر")
        skip_plate_btn.clicked.connect(self._next_image)

        legend = QLabel(self._legend_text())
        legend.setWordWrap(True)
        legend.setStyleSheet("color:#9fb0c3; font-size:11px;")

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(submit_btn)
        buttons_row.addWidget(skip_char_btn)
        buttons_row.addWidget(skip_plate_btn)

        layout = QVBoxLayout()
        layout.addWidget(self.plate_label)
        layout.addWidget(self.info_label)
        layout.addWidget(self.char_label, alignment=Qt.AlignCenter)
        layout.addWidget(self.suggestion_label)
        layout.addWidget(self.label_input)
        layout.addLayout(buttons_row)
        layout.addWidget(legend)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self._load_image()

    @staticmethod
    def _legend_text() -> str:
        digit_part = "  ".join(DIGITS)
        letter_part = "  ".join(f"{slug}={glyph}" for slug, glyph in LETTERS.items())
        return (
            "راهنمای کد برچسب‌ها — ارقام: "
            + digit_part
            + "\nحروف (کد=حرف): "
            + letter_part
            + "\n(کادر برچسب را خالی بگذارید و Enter بزنید تا بدون ثبت رد شود)"
        )

    def _load_image(self) -> None:
        if self.image_idx >= len(self.image_paths):
            QMessageBox.information(
                self, "پایان کار", f"همه تصاویر بررسی شد. تعداد {self.enrolled_count} نمونه ثبت شد."
            )
            self.close()
            return

        path = self.image_paths[self.image_idx]
        image = cv2.imread(str(path))
        if image is None:
            self.info_label.setText(f"{path.name}: خواندن تصویر ممکن نشد")
            self._next_image()
            return

        candidates = PlateDetector().detect(image)
        if not candidates:
            self.info_label.setText(f"{path.name}: پلاکی پیدا نشد")
            self._next_image()
            return

        self.plate_crop = candidates[0].crop
        self.plate_label.setPixmap(to_pixmap(self.plate_crop, max_width=480))
        self.chars = CharacterSegmenter().segment(self.plate_crop)
        self.char_idx = 0
        self.info_label.setText(f"{path.name} ({self.image_idx + 1}/{len(self.image_paths)}) — {len(self.chars)} کاراکتر")
        self._show_char()

    def _show_char(self) -> None:
        if self.char_idx >= len(self.chars):
            self._next_image()
            return
        glyph = self.chars[self.char_idx].image
        self.char_label.setPixmap(to_pixmap(glyph, max_width=150, max_height=200))

        suggestion = ""
        if self.classifier is not None:
            label, score = self.classifier.classify(glyph)
            if label:
                glyph_display = LETTERS.get(label, label)
                suggestion = f"حدس نرم‌افزار: {label} ({glyph_display}) — امتیاز {score:.2f}"
            else:
                suggestion = "حدس نرم‌افزار: نامشخص"
        self.suggestion_label.setText(suggestion)
        self.label_input.clear()
        self.label_input.setFocus()

    def _submit_label(self) -> None:
        label = self.label_input.text().strip()
        if label and label not in ALL_LABELS:
            QMessageBox.warning(self, "برچسب نامعتبر", f"«{label}» در فهرست کاراکترهای مجاز نیست.")
            return
        if label:
            self.store.enroll(label, self.chars[self.char_idx].image)
            self.enrolled_count += 1
            if self.classifier is not None:
                self.classifier.reload()
        self._next_char()

    def _next_char(self) -> None:
        self.char_idx += 1
        self._show_char()

    def _next_image(self) -> None:
        self.image_idx += 1
        self._load_image()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("images", nargs="+", help="فایل تصویر یا پوشه حاوی عکس‌های پلاک")
    default_config = Path(__file__).resolve().parent.parent / "config.yaml"
    parser.add_argument("--config", default=str(default_config), help="مسیر فایل تنظیمات")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        config_path = config_path.parent / "config.example.yaml"
    config = load_config(config_path)

    image_paths = collect_images(args.images)
    if not image_paths:
        print("هیچ تصویری در مسیرهای داده‌شده یافت نشد.")
        sys.exit(1)

    store = TemplateStore(config.paths.templates_dir)
    classifier = None if store.is_empty() else TemplateClassifier(store)

    app = QApplication(sys.argv)
    apply_app_style(app)
    window = EnrollWindow(store, classifier, image_paths)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
