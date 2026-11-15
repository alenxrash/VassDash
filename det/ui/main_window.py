"""Main window: icon navigation, top bar, pages, manager lock, and the shared-folder refresh."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QByteArray, QSize, Qt, QTimer
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QInputDialog, QLineEdit, QMainWindow, QMessageBox,
                               QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from ..auth import check_passcode, hash_passcode
from ..theme import tokens
from .common import label
from .dashboard_page import DashboardPage
from .icons import SIZE, nav_icon
from .log_page import LogPage
from .projects_page import ProjectsPage
from .reports_page import ReportsPage
from .settings_page import SettingsPage

# key, label, manager only, shown at the bottom of the sidebar
NAV = [('log', 'Log time', False, False), ('dashboard', 'Dashboard', True, False),
       ('projects', 'Projects', True, False), ('reports', 'Reports', True, False),
       ('settings', 'Settings', False, True)]
TITLES = {key: text for key, text, _, _ in NAV}
MANAGER_ONLY = {key: manager for key, _, manager, _ in NAV}
SYNC_MS = 30_000


def initials(name: str) -> str:
    parts = [part for part in name.split() if part]
    return ''.join(part[0] for part in parts[:2]).upper() or '?'


class MainWindow(QMainWindow):
    def __init__(self, store, settings):
        super().__init__()
        self.store, self.settings = store, settings
        self.manager = False
        self.offline = ''
        self.current_page = 'log'
        self.setWindowTitle('Discounted Engineering Tracker')
        self.resize(1320, 860)

        root = QWidget()
        root.setObjectName('root')
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- sidebar ----
        side = QFrame()
        side.setObjectName('sidebar')
        side.setFixedWidth(214)
        column = QVBoxLayout(side)
        column.setContentsMargins(18, 26, 14, 20)
        column.setSpacing(8)
        self.brand = label('', 'appTitle')
        column.addWidget(self.brand)
        column.addSpacing(26)
        self.nav: dict[str, QPushButton] = {}
        group = QButtonGroup(self)
        bottom = []
        for key, text, _, at_bottom in NAV:
            button = QPushButton('  ' + text)
            button.setObjectName('nav')
            button.setCheckable(True)
            button.setIconSize(QSize(SIZE, SIZE))
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: self.show_page(k))
            group.addButton(button)
            self.nav[key] = button
            if at_bottom:
                bottom.append(button)
            else:
                column.addWidget(button)
        column.addStretch(1)
        for button in bottom:
            column.addWidget(button)
        self.lock = QPushButton('  Manager sign in')
        self.lock.setObjectName('nav')
        self.lock.setIconSize(QSize(SIZE, SIZE))
        self.lock.setCursor(Qt.PointingHandCursor)
        self.lock.clicked.connect(self.toggle_manager)
        column.addWidget(self.lock)
        outer.addWidget(side)

        # ---- top bar + pages ----
        main = QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(32, 20, 32, 4)
        bar.setSpacing(10)
        self.crumbs = label('', 'crumbs')
        self.role = label('', 'chip')
        self.who = label('', 'muted')
        self.avatar = label('', 'avatar')
        self.avatar.setAlignment(Qt.AlignCenter)
        bar.addWidget(self.crumbs)
        bar.addStretch(1)
        for widget in (self.role, self.who, self.avatar):
            bar.addWidget(widget)
        main.addLayout(bar)
        self.banner = label('', 'banner')
        self.banner.setWordWrap(True)
        self.banner.setVisible(False)
        holder = QVBoxLayout()
        holder.setContentsMargins(32, 8, 32, 0)
        holder.addWidget(self.banner)
        main.addLayout(holder)
        self.stack = QStackedWidget()
        main.addWidget(self.stack, 1)
        outer.addLayout(main, 1)

        self.pages = {'log': LogPage(self), 'dashboard': DashboardPage(self), 'projects': ProjectsPage(self),
                      'reports': ReportsPage(self), 'settings': SettingsPage(self)}
        for key, _, _, _ in NAV:
            self.stack.addWidget(self.pages[key])

        self._signature = store.signature()
        self.sync = QTimer(self)
        self.sync.setInterval(SYNC_MS)
        self.sync.timeout.connect(self.check_sync)
        self.sync.start()
        geometry = settings.get('geometry')
        if geometry:
            self.restoreGeometry(QByteArray.fromHex(geometry.encode('ascii')))
        self.set_manager(False)
        self.show_page('log')

    @property
    def user(self) -> str:
        return self.settings.get('user_name') or 'Unknown'

    def show_page(self, key: str) -> None:
        if not self.nav[key].isEnabled():
            key = 'log'
        self.current_page = key
        self.nav[key].setChecked(True)
        self.stack.setCurrentWidget(self.pages[key])
        today = date.today()
        self.crumbs.setText(f'Home   /   {TITLES[key]}   /   {today.day} {today:%b %Y}')

    # ---- manager gate ----------------------------------------------------------------------
    def set_manager(self, on: bool) -> None:
        self.manager = on
        for key, _, manager_only, _ in NAV:
            self.nav[key].setEnabled(on or not manager_only)
        self.lock.setText('  Lock manager view' if on else '  Manager sign in')
        if not on and MANAGER_ONLY[self.current_page]:
            self.show_page('log')
        self.refresh_pages()

    def toggle_manager(self) -> None:
        if self.manager:
            self.set_manager(False)
            return
        stored = self.store.config.passcode_hash
        if not stored:
            code, ok = QInputDialog.getText(self, 'Set manager passcode',
                                            'No passcode is set yet. Choose one (4 characters or more).\n'
                                            'It only hides the manager screens; it does not protect the data files.',
                                            QLineEdit.Password)
            if not ok:
                return
            if len(code) < 4:
                QMessageBox.warning(self, 'Passcode', 'Use at least 4 characters.')
                return
            again, ok = QInputDialog.getText(self, 'Set manager passcode', 'Repeat the passcode:', QLineEdit.Password)
            if not ok or again != code:
                QMessageBox.warning(self, 'Passcode', 'The two entries did not match. Nothing was set.')
                return
            self.store.config.passcode_hash = hash_passcode(code)
            self.store.save_config()
            self.set_manager(True)
            self.show_page('dashboard')
            return
        code, ok = QInputDialog.getText(self, 'Manager sign in', 'Passcode:', QLineEdit.Password)
        if not ok:
            return
        if check_passcode(code, stored):
            self.set_manager(True)
            self.show_page('dashboard')
        else:
            QMessageBox.warning(self, 'Manager sign in', 'That passcode is not right.')

    # ---- data ------------------------------------------------------------------------------
    def restyle(self) -> None:
        """Colours baked into icons and rich text are redrawn here, so a theme change takes effect at once."""
        for key in self.nav:
            self.nav[key].setIcon(nav_icon(key))
        self.lock.setIcon(nav_icon('unlock' if self.manager else 'lock'))
        self.brand.setText(f'<span style="color:{tokens()["accent2"]};">Discounted</span><br>Engineering')

    def refresh_pages(self) -> None:
        self.restyle()
        self.who.setText(self.user)
        self.avatar.setText(initials(self.user))
        self.role.setText('Manager view' if self.manager else 'Engineer view')
        warnings = self.store.warnings
        self.banner.setVisible(bool(warnings or self.offline))
        if self.offline:
            self.banner.setText(self.offline)
        elif warnings:
            shown = '; '.join(warnings[:3]) + (f'; and {len(warnings) - 3} more' if len(warnings) > 3 else '')
            self.banner.setText(f'{len(warnings)} file(s) in the shared folder were skipped and are not in any total. '
                                f'{shown}')
        for page in getattr(self, 'pages', {}).values():
            page.refresh()
        self._signature = self.store.signature()

    def reload(self) -> None:
        try:
            self.store.load()
            self.offline = ''
        except OSError as problem:
            # Keep showing the last data that loaded; saving will report its own error.
            self.offline = f'The shared folder cannot be reached ({problem.__class__.__name__}). Showing the last data loaded.'
        self.refresh_pages()

    def check_sync(self) -> None:
        """Pick up changes that arrived through Dropbox from other people."""
        if self.store.signature() != self._signature:
            self.reload()

    def set_store(self, store) -> None:
        self.store = store
        self.set_manager(False)

    def closeEvent(self, event) -> None:
        self.settings.set('geometry', bytes(self.saveGeometry().toHex()).decode('ascii'))
        self.pages['log'].mini.save_state()
        self.pages['log'].mini.close()
        super().closeEvent(event)
