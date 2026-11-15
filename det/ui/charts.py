"""Small painted charts. Drawn by hand so they stay minimal and follow the theme."""
from __future__ import annotations

import math

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QLinearGradient, QPainter
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ..theme import tokens


class StatTile(QFrame):
    def __init__(self, title: str, hero: bool = False):
        super().__init__()
        self.setObjectName('heroCard' if hero else 'card')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(3)
        self.title = QLabel(title)
        self.title.setObjectName('muted')
        self.value = QLabel('—')
        self.value.setObjectName('tileValue')
        self.sub = QLabel('')
        self.sub.setObjectName('faint')
        for widget in (self.title, self.value, self.sub):
            layout.addWidget(widget)

    def set(self, value: str, sub: str = '') -> None:
        self.value.setText(value)
        self.sub.setText(sub)


class BarList(QWidget):
    """Ranked horizontal bars: label, bar, value. Rows are (key, label, value, text)."""
    activated = Signal(object)
    ROW = 32

    def __init__(self, tone: str = 'accent', empty: str = 'Nothing to show yet'):
        super().__init__()
        self.rows: list = []
        self.tone = tone
        self.empty = empty
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_rows(self, rows) -> None:
        self.rows = list(rows)
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(240, max(1, len(self.rows)) * self.ROW + 4)

    def minimumSizeHint(self) -> QSize:
        return QSize(150, self.sizeHint().height())

    def paintEvent(self, event) -> None:
        t = tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.rows:
            p.setPen(QColor(t['text_faint']))
            p.drawText(self.rect(), Qt.AlignLeft | Qt.AlignVCenter, self.empty)
            return
        metrics = QFontMetrics(self.font())
        width = self.width()
        label_w = min(int(width * 0.36), 220)
        value_w = max(metrics.horizontalAdvance(r[3]) for r in self.rows) + 10
        bar_x, bar_w = label_w + 10, max(10, width - label_w - value_w - 20)
        peak = max((abs(r[2]) for r in self.rows), default=0) or 1
        for i, (_, label, value, text) in enumerate(self.rows):
            y = i * self.ROW + 2
            p.setPen(QColor(t['text']))
            p.drawText(QRectF(0, y, label_w, self.ROW), Qt.AlignLeft | Qt.AlignVCenter,
                       metrics.elidedText(label, Qt.ElideRight, label_w))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t['surface_alt']))
            p.drawRoundedRect(QRectF(bar_x, y + 11, bar_w, 10), 5, 5)
            fill = bar_w * min(1.0, abs(value) / peak)
            if fill > 0:
                fill = max(fill, 8)
                if self.tone == 'accent':
                    gradient = QLinearGradient(bar_x, 0, bar_x + fill, 0)
                    gradient.setColorAt(0, QColor(t['accent']))
                    gradient.setColorAt(1, QColor(t['accent2']))
                    p.setBrush(gradient)
                else:
                    p.setBrush(QColor(t[self.tone]))
                p.drawRoundedRect(QRectF(bar_x, y + 11, fill, 10), 5, 5)
            p.setPen(QColor(t['text_muted']))
            p.drawText(QRectF(width - value_w, y, value_w, self.ROW), Qt.AlignRight | Qt.AlignVCenter, text)

    def mouseDoubleClickEvent(self, event) -> None:
        index = int(event.position().y() // self.ROW)
        if 0 <= index < len(self.rows):
            self.activated.emit(self.rows[index][0])


class TrendChart(QWidget):
    """Bars over time; the highest bar is lit and labelled. Points are (label, value)."""

    def __init__(self, empty: str = 'No dated entries in this period', unit: str = 'h'):
        super().__init__()
        self.points: list = []
        self.empty = empty
        self.unit = unit
        self.setMinimumHeight(170)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_points(self, points) -> None:
        self.points = list(points)
        self.update()

    def paintEvent(self, event) -> None:
        t = tokens()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self.points or not any(v for _, v in self.points):
            p.setPen(QColor(t['text_faint']))
            p.drawText(self.rect(), Qt.AlignLeft | Qt.AlignVCenter, self.empty)
            return
        metrics = QFontMetrics(self.font())
        top, bottom = metrics.height() + 16, metrics.height() + 8
        height = self.height() - top - bottom
        width = self.width()
        peak = max(v for _, v in self.points)
        peak_index = max(range(len(self.points)), key=lambda i: self.points[i][1])
        count = len(self.points)
        slot = width / count
        bar_w = max(4.0, min(30.0, slot * 0.56))
        every = max(1, math.ceil(count / max(1, int(width // 44))))
        base = top + height
        hatch = QColor(t['text_faint'])
        for i, (label, value) in enumerate(self.points):
            x = i * slot + (slot - bar_w) / 2
            bar_h = max(height * value / peak, 4) if value > 0 else 4
            rect = QRectF(x, base - bar_h, bar_w, bar_h)
            p.setPen(Qt.NoPen)
            if i == peak_index:
                gradient = QLinearGradient(0, rect.top(), 0, rect.bottom())
                gradient.setColorAt(0, QColor(t['accent2']))
                gradient.setColorAt(1, QColor(t['accent']))
                p.setBrush(gradient)
                p.drawRoundedRect(rect, 4, 4)
                text = f'{value:,.1f} {self.unit}'
                bubble_w = metrics.horizontalAdvance(text) + 16
                bubble_x = min(max(2.0, x + bar_w / 2 - bubble_w / 2), width - bubble_w - 2)
                bubble = QRectF(bubble_x, rect.top() - metrics.height() - 10, bubble_w, metrics.height() + 4)
                p.setBrush(QColor(t['accent']))
                p.drawRoundedRect(bubble, bubble.height() / 2, bubble.height() / 2)
                p.setPen(QColor(t['accent_text']))
                p.drawText(bubble, Qt.AlignCenter, text)
            else:
                p.setBrush(QColor(t['surface_alt']))
                p.drawRoundedRect(rect, 4, 4)
                if value > 0:
                    p.setBrush(QBrush(hatch, Qt.BDiagPattern))
                    p.drawRoundedRect(rect, 4, 4)
            if i % every == 0 or i == peak_index:
                p.setPen(QColor(t['text'] if i == peak_index else t['text_faint']))
                p.drawText(QRectF(i * slot - 24, base + 5, slot + 48, bottom), Qt.AlignHCenter | Qt.AlignTop, label)
