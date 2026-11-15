"""Discounted Engineering Tracker. Run with: python app.py"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from det.settings import Settings, default_path
from det.store import Store
from det.theme import apply_theme
from det.ui.dialogs import FirstRunDialog
from det.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName('Discounted Engineering Tracker')
    settings = Settings(default_path())
    settings.load()
    apply_theme(app, settings.get('theme') or 'dark')
    folder = settings.get('shared_dir')
    if not settings.get('user_name') or not folder or not Path(folder).is_dir():
        if not FirstRunDialog(settings).exec():
            return 0
    store = Store(settings.get('shared_dir'))
    try:
        store.load()
    except OSError as problem:
        QMessageBox.critical(None, 'Shared folder', f'The shared folder could not be opened.\n\n{problem}')
        return 1
    window = MainWindow(store, settings)
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
