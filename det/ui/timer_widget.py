"""Desktop timer widget: a small window of its own that sits on the Windows desktop.

It is separate from the main window. Closing the main window leaves the widget (and the timer)
running; the tray icon or the widget's menu brings the main window back or quits.

Notes on the Qt behaviour this relies on:
- It is a frameless tool window, optionally always on top. Changing window flags hides a window,
  so it is shown again after every change.
- It is opaque with square corners. Rounded corners would need a translucent top-level window, which
  has a history of not appearing on Windows for frameless tool windows.
- Moving and resizing are done here from the mouse events, which the tests exercise.

This is a desktop widget. It is not a Windows 11 Widgets-board widget: those must be shipped as a
packaged (MSIX) app with a widget provider, which a single .exe cannot be.
"""
from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QAction, QFont, QFontMetrics, QGuiApplication
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QInputDialog, QLabel, QMenu, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from .common import ProjectCombo

EDGE = 8                       # width of the resize border, in pixels
MIN_W, MIN_H = 280, 116
DEFAULT_W, DEFAULT_H = 360, 140
MARGIN = 24                    # default gap from the bottom-right corner of the screen
KEY = 'timer_widget'
MIN_CLOCK_PX = 18

CURSORS = {
    Qt.LeftEdge: Qt.SizeHorCursor, Qt.RightEdge: Qt.SizeHorCursor,
    Qt.TopEdge: Qt.SizeVerCursor, Qt.BottomEdge: Qt.SizeVerCursor,
    Qt.LeftEdge | Qt.TopEdge: Qt.SizeFDiagCursor, Qt.RightEdge | Qt.BottomEdge: Qt.SizeFDiagCursor,
    Qt.RightEdge | Qt.TopEdge: Qt.SizeBDiagCursor, Qt.LeftEdge | Qt.BottomEdge: Qt.SizeBDiagCursor,
}


class TimerWidget(QFrame):
    def __init__(self, win, controller):
        super().__init__(None)
        self.win, self.controller = win, controller
        self.setObjectName('timerWidget')
        self.setWindowTitle('VassDash timer')
        self.setMouseTracking(True)
        self.setMinimumSize(MIN_W, MIN_H)
        self.shown = True
        self.on_top = True
        self.rect_saved: list | None = None        # x, y, width, height on the screen
        self.elapsed_px = 0
        self._press = None                         # (edges, global start point, start geometry)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 14, 12)
        layout.setSpacing(4)
        head = QHBoxLayout()
        head.setSpacing(2)
        self.title = QLabel('Timer')
        self.title.setObjectName('muted')
        self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.open_button = QPushButton('Open')
        self.open_button.setToolTip('Open the VassDash window')
        self.open_button.clicked.connect(win.show_main)
        self.hide_button = QPushButton('Hide')
        self.hide_button.setToolTip('Hide the widget. Bring it back from the tray icon or the VassDash window.')
        self.hide_button.clicked.connect(lambda: self.set_shown(False))
        for button in (self.open_button, self.hide_button):
            button.setObjectName('mini')
            button.setCursor(Qt.PointingHandCursor)
        head.addWidget(self.title, 1)
        head.addWidget(self.open_button)
        head.addWidget(self.hide_button)
        layout.addLayout(head)

        self.running_box = QWidget()
        row = QHBoxLayout(self.running_box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.elapsed = QLabel('0:00:00')
        self.elapsed.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.pause = QPushButton('Pause')
        self.pause.setMinimumWidth(88)             # wide enough for "Resume", so the buttons never squash
        self.pause.clicked.connect(controller.toggle_pause)
        self.stop = QPushButton('Stop')
        self.stop.setObjectName('primary')
        self.stop.setMinimumWidth(66)
        self.stop.setToolTip('Stop and save the time')
        self.stop.clicked.connect(self.stop_clicked)
        row.addWidget(self.elapsed, 1)
        row.addWidget(self.pause)
        row.addWidget(self.stop)
        layout.addWidget(self.running_box, 1)

        self.idle_box = QWidget()
        row = QHBoxLayout(self.idle_box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.project = ProjectCombo(win.store)
        self.project.setMinimumWidth(80)
        self.project.lineEdit().returnPressed.connect(self.start_clicked)
        self.start = QPushButton('Start')
        self.start.setObjectName('primary')
        self.start.clicked.connect(self.start_clicked)
        row.addWidget(self.project, 1)
        row.addWidget(self.start)
        layout.addWidget(self.idle_box, 1)
        self.running_box.setVisible(False)

        controller.changed.connect(self.update_view)
        self._restore()
        self.update_view()

    # ---- state ------------------------------------------------------------------------------
    def _restore(self) -> None:
        saved = self.win.settings.get(KEY) or {}
        try:
            rect = saved.get('rect') or saved.get('float')         # 'float' was revision 3's name
            if rect and len(rect) == 4:
                self.rect_saved = [int(v) for v in rect]
            self.shown = bool(saved.get('shown', True))
            self.on_top = bool(saved.get('on_top', True))
        except (TypeError, ValueError, AttributeError):
            self.rect_saved = None
        self._apply_flags()

    def save_state(self) -> None:
        self.win.settings.set(KEY, {'shown': self.shown, 'on_top': self.on_top, 'rect': self.rect_saved})

    def _default_rect(self) -> QRect:
        screen = QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRect(0, 0, 1280, 720)
        return QRect(area.right() + 1 - DEFAULT_W - MARGIN, area.bottom() + 1 - DEFAULT_H - MARGIN, DEFAULT_W, DEFAULT_H)

    def _apply_flags(self) -> None:
        flags = Qt.Tool | Qt.FramelessWindowHint
        if self.on_top:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.place(QRect(*self.rect_saved) if self.rect_saved else self._default_rect())
        self.setVisible(self.shown)                # changing flags hides the window, so show it again

    def set_on_top(self, on: bool) -> None:
        self.on_top = on
        self._apply_flags()
        self.save_state()

    def set_shown(self, on: bool) -> None:
        self.shown = on
        self.setVisible(on)
        if on:
            self.raise_()
        self.save_state()
        self.win.widget_visibility_changed()

    # ---- geometry -----------------------------------------------------------------------------
    def place(self, rect: QRect) -> None:
        """Move and size the widget, kept fully on a screen."""
        screen = QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()
        bounds = screen.availableGeometry() if screen else rect
        width = max(MIN_W, min(rect.width(), max(MIN_W, bounds.width())))
        height = max(MIN_H, min(rect.height(), max(MIN_H, bounds.height())))
        x = max(bounds.left(), min(rect.x(), bounds.right() + 1 - width))
        y = max(bounds.top(), min(rect.y(), bounds.bottom() + 1 - height))
        self.setGeometry(x, y, width, height)
        self.rect_saved = [x, y, width, height]

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_clock()

    def _fit_clock(self) -> None:
        """Scale the clock with the widget: as tall as the height allows, shrunk until the digits fit the width."""
        margins = self.layout().contentsMargins()
        room = self.width() - margins.left() - margins.right() - self.pause.minimumWidth() - self.stop.minimumWidth() - 24
        text = self.elapsed.text() if len(self.elapsed.text()) > 7 else '0:00:00'
        px = int(max(MIN_CLOCK_PX, min(self.height() * 0.36, 160)))
        font = QFont(self.font())
        font.setWeight(QFont.DemiBold)
        while px > MIN_CLOCK_PX:
            font.setPixelSize(px)
            if QFontMetrics(font).horizontalAdvance(text) <= room:
                break
            px -= 1
        if px != self.elapsed_px:
            self.elapsed_px = px
            self.elapsed.setStyleSheet(f'font-size: {px}px; font-weight: 600;')

    # ---- drag to move, drag an edge to resize ---------------------------------------------------
    def _edges_at(self, pos) -> Qt.Edges:
        edges = Qt.Edges()
        if pos.x() < EDGE:
            edges |= Qt.LeftEdge
        elif pos.x() >= self.width() - EDGE:
            edges |= Qt.RightEdge
        if pos.y() < EDGE:
            edges |= Qt.TopEdge
        elif pos.y() >= self.height() - EDGE:
            edges |= Qt.BottomEdge
        return edges

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._press = (self._edges_at(event.position().toPoint()), event.globalPosition().toPoint(), self.geometry())
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._press is None:
            edges = self._edges_at(event.position().toPoint())
            self.setCursor(CURSORS.get(edges, Qt.SizeAllCursor) if edges else Qt.ArrowCursor)
            return
        edges, start, origin = self._press
        delta = event.globalPosition().toPoint() - start
        rect = QRect(origin)
        if not edges:
            rect.translate(delta)
        else:
            if edges & Qt.LeftEdge:
                rect.setLeft(min(origin.left() + delta.x(), origin.right() - MIN_W + 1))
            if edges & Qt.RightEdge:
                rect.setRight(max(origin.right() + delta.x(), origin.left() + MIN_W - 1))
            if edges & Qt.TopEdge:
                rect.setTop(min(origin.top() + delta.y(), origin.bottom() - MIN_H + 1))
            if edges & Qt.BottomEdge:
                rect.setBottom(max(origin.bottom() + delta.y(), origin.top() + MIN_H - 1))
        self.place(rect)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self._press is not None:
            self._press = None
            self.save_state()
            event.accept()

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        menu.addAction('Open VassDash', self.win.show_main)
        pin = QAction('Always on top', menu, checkable=True)
        pin.setChecked(self.on_top)
        pin.toggled.connect(self.set_on_top)
        menu.addAction(pin)
        menu.addAction('Hide widget', lambda: self.set_shown(False))
        menu.addSeparator()
        menu.addAction('Quit VassDash', self.win.quit_app)
        menu.exec(event.globalPos())

    # ---- timer controls -----------------------------------------------------------------------
    def start_clicked(self) -> None:
        project_id = self.win.ensure_project(self.project, self)
        if project_id:
            self.controller.start(project_id)
        else:
            self.controller.message = 'Choose a project first'
            self.update_view()

    def stop_clicked(self) -> None:
        hours = None
        if self.controller.is_long():
            measured = self.controller.hours()
            hours, ok = QInputDialog.getDouble(
                self, 'Long timer', f'This timer ran for {measured:.1f} hours. Was it left running?\n'
                'Hours to save:', min(measured, 24.0), 0.02, 24.0, 2)
            if not ok:
                return
        self.controller.stop(hours)

    def refresh(self, store) -> None:
        self.project.reload(store)

    def update_view(self) -> None:
        c = self.controller
        if c.active:
            label = c.project_name if c.running else f'{c.project_name}  ·  paused'
            if c.message:
                label = c.message
        else:
            label = c.message or 'Timer'
        self.title.setText(self.title.fontMetrics().elidedText(label, Qt.ElideRight, max(40, self.title.width())))
        self.title.setToolTip(label)
        text = c.elapsed_text()
        if len(text) != len(self.elapsed.text()):
            self.elapsed.setText(text)
            self._fit_clock()                      # ten hours and over needs one more digit
        self.elapsed.setText(text)
        self.pause.setText('Pause' if c.running else 'Resume')
        self.running_box.setVisible(c.active)
        self.idle_box.setVisible(not c.active)
