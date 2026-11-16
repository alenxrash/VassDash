"""Budget Tracker: discounted engineering tracker.

    python app.py            open the window and the desktop timer widget
    python app.py --widget   open only the widget (used by "Start with Windows")

There is no setup step. The person's name comes from Windows and the team data folder is found in
Dropbox automatically (see det/locate.py). Only one copy runs at a time: starting it again brings the
running copy's window forward.
"""
from __future__ import annotations

import sys

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from det import autostart, locate
from det.settings import Settings, default_path
from det.store import Store
from det.theme import apply_theme
from det.ui import brand
from det.ui.main_window import MainWindow

INSTANCE = 'BudgetTracker-single-instance'


def already_running() -> bool:
    """Ask a running copy to show its window. True if one answered."""
    socket = QLocalSocket()
    socket.connectToServer(INSTANCE)
    if not socket.waitForConnected(300):
        return False
    socket.write(b'show')
    socket.waitForBytesWritten(300)
    socket.disconnectFromServer()
    return True


def main(argv=None) -> int:
    argv = sys.argv if argv is None else argv
    app = QApplication(argv)
    app.setApplicationName(brand.NAME)
    app.setQuitOnLastWindowClosed(False)           # the widget and tray keep the app alive
    if already_running():
        return 0
    autostart.migrate_legacy()
    settings = Settings(default_path())
    settings.load()
    apply_theme(app, settings.get('theme') or 'dark')
    app.setWindowIcon(brand.app_icon())
    location = locate.resolve(settings)
    store = Store(location.path)
    try:
        store.load()
    except OSError as problem:
        QMessageBox.critical(None, brand.NAME, f'The data folder could not be opened.\n\n{location.path}\n\n{problem}')
        return 1
    window = MainWindow(store, settings, location)

    QLocalServer.removeServer(INSTANCE)            # clear a stale name left by a crash
    server = QLocalServer(app)
    server.newConnection.connect(lambda: (server.nextPendingConnection(), window.show_main()))
    server.listen(INSTANCE)

    widget_only = '--widget' in argv[1:]
    if widget_only:
        window.widget.set_shown(True)              # started with Windows: just the widget
    else:
        window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
