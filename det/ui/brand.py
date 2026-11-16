"""VassDash's own mark, painted in code: used for the window, the taskbar and the tray icon."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPen, QPixmap

NAME = 'VassDash'
TAGLINE = 'Discounted engineering'


def mark(size: int = 64) -> QPixmap:
    """A rounded blue tile with a white tick-shaped V and a dial dot."""
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
    pen = QPen(QColor('#FFFFFF'), 7)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.drawPolyline([QPointF(17, 22), QPointF(30, 44), QPointF(47, 18)])
    p.setPen(Qt.NoPen)
    p.setBrush(QColor('#FFFFFF'))
    p.drawEllipse(QPointF(47, 44), 4, 4)
    p.end()
    return pixmap


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(mark(size))
    return icon
