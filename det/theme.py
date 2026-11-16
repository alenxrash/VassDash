"""App theme: every colour and the stylesheet live here. Call apply_theme(app, mode) at startup.

VassDash look: deep navy canvas, rounded cards, pill controls and a blue accent, with a top tab bar.
'dark' is the default; 'light' keeps the same shapes on a pale background.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from string import Template

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPalette, QPen, QPixmap

TOKENS = {
    'dark': {
        'canvas': '#090E1D', 'canvas2': '#0F1836', 'sidebar': '#0C1224',
        'surface': '#151D38', 'surface_low': '#10172D', 'surface_alt': '#1C2547', 'field': '#0E1530',
        'border': '#232E52', 'border_strong': '#33416F',
        'text': '#F2F5FF', 'text_muted': '#9BA7C9', 'text_faint': '#6C779B',
        'accent': '#3D6BFF', 'accent_hover': '#6187FF', 'accent2': '#86A4FF', 'accent_soft': '#1A2B63',
        'accent_text': '#FFFFFF', 'glow': '#2A4FD6',
        'danger': '#FF6B7D', 'danger_soft': '#3B1A2B', 'good': '#4ADE80',
    },
    'light': {
        'canvas': '#EEF2FB', 'canvas2': '#E1E9FB', 'sidebar': '#FFFFFF',
        'surface': '#FFFFFF', 'surface_low': '#F8FAFF', 'surface_alt': '#EDF1FB', 'field': '#F6F8FE',
        'border': '#DCE3F2', 'border_strong': '#C2CDE6',
        'text': '#0E1630', 'text_muted': '#55607F', 'text_faint': '#8792B0',
        'accent': '#2F5BEA', 'accent_hover': '#4A72F5', 'accent2': '#2F5BEA', 'accent_soft': '#E2E9FF',
        'accent_text': '#FFFFFF', 'glow': '#B9C9FF',
        'danger': '#C2334A', 'danger_soft': '#FCE8EC', 'good': '#158668',
    },
}
MODE = 'dark'

QSS = Template('''
QWidget { font-size: 13px; color: $text; }
QMainWindow, QDialog { background: $canvas; }
QWidget#root { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 $canvas, stop:1 $canvas2); }
QToolTip { background: $surface_alt; color: $text; border: 1px solid $border_strong; padding: 6px 8px; }
QFrame#topbar { background: $sidebar; border: none; border-bottom: 1px solid $border; }
QFrame#noteBox { background: $accent_soft; border: 1px solid $border_strong; border-radius: 14px; }
QFrame#card { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 $surface, stop:1 $surface_low);
              border: 1px solid $border; border-radius: 22px; }
QFrame#heroCard { background: qlineargradient(x1:0, y1:0, x2:0.25, y2:1, stop:0 $surface, stop:0.5 $accent_soft, stop:1 $glow);
                  border: 1px solid $border_strong; border-radius: 22px; }
QFrame#timerWidget { background: qlineargradient(x1:0, y1:0, x2:0.3, y2:1, stop:0 $surface_alt, stop:0.6 $accent_soft, stop:1 $glow);
                     border: 1px solid $accent; border-radius: 0px; }
QPushButton#mini { border: none; background: transparent; color: $text_muted; padding: 0px 5px; min-height: 0px;
                   font-size: 12px; }
QPushButton#mini:hover { color: $text; }
QLabel { background: transparent; }
QLabel#appTitle { font-size: 17px; font-weight: 700; }
QLabel#hero { font-size: 30px; font-weight: 600; }
QLabel#title { font-size: 21px; font-weight: 600; }
QLabel#cardTitle { font-size: 14px; font-weight: 600; color: $text; }
QLabel#muted { color: $text_muted; }
QLabel#faint { color: $text_faint; font-size: 12px; }
QLabel#tileValue { font-size: 28px; font-weight: 600; }
QLabel#timerValue { font-size: 44px; font-weight: 600; }
QLabel#error { color: $danger; }
QLabel#banner { background: $danger_soft; color: $danger; padding: 9px 14px; border-radius: 14px; }
QLabel#note { background: $accent_soft; color: $text; padding: 9px 14px; border-radius: 14px; }
QLabel#chip { background: $surface_alt; color: $text_muted; border: 1px solid $border; border-radius: 13px;
              padding: 4px 12px; }
QLabel#avatar { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 $accent_hover, stop:1 $glow);
                color: #FFFFFF; font-weight: 700; border-radius: 19px; min-width: 38px; max-width: 38px;
                min-height: 38px; max-height: 38px; }

QPushButton { background: $surface_alt; border: 1px solid $border; border-radius: 17px; padding: 7px 16px;
              min-height: 18px; }
QPushButton:hover { border-color: $accent; }
QPushButton:disabled { color: $text_faint; border-color: $border; }
QPushButton#primary { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $accent, stop:1 $accent_hover);
                      color: $accent_text; border: 1px solid $accent_hover; font-weight: 600; }
QPushButton#primary:hover { background: $accent_hover; }
QPushButton#primary:disabled { background: $border_strong; border-color: $border_strong; color: $text_faint; }
QPushButton#round { border-radius: 17px; padding: 0px; min-width: 34px; max-width: 34px; min-height: 34px;
                    max-height: 34px; font-size: 16px; }
QPushButton#tab { border: none; background: transparent; color: $text_muted; padding: 8px 16px; border-radius: 17px; }
QPushButton#tab:hover { color: $text; background: $surface_alt; }
QPushButton#tab:checked { color: $accent_text; font-weight: 600;
                          background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 $accent, stop:1 $accent_hover); }
QPushButton#link { border: none; background: transparent; color: $accent2; padding: 2px 4px; }

QLineEdit, QComboBox, QDateEdit, QDoubleSpinBox, QSpinBox, QPlainTextEdit {
    background: $field; border: 1px solid $border; border-radius: 15px; padding: 6px 12px; min-height: 18px;
    selection-background-color: $accent; selection-color: $accent_text; }
QPlainTextEdit { border-radius: 14px; }
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QPlainTextEdit:focus {
    border: 1px solid $accent; }
QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled { color: $text_faint; }
QComboBox QLineEdit, QAbstractSpinBox QLineEdit { border: none; background: transparent; padding: 0px; min-height: 0px; }
QComboBox::drop-down, QDateEdit::drop-down { border: none; width: 30px; subcontrol-origin: padding;
                                             subcontrol-position: center right; }
QComboBox::down-arrow, QDateEdit::down-arrow { image: url($chevron); width: 12px; height: 12px; }
QComboBox QAbstractItemView { background: $surface; border: 1px solid $border_strong; outline: none; padding: 4px;
                              selection-background-color: $accent_soft; selection-color: $text; }
QDoubleSpinBox, QSpinBox { padding-left: 16px; }
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button, QSpinBox::up-button, QSpinBox::down-button {
    width: 0px; border: none; }
QCalendarWidget QWidget { background: $surface; alternate-background-color: $surface_alt; }
QCalendarWidget QAbstractItemView { selection-background-color: $accent; selection-color: $accent_text; }
QCheckBox { spacing: 8px; }

QTableWidget { background: transparent; border: none; gridline-color: $border;
               selection-background-color: $accent_soft; selection-color: $text; }
QTableWidget::item { padding: 3px 8px; border-bottom: 1px solid $border; }
QHeaderView { background: transparent; }
QHeaderView::section { background: transparent; color: $text_faint; border: none;
                       border-bottom: 1px solid $border_strong; padding: 7px 8px; font-weight: 600; }
QTableCornerButton::section { background: transparent; border: none; }
QScrollArea { border: none; background: transparent; }
QWidget#page { background: transparent; }
QTextBrowser { background: $surface; border: 1px solid $border; border-radius: 22px; padding: 14px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $border_strong; border-radius: 3px; min-height: 30px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: $border_strong; border-radius: 3px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0px; height: 0px; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
''')


def tokens(mode: str | None = None) -> dict:
    return TOKENS[mode or MODE]


def _chevron(mode: str) -> str:
    """The drop-down arrow is painted to a small image file, because a stylesheet can only take an image."""
    folder = Path(tempfile.gettempdir()) / 'det_tracker_theme'
    path = folder / f'chevron_{mode}.png'
    try:
        folder.mkdir(parents=True, exist_ok=True)
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(TOKENS[mode]['text_muted']), 2.6)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.drawPolyline([QPointF(6, 9), QPointF(12, 15), QPointF(18, 9)])
        painter.end()
        pixmap.save(str(path), 'PNG')
    except OSError:
        pass
    return path.as_posix()


def apply_theme(app, mode: str = 'dark') -> None:
    global MODE
    MODE = mode if mode in TOKENS else 'dark'
    t = tokens()
    app.setStyle('Fusion')
    font = QFont()
    font.setFamilies(['Segoe UI', 'Inter', 'Helvetica Neue', 'Arial'])
    font.setPointSize(10)
    app.setFont(font)
    palette = QPalette()
    roles = {
        QPalette.Window: 'canvas', QPalette.WindowText: 'text', QPalette.Base: 'field',
        QPalette.AlternateBase: 'surface_alt', QPalette.Text: 'text', QPalette.Button: 'surface_alt',
        QPalette.ButtonText: 'text', QPalette.Highlight: 'accent', QPalette.HighlightedText: 'accent_text',
        QPalette.ToolTipBase: 'surface_alt', QPalette.ToolTipText: 'text', QPalette.PlaceholderText: 'text_faint',
        QPalette.Mid: 'border_strong', QPalette.Dark: 'border_strong', QPalette.Light: 'surface',
        QPalette.Midlight: 'border', QPalette.Link: 'accent2',
    }
    for role, name in roles.items():
        palette.setColor(role, QColor(t[name]))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, QColor(t['text_faint']))
    app.setPalette(palette)
    app.setStyleSheet(QSS.substitute(t, chevron=_chevron(MODE)))
