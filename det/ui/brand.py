"""Budget Tracker's own mark, painted in code: used for the window, the taskbar and the tray icon."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPixmap

NAME = 'Budget Tracker'
TAGLINE = 'Discounted engineering'


def mark(size: int = 64) -> QPixmap:
    """A rounded blue tile with three rising white bars (a budget being drawn down)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size / 64, size / 64)
    gradient = QLinearGradient(0, 0, 64, 64)
    gradient.setColorAt(0, QColor('#6187FF'))
    gradient.setColorAt(1, QColor('#2A4FD6'))
    p.setPen(Qt.NoPen)
    p.setBrush(gradient)
    p.drawRoundedRect(QRectF(2, 2, 60, 60), 16, 16)
    p.setBrush(QColor('#FFFFFF'))
    for x, top in ((15, 34), (28, 25), (41, 16)):
        p.drawRoundedRect(QRectF(x, top, 9, 48 - top), 3.5, 3.5)
    p.end()
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(mark(size))
    return icon
