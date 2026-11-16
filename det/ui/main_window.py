"""VassDash main window: a top bar with three tabs, and the pieces that outlive it.

The timer controller, the desktop widget and the tray icon are owned here but do not depend on the
window being visible. Closing the window only hides it; the timer keeps running. Quit from the tray
icon or the widget's right-click menu.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QApplication, QButtonGroup, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QMainWindow, QMenu, QMessageBox, QPushButton, QStackedWidget, QSystemTrayIcon,
                               QVBoxLayout, QWidget)

from .. import autostart, locate
from ..models import Project
from ..store import Store
from ..theme import tokens
from . import brand
from .common import label
from .controller import TimerController
from .dashboard_page import DashboardPage
from .reports_page import ReportsPage
from .settings_page import SettingsPage
from .time_page import TimePage
from .timer_widget import TimerWidget

NAV = [('time', 'My time'), ('dashboard', 'Dashboard'), ('reports', 'Reports')]
SYNC_MS = 30_000


def initials(name: str) -> str:
    parts = [part for part in name.split() if part]
    return ''.join(part[0] for part in parts[:2]).upper() or '?'


def ask(title: str, text: str, parent=None) -> bool:
    return QMessageBox.question(parent, title, text) == QMessageBox.Yes


class MainWindow(QMainWindow):
    def __init__(self, store, settings, location: locate.Location | None = None):
        super().__init__()
        self.store, self.settings = store, settings
        self.location = location or locate.Location(Path(store.directory), True)
        self.offline = ''
        self.confirm = ask                        # replaced in tests so no dialog blocks
        self.current_page = 'time'
        self._quitting = False
        self.setWindowTitle(f'{brand.NAME}  ·  {brand.TAGLINE}')
        self.setWindowIcon(brand.app_icon())
        self.resize(1240, 820)
        self.controller = TimerController(self)

        root = QWidget()
        root.setObjectName('root')
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- top bar: brand, tabs, timer, settings, who ----
        bar_frame = QFrame()
        bar_frame.setObjectName('topbar')
        bar_frame.setFixedHeight(66)
        bar = QHBoxLayout(bar_frame)
        bar.setContentsMargins(24, 0, 24, 0)
        bar.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(brand.mark(34))
        self.brand = label('', 'appTitle')
        bar.addWidget(logo)
        bar.addWidget(self.brand)
        bar.addSpacing(26)
        self.nav: dict[str, QPushButton] = {}
        group = QButtonGroup(self)
        for key, text in NAV:
            button = QPushButton(text)
            button.setObjectName('tab')
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: self.show_page(k))
            group.addButton(button)
            self.nav[key] = button
            bar.addWidget(button)
        bar.addStretch(1)
        self.timer_button = QPushButton('Timer')
        self.timer_button.setToolTip('Show the desktop timer widget')
        self.timer_button.clicked.connect(lambda: self.widget.set_shown(True))
        self.settings_button = QPushButton('Settings')
        self.settings_button.clicked.connect(self.open_settings)
        self.who = label('', 'muted')
        self.avatar = label('', 'avatar')
        self.avatar.setAlignment(Qt.AlignCenter)
        for widget in (self.timer_button, self.settings_button, self.who, self.avatar):
            bar.addWidget(widget)
        outer.addWidget(bar_frame)

        # ---- notices ----
        holder = QVBoxLayout()
        holder.setContentsMargins(32, 10, 32, 0)
        holder.setSpacing(8)
        self.banner = label('', 'banner')
        self.banner.setWordWrap(True)
        self.banner.setVisible(False)
        self.local_box = QFrame()
        self.local_box.setObjectName('noteBox')
        row = QHBoxLayout(self.local_box)
        row.setContentsMargins(14, 8, 10, 8)
        self.local_note = label('')
        self.local_note.setWordWrap(True)
        self.connect_button = QPushButton('Choose folder…')
        self.connect_button.clicked.connect(self.choose_folder)
        row.addWidget(self.local_note, 1)
        row.addWidget(self.connect_button)
        self.local_box.setVisible(False)
        holder.addWidget(self.banner)
        holder.addWidget(self.local_box)
        outer.addLayout(holder)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self.widget = TimerWidget(self, self.controller)
        self.pages = {'time': TimePage(self), 'dashboard': DashboardPage(self), 'reports': ReportsPage(self)}
        for key, _ in NAV:
            self.stack.addWidget(self.pages[key])

        self.tray = self._make_tray()
        # Signing out of or shutting down Windows must not be held up by the hide-on-close behaviour below.
        QApplication.instance().commitDataRequest.connect(self._session_ending)
        self.controller.changed.connect(self.update_timer_views)
        self.controller.saved.connect(lambda _entry: self.refresh_pages())
        self._signature = store.signature()
        self.sync = QTimer(self)
        self.sync.setInterval(SYNC_MS)
        self.sync.timeout.connect(self.check_sync)
        self.sync.start()
        geometry = settings.get('geometry')
        if geometry:
            self.restoreGeometry(QByteArray.fromHex(geometry.encode('ascii')))
        self.refresh_pages()
        self.show_page('time')

    # ---- who and where ----------------------------------------------------------------------
    @property
    def user(self) -> str:
        return self.settings.get('user_name') or locate.default_user_name()

    def show_page(self, key: str) -> None:
        self.current_page = key
        self.nav[key].setChecked(True)
        self.stack.setCurrentWidget(self.pages[key])

    def show_main(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def open_settings(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle('Settings')
        dialog.setMinimumSize(760, 620)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 12)
        self.settings_view = SettingsPage(self)
        layout.addWidget(self.settings_view)
        row = QHBoxLayout()
        row.setContentsMargins(32, 0, 32, 0)
        row.addStretch(1)
        close = QPushButton('Close')
        close.clicked.connect(dialog.accept)
        row.addWidget(close)
        layout.addLayout(row)
        dialog.exec()
        self.settings_view = None

    def choose_folder(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, 'Team data folder', str(self.store.directory))
        if chosen and Path(chosen).is_dir():
            self.use_folder(chosen)

    def use_folder(self, chosen) -> None:
        """Switch to a folder picked by hand, taking along anything saved on this PC."""
        merged = 0
        if not self.location.shared and Path(chosen) != Path(self.store.directory):
            merged = locate.merge(self.store.directory, chosen)
        store = Store(chosen)
        try:
            store.load()
        except OSError as problem:
            QMessageBox.warning(self, 'Folder', f'That folder could not be opened.\n\n{problem}')
            return
        self.settings.data.update(shared_dir=str(chosen), data_mode='shared')
        self.settings.save()
        self.location = locate.Location(Path(chosen), True, merged)
        self.set_store(store)

    def ensure_project(self, combo, parent=None):
        """The picked project's id. A name that is not in the list can be created on the spot."""
        project_id = combo.project_id()
        if project_id:
            return project_id
        name = combo.currentText().strip()
        if not name:
            return None
        if not self.confirm('New project', f'"{name}" is not in the list.\n\nCreate it as a new project?', parent or self):
            return None
        project = Project(name=name, created_by=self.user, lead_engineer=self.user)
        try:
            self.store.save_project(project, new=True)
        except (ValueError, OSError) as problem:
            QMessageBox.warning(parent or self, 'New project', f'The project could not be created.\n\n{problem}')
            return None
        self.refresh_pages()
        combo.set_project(project.id)
        return project.id

    # ---- tray, widget, quitting -------------------------------------------------------------
    def _make_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return None
        tray = QSystemTrayIcon(brand.app_icon(), self)
        tray.setToolTip(brand.NAME)
        menu = QMenu()
        menu.addAction(f'Open {brand.NAME}', self.show_main)
        menu.addAction('Show timer widget', lambda: self.widget.set_shown(True))
        if autostart.supported():
            start = QAction('Start with Windows', menu, checkable=True)
            start.setChecked(autostart.is_enabled())
            start.toggled.connect(autostart.set_enabled)
            menu.addAction(start)
        menu.addSeparator()
        menu.addAction('Quit', self.quit_app)
        tray.setContextMenu(menu)
        self._tray_menu = menu
        tray.activated.connect(lambda reason: self.show_main() if reason == QSystemTrayIcon.Trigger else None)
        tray.show()
        return tray

    def widget_visibility_changed(self) -> None:
        """Never leave the app running with nothing on screen and no tray icon to reach it."""
        if not self.widget.shown and self.tray is None and not self.isVisible():
            self.show_main()
        self.update_timer_views()

    def update_timer_views(self) -> None:
        c = self.controller
        self.timer_button.setText(f'●  {c.elapsed_text()}' if c.running else f'Paused  {c.elapsed_text()}' if c.active else 'Timer')
        self.timer_button.setObjectName('primary' if c.active else '')
        self.timer_button.style().unpolish(self.timer_button)
        self.timer_button.style().polish(self.timer_button)
        self.pages['time'].update_timer_view()
        if self.tray:
            self.tray.setToolTip(f'{brand.NAME}: {c.project_name} {c.elapsed_text()}' if c.active else brand.NAME)

    def _session_ending(self, *_) -> None:
        self._quitting = True
        self.settings.set('geometry', bytes(self.saveGeometry().toHex()).decode('ascii'))
        self.widget.save_state()

    def shutdown(self) -> None:
        """Save state and close everything this window owns."""
        self._quitting = True
        self.settings.set('geometry', bytes(self.saveGeometry().toHex()).decode('ascii'))
        self.widget.save_state()
        self.controller.ticker.stop()
        self.sync.stop()
        self.widget.close()
        if self.tray:
            self.tray.hide()
        self.close()

    def quit_app(self) -> None:
        self.shutdown()
        QApplication.quit()

    def closeEvent(self, event) -> None:
        if self._quitting:
            super().closeEvent(event)
            return
        self.settings.set('geometry', bytes(self.saveGeometry().toHex()).decode('ascii'))
        if self.tray is None and not self.widget.shown:
            self.quit_app()                        # nothing would be left to reach the app with
            return
        event.ignore()                             # keep the timer alive: hide instead of closing
        self.hide()

    # ---- data ------------------------------------------------------------------------------
    def refresh_pages(self) -> None:
        self.brand.setText(f'{brand.NAME}<br><span style="color:{tokens()["text_faint"]}; font-size:11px; '
                           f'font-weight:400;">{brand.TAGLINE}</span>')
        self.who.setText(self.user)
        self.avatar.setText(initials(self.user))
        warnings = self.store.warnings
        self.banner.setVisible(bool(warnings or self.offline))
        if self.offline:
            self.banner.setText(self.offline)
        elif warnings:
            shown = '; '.join(warnings[:3]) + (f'; and {len(warnings) - 3} more' if len(warnings) > 3 else '')
            self.banner.setText(f'{len(warnings)} file(s) in the data folder were skipped and are not in any total. '
                                f'{shown}')
        local = not self.location.shared
        self.local_box.setVisible(local or self.location.merged > 0)
        self.connect_button.setVisible(local)
        if local:
            self.local_note.setText(f'The team folder "{locate.DATA_FOLDER}" was not found in Dropbox on this PC, so your '
                                    f'time is being saved here only. It moves across by itself once the folder appears.')
        elif self.location.merged:
            self.local_note.setText(f'Connected to the team folder. {self.location.merged} record(s) saved on this PC '
                                    f'were moved into it.')
        for page in getattr(self, 'pages', {}).values():
            page.refresh()
        if getattr(self, 'settings_view', None):
            self.settings_view.refresh()
        self.widget.refresh(self.store)
        self.update_timer_views()
        self._signature = self.store.signature()

    def reload(self) -> None:
        try:
            self.store.load()
            self.offline = ''
        except OSError as problem:
            # Keep showing the last data that loaded; saving will report its own error.
            self.offline = f'The data folder cannot be reached ({problem.__class__.__name__}). Showing the last data loaded.'
        self.refresh_pages()

    def check_sync(self) -> None:
        """Pick up changes that arrived through Dropbox from other people."""
        if self.store.signature() != self._signature:
            self.reload()

    def set_store(self, store) -> None:
        self.store = store
        self.refresh_pages()
