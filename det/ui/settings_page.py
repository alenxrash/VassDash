"""Settings: personal (name, theme, start with Windows, data folder) and shared (rate, lists, Excel import)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget)

from .. import autostart, importer
from ..theme import apply_theme
from .common import Hero, card, label
from .dialogs import ImportDialog

MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
          'November', 'December']


class SettingsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 22, 32, 12)
        layout.setSpacing(18)
        self.hero = Hero('Settings', '', 'Nothing here is needed to start. Personal settings stay on this computer; shared settings apply to everyone.')
        layout.addWidget(self.hero)

        frame, box = card('This computer')
        form = QFormLayout()
        self.name = QLineEdit()
        self.folder = label('', 'muted')
        self.folder.setWordWrap(True)
        change = QPushButton('Change…')
        change.clicked.connect(win.choose_folder)
        row = QHBoxLayout()
        row.addWidget(self.folder, 1)
        row.addWidget(change)
        self.theme = QComboBox()
        self.theme.addItems(['dark', 'light'])
        self.autostart = QCheckBox('Start the timer widget when I sign in to Windows')
        self.autostart.setEnabled(autostart.supported())
        self.autostart.setChecked(autostart.is_enabled())
        self.autostart.toggled.connect(autostart.set_enabled)
        form.addRow('Your name', self.name)
        form.addRow('Theme', self.theme)
        form.addRow('', self.autostart)
        form.addRow('Data folder', row)
        box.addLayout(form)
        hint = label('Your name comes from Windows and is stored on each entry you log. Changing it does not rename '
                     'past entries. The data folder is found by itself; change it only if it is wrong.', 'faint')
        box.addWidget(hint)
        save = QPushButton('Save')
        save.setObjectName('primary')
        save.clicked.connect(self.save_personal)
        row = QHBoxLayout()
        row.addWidget(save)
        row.addStretch(1)
        box.addLayout(row)
        layout.addWidget(frame)

        self.shared_card, box = card('Shared settings (apply to everyone)')
        form = QFormLayout()
        self.rate = QDoubleSpinBox()
        self.rate.setRange(0.0, 100000.0)
        self.rate.setDecimals(2)
        self.rate.setPrefix('$ ')
        self.fy = QComboBox()
        self.fy.addItems(MONTHS)
        self.regions = QLineEdit()
        self.reasons = QLineEdit()
        form.addRow('Rate per hour', self.rate)
        form.addRow('Financial year starts', self.fy)
        form.addRow('Regions (comma separated)', self.regions)
        form.addRow('Reason categories', self.reasons)
        box.addLayout(form)
        row = QHBoxLayout()
        save_shared = QPushButton('Save shared settings')
        save_shared.setObjectName('primary')
        save_shared.clicked.connect(self.save_shared)
        excel = QPushButton('Import from Excel…')
        excel.clicked.connect(self.import_excel)
        for button in (save_shared, excel):
            row.addWidget(button)
        row.addStretch(1)
        box.addLayout(row)
        self.shared_status = label('', 'muted')
        box.addWidget(self.shared_status)
        layout.addWidget(self.shared_card)
        layout.addStretch(1)
        self.refresh()

    def refresh(self) -> None:
        self.hero.restyle()
        settings, config = self.win.settings, self.win.store.config
        if not self.name.hasFocus():
            self.name.setText(self.win.user)
        where = 'team folder, found automatically or chosen here' if self.win.location.shared else 'this PC only'
        self.folder.setText(f'{self.win.store.directory}   ({where})')
        self.theme.setCurrentText(settings.get('theme') or 'dark')
        if not any(w.hasFocus() for w in (self.rate, self.regions, self.reasons)):
            self.rate.setValue(config.rate)
            self.fy.setCurrentIndex(max(0, min(11, config.fy_start_month - 1)))
            self.regions.setText(', '.join(config.regions))
            self.reasons.setText(', '.join(config.reason_categories))

    def save_personal(self) -> None:
        name = self.name.text().strip()
        if not name:
            QMessageBox.warning(self, 'Name needed', 'Enter your name.')
            return
        self.win.settings.data.update(user_name=name, theme=self.theme.currentText())
        self.win.settings.save()
        apply_theme(QApplication.instance(), self.theme.currentText())
        self.win.refresh_pages()

    def save_shared(self) -> None:
        config = self.win.store.config
        split = lambda text: [part.strip() for part in text.split(',') if part.strip()]
        config.rate = self.rate.value()
        config.fy_start_month = self.fy.currentIndex() + 1
        config.regions = [r.upper() for r in split(self.regions.text())]
        config.reason_categories = split(self.reasons.text()) or ['Other']
        self.win.store.save_config()
        self.shared_status.setText('Shared settings saved.')
        self.win.refresh_pages()

    def import_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, 'Discounted Engineering workbook', '', 'Excel workbook (*.xlsx *.xlsm)')
        if not path:
            return
        try:
            rows = importer.read_sheet(path)
        except Exception as problem:                       # unreadable or unexpected workbook
            QMessageBox.warning(self, 'Import', f'This workbook could not be read.\n\n{problem}')
            return
        if not rows:
            QMessageBox.information(self, 'Import', 'No rows were found under the header.')
            return
        existing = len(self.win.store.live_projects())
        if existing and QMessageBox.question(
                self, 'Import', f'There are already {existing} project(s). Importing adds {len(rows)} more and does '
                'not check for duplicates. Continue?') != QMessageBox.Yes:
            return
        dialog = ImportDialog(self.win, rows)
        if dialog.exec():
            projects, entries = dialog.created
            self.shared_status.setText(f'Imported {projects} project(s) and {entries} opening balance(s).')
        self.win.refresh_pages()
