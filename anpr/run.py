#!/usr/bin/env python3
"""Entry point for the license-plate reader app.

Usage:
    python run.py               # uses ./config.yaml (created from the example on first run)
    python run.py path/to.yaml  # uses an explicit config file
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtWidgets import QApplication  # noqa: E402

from anpr_app.config import load_config  # noqa: E402
from anpr_app.database.db import Database  # noqa: E402
from anpr_app.gui.main_window import MainWindow  # noqa: E402
from anpr_app.gui.style import apply_app_style  # noqa: E402


def resolve_config_path() -> Path:
    project_root = Path(__file__).parent
    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
        if not path.exists():
            print(f"فایل تنظیمات یافت نشد: {path}")
            sys.exit(1)
        return path

    path = project_root / "config.yaml"
    if not path.exists():
        example = project_root / "config.example.yaml"
        shutil.copyfile(example, path)
        print(f"فایل تنظیمات ساخته شد: {path}")
        print("پیش از اجرای بعدی، آدرس دوربین و سایر تنظیمات را در این فایل ویرایش کنید.")
    return path


def main() -> None:
    config = load_config(resolve_config_path())
    db = Database(config.paths.database)

    app = QApplication(sys.argv)
    apply_app_style(app)
    window = MainWindow(config, db)
    window.show()
    exit_code = app.exec()

    db.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
