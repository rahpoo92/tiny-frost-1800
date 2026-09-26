from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

FONT_FAMILIES = ["Vazirmatn", "Tahoma", "Segoe UI", "Arial"]

STYLE_QSS = """
QWidget { background: #10151c; color: #e6edf3; }
QMainWindow { background: #10151c; }
QLabel#videoLabel { background: #000000; border: 2px solid #263140; border-radius: 6px; color: #6b7788; }
QLabel#sectionTitle { font-weight: bold; font-size: 15px; padding: 4px 0; }
QListWidget, QTableWidget { background: #161b22; color: #e6edf3; border: 1px solid #263140; font-size: 13px; gridline-color: #263140; }
QListWidget::item { padding: 8px; border-bottom: 1px solid #21262d; }
QHeaderView::section { background: #1c2129; color: #9fb0c3; padding: 6px; border: none; }
QPushButton { background: #2563eb; color: white; border: none; border-radius: 6px; padding: 8px 16px; }
QPushButton:hover { background: #1d4ed8; }
QPushButton:disabled { background: #33445c; color: #7c8aa0; }
QPushButton#dangerButton { background: #b3261e; }
QPushButton#dangerButton:hover { background: #8f1e17; }
QComboBox, QLineEdit, QSpinBox { background: #1c2129; border: 1px solid #33445c; border-radius: 4px; padding: 6px; color: #e6edf3; }
QStatusBar { color: #9fb0c3; }
QTabWidget::pane { border: 1px solid #263140; }
QTabBar::tab { background: #1c2129; padding: 8px 16px; color: #9fb0c3; }
QTabBar::tab:selected { background: #2563eb; color: white; }
"""


def apply_app_style(app: QApplication) -> None:
    app.setLayoutDirection(Qt.RightToLeft)
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPointSize(10)
    app.setFont(font)
    app.setStyleSheet(STYLE_QSS)
