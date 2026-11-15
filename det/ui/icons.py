"""Round navigation icons, painted in code so they follow the theme and need no image files."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient

from ..theme import tokens

SIZE = 40
SCALE = 3


def _glyph(p: QPainter, kind: str, color: QColor) -> None:
    pen = QPen(color, 1.8)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    if kind == 'log':                                   # clock
        p.drawEllipse(QPointF(20, 20), 7.5, 7.5)
        p.drawPolyline([QPointF(20, 15.5), QPointF(20, 20), QPointF(23.5, 22)])
    elif kind == 'dashboard':                           # four tiles
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        for x, y in ((13, 13), (21.5, 13), (13, 21.5), (21.5, 21.5)):
            p.drawRoundedRect(QRectF(x, y, 5.5, 5.5), 1.6, 1.6)
    elif kind == 'projects':                            # folder
        path = QPainterPath()
        path.moveTo(12.5, 15)
        path.lineTo(17.5, 15)
        path.lineTo(19.5, 17)
        path.lineTo(27.5, 17)
        path.lineTo(27.5, 26)
        path.lineTo(12.5, 26)
        path.closeSubpath()
        p.drawPath(path)
    elif kind == 'reports':                             # bars
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        for x, height in ((13.5, 6), (18.5, 11), (23.5, 8)):
            p.drawRoundedRect(QRectF(x, 27 - height, 3.4, height), 1.2, 1.2)
    elif kind == 'settings':                            # sliders
        p.drawLine(QPointF(13, 16.5), QPointF(27, 16.5))
        p.drawLine(QPointF(13, 23.5), QPointF(27, 23.5))
        p.setBrush(color)
        p.drawEllipse(QPointF(23, 16.5), 2.2, 2.2)
        p.drawEllipse(QPointF(17, 23.5), 2.2, 2.2)
    elif kind in ('lock', 'unlock'):
        p.drawRoundedRect(QRectF(14, 19, 12, 8.5), 2, 2)
        path = QPainterPath()
        if kind == 'lock':
            path.moveTo(16.5, 19)
            path.cubicTo(16.5, 11.5, 23.5, 11.5, 23.5, 19)
        else:
            path.moveTo(16.5, 19)
            path.cubicTo(16.5, 11.5, 23.5, 11.5, 23.5, 15.5)
        p.drawPath(path)


def _pixmap(kind: str, active: bool, enabled: bool = True) -> QPixmap:
    t = tokens()
    pixmap = QPixmap(SIZE * SCALE, SIZE * SCALE)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(SCALE, SCALE)
    if active:
        glow = QRadialGradient(QPointF(20, 16), 22)
        glow.setColorAt(0.0, QColor(t['accent2']))
        glow.setColorAt(0.55, QColor(t['accent']))
        glow.setColorAt(1.0, QColor(t['glow']))
        p.setPen(QPen(QColor(t['accent2']), 1))
        p.setBrush(glow)
    else:
        p.setPen(QPen(QColor(t['border']), 1))
        p.setBrush(QColor(t['surface_alt']))
    p.drawEllipse(QRectF(1.5, 1.5, SIZE - 3, SIZE - 3))
    color = QColor('#FFFFFF') if active else QColor(t['text_muted'] if enabled else t['text_faint'])
    _glyph(p, kind, color)
    p.end()
    pixmap.setDevicePixelRatio(SCALE)
    return pixmap


def nav_icon(kind: str) -> QIcon:
    icon = QIcon()
    icon.addPixmap(_pixmap(kind, False), QIcon.Normal, QIcon.Off)
    icon.addPixmap(_pixmap(kind, True), QIcon.Normal, QIcon.On)
    icon.addPixmap(_pixmap(kind, True), QIcon.Active, QIcon.On)
    icon.addPixmap(_pixmap(kind, False, enabled=False), QIcon.Disabled, QIcon.Off)
    return icon
