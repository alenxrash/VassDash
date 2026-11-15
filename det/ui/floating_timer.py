"""Floating timer widget.

Docked, it floats over every page inside the main window. Detached, it is its own frameless,
always-on-top window that stays visible while other programs are in front. In both states it can be
dragged by its body and resized from any edge or corner, and it offers start, pause, resume and stop.

Notes from the Qt behaviour this relies on:
- Changing a widget's parent or window flags hides it, so it is shown again after every switch.
- Moving and resizing are done here from the mouse events rather than handed to the system, so the
  docked and detached states share one code path that the tests exercise.
- The detached window is deliberately opaque with square corners. Rounded corners would need a
  translucent top-level window, which has a history of not appearing on Windows for frameless tool windows.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, Qt
from PySide6.QtGui import QFont, QFontMetrics, QGuiApplication
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from .common import ProjectCombo

EDGE = 8                       # width of the resize border, in pixels
MIN_W, MIN_H = 280, 116
DEFAULT_W, DEFAULT_H = 360, 140
MARGIN = 24                    # default gap from the window's bottom-right corner
KEY = 'timer_widget'
MIN_CLOCK_PX = 18

CURSORS = {
    Qt.LeftEdge: Qt.SizeHorCursor, Qt.RightEdge: Qt.SizeHorCursor,
    Qt.TopEdge: Qt.SizeVerCursor, Qt.BottomEdge: Qt.SizeVerCursor,
    Qt.LeftEdge | Qt.TopEdge: Qt.SizeFDiagCursor, Qt.RightEdge | Qt.BottomEdge: Qt.SizeFDiagCursor,
    Qt.RightEdge | Qt.TopEdge: Qt.SizeBDiagCursor, Qt.LeftEdge | Qt.BottomEdge: Qt.SizeBDiagCursor,
}


class FloatingTimer(QFrame):
    def __init__(self, page, host: QWidget):
        super().__init__(host)
        self.page, self.host = page, host
        self.setObjectName('floatTimer')
        self.setWindowTitle('Timer')
        self.setMouseTracking(True)
        self.setMinimumSize(MIN_W, MIN_H)
        self.detached = False
        self.shown = True
        self.dock = [MARGIN, MARGIN, DEFAULT_W, DEFAULT_H]     # gap to right edge, gap to bottom edge, width, height
        self.float_rect: list | None = None                    # x, y, width, height on the screen
        self.elapsed_px = 0
        self.hint = ''
        self._press = None                                     # (edges, global start point, start geometry)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 14, 12)
        layout.setSpacing(4)
        head = QHBoxLayout()
        head.setSpacing(2)
        self.title = QLabel('Timer')
        self.title.setObjectName('muted')
        self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.detach = QPushButton('Detach')
        self.detach.setToolTip('Detach into its own always-on-top window, or dock it back into the app')
        self.detach.clicked.connect(lambda: self.set_detached(not self.detached))
        self.hide_button = QPushButton('Hide')
        self.hide_button.setToolTip('Hide the widget. Bring it back from Log time.')
        self.hide_button.clicked.connect(lambda: self.set_shown(False))
        for button in (self.detach, self.hide_button):
            button.setObjectName('mini')
            button.setCursor(Qt.PointingHandCursor)
        head.addWidget(self.title, 1)
        head.addWidget(self.detach)
        head.addWidget(self.hide_button)
        layout.addLayout(head)

        self.running_box = QWidget()
        row = QHBoxLayout(self.running_box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.elapsed = QLabel('0:00:00')
        self.pause = QPushButton('Pause')
        self.pause.clicked.connect(page.toggle_pause)
        self.stop = QPushButton('Stop')
        self.stop.setObjectName('primary')
        self.stop.setToolTip('Stop and save the time as an entry')
        self.stop.clicked.connect(page.stop_clicked)
        self.elapsed.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.pause.setMinimumWidth(88)            # wide enough for "Resume", so the buttons never squash
        self.stop.setMinimumWidth(66)
        row.addWidget(self.elapsed, 1)
        row.addWidget(self.pause)
        row.addWidget(self.stop)
        layout.addWidget(self.running_box, 1)

        self.idle_box = QWidget()
        row = QHBoxLayout(self.idle_box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.project = ProjectCombo(page.win.store)
        self.project.setMinimumWidth(80)
        self.project.editTextChanged.connect(self._clear_hint)
        self.start = QPushButton('Start')
        self.start.setObjectName('primary')
        self.start.clicked.connect(self._start)
        row.addWidget(self.project, 1)
        row.addWidget(self.start)
        layout.addWidget(self.idle_box, 1)
        self.running_box.setVisible(False)

        host.installEventFilter(self)
        self._restore()

    # ---- state ------------------------------------------------------------------------------
    def _restore(self) -> None:
        saved = self.page.win.settings.get(KEY) or {}
        try:
            dock = [int(v) for v in saved.get('dock', self.dock)]
            if len(dock) == 4:
                self.dock = dock
            rect = saved.get('float')
            if rect and len(rect) == 4:
                self.float_rect = [int(v) for v in rect]
            self.shown = bool(saved.get('shown', True))
            detached = bool(saved.get('detached', False))
        except (TypeError, ValueError, AttributeError):
            detached = False
        self._apply_mode(detached)

    def save_state(self) -> None:
        self.page.win.settings.set(KEY, {'detached': self.detached, 'shown': self.shown, 'dock': list(self.dock),
                                         'float': self.float_rect})

    # ---- docked / detached --------------------------------------------------------------------
    def set_detached(self, on: bool) -> None:
        if on != self.detached:
            self._apply_mode(on)
            self.save_state()

    def _apply_mode(self, detached: bool) -> None:
        if detached and self.float_rect is None:
            # First detach: appear where the docked widget was, in screen coordinates.
            corner = self.host.mapToGlobal(self._dock_rect().topLeft())
            self.float_rect = [corner.x(), corner.y(), self.dock[2], self.dock[3]]
        self.detached = detached
        self.setProperty('detached', detached)
        if detached:
            self.setParent(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        else:
            self.setParent(self.host, Qt.Widget)
        self.style().unpolish(self)
        self.style().polish(self)
        self.detach.setText('Dock' if detached else 'Detach')
        self.place(QRect(*self.float_rect) if detached else self._dock_rect(), remember=False)
        # Re-parenting hides the widget, so it has to be shown again.
        self.setVisible(self.shown)
        if self.shown:
            self.raise_()

    def set_shown(self, on: bool) -> None:
        self.shown = on
        self.setVisible(on)
        if on:
            self.raise_()
        self.save_state()
        self.page.update_timer_view()

    # ---- geometry -----------------------------------------------------------------------------
    def _dock_rect(self) -> QRect:
        right, bottom, width, height = self.dock
        return QRect(self.host.width() - right - width, self.host.height() - bottom - height, width, height)

    def _bounds(self, rect: QRect) -> QRect:
        if not self.detached:
            return self.host.rect()
        screen = QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()
        return screen.availableGeometry() if screen else rect

    def place(self, rect: QRect, remember: bool = True) -> None:
        """Move and size the widget, kept fully inside the window (docked) or the screen (detached)."""
        bounds = self._bounds(rect)
        width = max(MIN_W, min(rect.width(), max(MIN_W, bounds.width())))
        height = max(MIN_H, min(rect.height(), max(MIN_H, bounds.height())))
        x = max(bounds.left(), min(rect.x(), bounds.right() + 1 - width))
        y = max(bounds.top(), min(rect.y(), bounds.bottom() + 1 - height))
        self.setGeometry(x, y, width, height)
        if not remember:
            return
        if self.detached:
            self.float_rect = [x, y, width, height]
        else:
            self.dock = [self.host.width() - x - width, self.host.height() - y - height, width, height]

    def eventFilter(self, watched, event) -> bool:
        if watched is self.host and event.type() == QEvent.Resize and not self.detached:
            self.place(self._dock_rect(), remember=False)      # follow the corner as the window resizes
        return False

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
            self.raise_()
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

    # ---- timer controls -----------------------------------------------------------------------
    def _clear_hint(self, *_) -> None:
        self.hint = ''

    def _start(self) -> None:
        self.page.start_timer(self.project.project_id())
        if self.page.timer is None:
            self.hint = 'Choose a project first'
            self.title.setText(self.hint)

    def refresh(self, store) -> None:
        self.project.reload(store)

    def update_view(self, name: str, text: str, active: bool, running: bool) -> None:
        label = (name if running else f'{name}  ·  paused') if active else (self.hint or 'Timer')
        self.title.setText(self.title.fontMetrics().elidedText(label, Qt.ElideRight, max(40, self.title.width())))
        self.title.setToolTip(label)
        if len(text) != len(self.elapsed.text()):
            self.elapsed.setText(text)
            self._fit_clock()                     # ten hours and over needs one more digit
        self.elapsed.setText(text)
        self.pause.setText('Pause' if running else 'Resume')
        self.running_box.setVisible(active)
        self.idle_box.setVisible(not active)
