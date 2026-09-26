"""Full entry/exit report, with filters and CSV export."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..database.db import Database
from ..jalali import format_jalali_compact, format_jalali_datetime

DAY_RANGE_OPTIONS = ["امروز", "۷ روز اخیر", "۳۰ روز اخیر", "همه"]


class LogsDialog(QDialog):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("گزارش کامل ورود و خروج")
        self.resize(920, 560)
        self._logs_cache: list = []

        self.plate_filter = QLineEdit()
        self.plate_filter.setPlaceholderText("فیلتر بر اساس پلاک (اختیاری)")
        self.plate_filter.returnPressed.connect(self._reload)

        self.person_combo = QComboBox()
        self.person_combo.addItem("همه افراد", None)
        for person in db.list_persons():
            self.person_combo.addItem(person.display_name, person.id)

        self.days_combo = QComboBox()
        self.days_combo.addItems(DAY_RANGE_OPTIONS)

        search_btn = QPushButton("جست‌وجو")
        search_btn.clicked.connect(self._reload)
        export_btn = QPushButton("خروجی CSV")
        export_btn.clicked.connect(self._export_csv)

        filters_row = QHBoxLayout()
        filters_row.addWidget(QLabel("پلاک:"))
        filters_row.addWidget(self.plate_filter)
        filters_row.addWidget(QLabel("شخص:"))
        filters_row.addWidget(self.person_combo)
        filters_row.addWidget(self.days_combo)
        filters_row.addWidget(search_btn)
        filters_row.addStretch(1)
        filters_row.addWidget(export_btn)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["تاریخ و ساعت", "جهت", "پلاک", "شخص", "دوربین"])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)

        layout = QVBoxLayout(self)
        layout.addLayout(filters_row)
        layout.addWidget(self.table)

        self._reload()

    def _range_start(self) -> datetime | None:
        now = datetime.now()
        idx = self.days_combo.currentIndex()
        if idx == 0:
            return datetime(now.year, now.month, now.day)
        if idx == 1:
            return now - timedelta(days=7)
        if idx == 2:
            return now - timedelta(days=30)
        return None

    def _reload(self) -> None:
        logs = self.db.query_logs(person_id=self.person_combo.currentData(), start=self._range_start(), limit=2000)
        plate_text = self.plate_filter.text().strip()
        if plate_text:
            logs = [log for log in logs if plate_text in log.plate_display or plate_text in log.plate_key]
        self._logs_cache = logs

        self.table.setRowCount(len(logs))
        for row, log in enumerate(logs):
            dt = datetime.fromisoformat(log.occurred_at)
            direction_fa = "ورود" if log.direction == "entry" else "خروج"
            for col, text in enumerate(
                [
                    format_jalali_datetime(dt),
                    direction_fa,
                    log.plate_display,
                    log.person_name_snapshot or "ناشناس",
                    log.camera_name or "",
                ]
            ):
                self.table.setItem(row, col, QTableWidgetItem(text))

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "ذخیره گزارش", "access-log.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh)
            writer.writerow(["تاریخ شمسی", "ساعت", "جهت", "پلاک", "شخص", "دوربین"])
            for log in self._logs_cache:
                dt = datetime.fromisoformat(log.occurred_at)
                writer.writerow(
                    [
                        format_jalali_compact(dt).split(" ")[0],
                        dt.strftime("%H:%M:%S"),
                        "ورود" if log.direction == "entry" else "خروج",
                        log.plate_display,
                        log.person_name_snapshot or "ناشناس",
                        log.camera_name or "",
                    ]
                )
        QMessageBox.information(self, "خروجی CSV", "گزارش با موفقیت ذخیره شد.")
