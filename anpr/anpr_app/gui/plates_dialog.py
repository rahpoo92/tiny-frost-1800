"""The plate bank: manage people and the plates registered to them."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..database.db import Database, Person, PlateRecord
from ..vision.plate_letters import LETTERS, PlateNumber


class PersonFormDialog(QDialog):
    def __init__(self, parent=None, person: Person | None = None):
        super().__init__(parent)
        self.setWindowTitle("ویرایش شخص" if person else "افزودن شخص جدید")
        self.person = person

        self.name_edit = QLineEdit(person.full_name if person else "")
        self.title_edit = QLineEdit(person.title if person and person.title else "")
        self.title_edit.setPlaceholderText("مثلاً: دکتر، پرستار، کارمند (اختیاری)")
        self.notes_edit = QLineEdit(person.notes if person and person.notes else "")

        form = QFormLayout()
        form.addRow("نام و نام خانوادگی:", self.name_edit)
        form.addRow("عنوان/سمت:", self.title_edit)
        form.addRow("توضیحات:", self.notes_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "خطا", "نام نمی‌تواند خالی باشد.")
            return
        self.accept()

    def values(self) -> dict:
        return {
            "full_name": self.name_edit.text().strip(),
            "title": self.title_edit.text().strip() or None,
            "notes": self.notes_edit.text().strip() or None,
        }


class PlateFormDialog(QDialog):
    def __init__(self, db: Database, parent=None, plate: PlateRecord | None = None):
        super().__init__(parent)
        self.setWindowTitle("ویرایش پلاک" if plate else "افزودن پلاک جدید")
        self.db = db
        self.plate = plate

        self.part1_edit = QLineEdit(plate.part1 if plate else "")
        self.part1_edit.setMaxLength(2)
        self.part1_edit.setPlaceholderText("۱۲")

        self.letter_combo = QComboBox()
        for slug, glyph in LETTERS.items():
            self.letter_combo.addItem(glyph, slug)
        if plate:
            idx = self.letter_combo.findData(plate.letter_slug)
            if idx >= 0:
                self.letter_combo.setCurrentIndex(idx)

        self.part2_edit = QLineEdit(plate.part2 if plate else "")
        self.part2_edit.setMaxLength(3)
        self.part2_edit.setPlaceholderText("۳۴۵")

        self.province_edit = QLineEdit(plate.province if plate else "")
        self.province_edit.setMaxLength(2)
        self.province_edit.setPlaceholderText("۲۲")

        self.person_combo = QComboBox()
        self.person_combo.addItem("(بدون مالک مشخص)", None)
        for person in db.list_persons():
            self.person_combo.addItem(person.display_name, person.id)
        if plate and plate.person_id is not None:
            idx = self.person_combo.findData(plate.person_id)
            if idx >= 0:
                self.person_combo.setCurrentIndex(idx)

        self.notes_edit = QLineEdit(plate.notes if plate and plate.notes else "")

        plate_row = QHBoxLayout()
        plate_row.addWidget(self.part1_edit)
        plate_row.addWidget(self.letter_combo)
        plate_row.addWidget(self.part2_edit)
        plate_row.addWidget(self.province_edit)

        form = QFormLayout()
        form.addRow("شماره پلاک:", plate_row)
        form.addRow("متعلق به:", self.person_combo)
        form.addRow("توضیحات:", self.notes_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        plate = self._build_plate()
        if plate is None or not plate.is_valid():
            QMessageBox.warning(
                self,
                "خطا",
                "شماره پلاک نامعتبر است. لطفاً ۲ رقم، یک حرف، ۳ رقم و کد ۲ رقمی استان را کامل وارد کنید.",
            )
            return
        existing = self.db.find_plate_by_key(plate.to_key())
        if existing and (self.plate is None or existing.id != self.plate.id):
            QMessageBox.warning(self, "خطا", "این پلاک قبلاً در بانک اطلاعاتی ثبت شده است.")
            return
        self.accept()

    def _build_plate(self) -> PlateNumber | None:
        try:
            return PlateNumber(
                part1=self.part1_edit.text().strip(),
                letter_slug=self.letter_combo.currentData(),
                part2=self.part2_edit.text().strip(),
                province=self.province_edit.text().strip(),
            )
        except Exception:
            return None

    def values(self) -> dict:
        return {
            "plate": self._build_plate(),
            "person_id": self.person_combo.currentData(),
            "notes": self.notes_edit.text().strip() or None,
        }


class PlatesDialog(QDialog):
    """Manage the plate bank: people (تب افراد) and their plates (تب پلاک‌ها)."""

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("مدیریت افراد و پلاک‌ها")
        self.resize(760, 480)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_people_tab(), "افراد")
        self.tabs.addTab(self._build_plates_tab(), "پلاک‌ها")

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)

        self._reload_people()
        self._reload_plates()

    # ---- people tab -----------------------------------------------------

    def _build_people_tab(self) -> QWidget:
        widget = QWidget()
        self.people_table = QTableWidget(0, 3)
        self.people_table.setHorizontalHeaderLabels(["نام", "عنوان/سمت", "توضیحات"])
        self.people_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.people_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.people_table.horizontalHeader().setStretchLastSection(True)

        add_btn = QPushButton("افزودن شخص")
        add_btn.clicked.connect(self._add_person)
        edit_btn = QPushButton("ویرایش")
        edit_btn.clicked.connect(self._edit_person)
        delete_btn = QPushButton("حذف")
        delete_btn.setObjectName("dangerButton")
        delete_btn.clicked.connect(self._delete_person)

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(add_btn)
        buttons_row.addWidget(edit_btn)
        buttons_row.addWidget(delete_btn)
        buttons_row.addStretch(1)

        layout = QVBoxLayout(widget)
        layout.addWidget(self.people_table)
        layout.addLayout(buttons_row)
        return widget

    def _reload_people(self) -> None:
        people = self.db.list_persons()
        self.people_table.setRowCount(len(people))
        for row, person in enumerate(people):
            self.people_table.setItem(row, 0, QTableWidgetItem(person.full_name))
            self.people_table.setItem(row, 1, QTableWidgetItem(person.title or ""))
            self.people_table.setItem(row, 2, QTableWidgetItem(person.notes or ""))
            self.people_table.item(row, 0).setData(Qt.UserRole, person.id)
        self._people_cache = people

    def _selected_person(self) -> Person | None:
        row = self.people_table.currentRow()
        if row < 0 or row >= len(self._people_cache):
            return None
        return self._people_cache[row]

    def _add_person(self) -> None:
        dlg = PersonFormDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self.db.add_person(**dlg.values())
            self._reload_people()
            self._reload_plates()  # person combo in plate form depends on this list

    def _edit_person(self) -> None:
        person = self._selected_person()
        if person is None:
            QMessageBox.information(self, "راهنما", "ابتدا یک شخص را از فهرست انتخاب کنید.")
            return
        dlg = PersonFormDialog(self, person=person)
        if dlg.exec() == QDialog.Accepted:
            self.db.update_person(person.id, **dlg.values())
            self._reload_people()
            self._reload_plates()

    def _delete_person(self) -> None:
        person = self._selected_person()
        if person is None:
            QMessageBox.information(self, "راهنما", "ابتدا یک شخص را از فهرست انتخاب کنید.")
            return
        reply = QMessageBox.question(
            self,
            "تأیید حذف",
            f"آیا از حذف «{person.display_name}» مطمئن هستید؟ پلاک‌های او بدون مالک باقی می‌مانند.",
        )
        if reply == QMessageBox.Yes:
            self.db.delete_person(person.id)
            self._reload_people()
            self._reload_plates()

    # ---- plates tab -----------------------------------------------------

    def _build_plates_tab(self) -> QWidget:
        widget = QWidget()
        self.plates_table = QTableWidget(0, 3)
        self.plates_table.setHorizontalHeaderLabels(["شماره پلاک", "متعلق به", "توضیحات"])
        self.plates_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.plates_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.plates_table.horizontalHeader().setStretchLastSection(True)

        add_btn = QPushButton("افزودن پلاک")
        add_btn.clicked.connect(self._add_plate)
        edit_btn = QPushButton("ویرایش")
        edit_btn.clicked.connect(self._edit_plate)
        delete_btn = QPushButton("حذف")
        delete_btn.setObjectName("dangerButton")
        delete_btn.clicked.connect(self._delete_plate)

        buttons_row = QHBoxLayout()
        buttons_row.addWidget(add_btn)
        buttons_row.addWidget(edit_btn)
        buttons_row.addWidget(delete_btn)
        buttons_row.addStretch(1)

        layout = QVBoxLayout(widget)
        layout.addWidget(self.plates_table)
        layout.addLayout(buttons_row)
        return widget

    def _reload_plates(self) -> None:
        plates = self.db.list_plates()
        self.plates_table.setRowCount(len(plates))
        for row, plate in enumerate(plates):
            owner = ""
            if plate.person_id:
                person = self.db.get_person(plate.person_id)
                owner = person.display_name if person else ""
            self.plates_table.setItem(row, 0, QTableWidgetItem(plate.plate_number().to_display()))
            self.plates_table.setItem(row, 1, QTableWidgetItem(owner))
            self.plates_table.setItem(row, 2, QTableWidgetItem(plate.notes or ""))
            self.plates_table.item(row, 0).setData(Qt.UserRole, plate.id)
        self._plates_cache = plates

    def _selected_plate(self) -> PlateRecord | None:
        row = self.plates_table.currentRow()
        if row < 0 or row >= len(self._plates_cache):
            return None
        return self._plates_cache[row]

    def _add_plate(self) -> None:
        dlg = PlateFormDialog(self.db, self)
        if dlg.exec() == QDialog.Accepted:
            values = dlg.values()
            self.db.add_plate(values["plate"], person_id=values["person_id"], notes=values["notes"])
            self._reload_plates()

    def _edit_plate(self) -> None:
        plate = self._selected_plate()
        if plate is None:
            QMessageBox.information(self, "راهنما", "ابتدا یک پلاک را از فهرست انتخاب کنید.")
            return
        dlg = PlateFormDialog(self.db, self, plate=plate)
        if dlg.exec() == QDialog.Accepted:
            values = dlg.values()
            if values["plate"].to_key() != plate.plate_key:
                # the plate number itself changed: this is really a new lookup key,
                # so replace the row rather than updating it in place.
                self.db.delete_plate(plate.id)
                self.db.add_plate(values["plate"], person_id=values["person_id"], notes=values["notes"])
            else:
                self.db.update_plate(plate.id, person_id=values["person_id"], notes=values["notes"])
            self._reload_plates()

    def _delete_plate(self) -> None:
        plate = self._selected_plate()
        if plate is None:
            QMessageBox.information(self, "راهنما", "ابتدا یک پلاک را از فهرست انتخاب کنید.")
            return
        reply = QMessageBox.question(
            self, "تأیید حذف", f"آیا از حذف پلاک «{plate.plate_number().to_display()}» مطمئن هستید؟"
        )
        if reply == QMessageBox.Yes:
            self.db.delete_plate(plate.id)
            self._reload_plates()
