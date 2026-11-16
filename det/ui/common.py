"""Shared widgets and formatting for the interface."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, Qt
from html import escape

from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QCompleter, QFrame, QHeaderView, QLabel, QPushButton,
                               QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import calc
from ..theme import tokens

HEADER_H = 38
ROW_H = 36
PERIODS = ['This week', 'Last week', 'This month', 'Last month', 'This financial year', 'Last financial year',
           'All time', 'Custom']


def fmt_h(hours: float) -> str:
    return f'{hours:,.2f} h'


def fmt_money(amount: float) -> str:
    return f'${amount:,.0f}'


def fmt_pct(pct) -> str:
    return '—' if pct is None else f'{pct:+.0f}%'


def fmt_date(iso) -> str:
    return f'{iso[8:10]}/{iso[5:7]}/{iso[0:4]}' if iso else 'Undated'


def to_qdate(day: date) -> QDate:
    return QDate(day.year, day.month, day.day)


def from_qdate(value: QDate) -> date:
    return date(value.year(), value.month(), value.day())


def period_for(choice: str, today: date, fy_start: int = 7, start: date | None = None,
               end: date | None = None) -> calc.Period:
    if choice == 'This week':
        return calc.week_of(today)
    if choice == 'Last week':
        return calc.week_of(today - timedelta(days=7))
    if choice == 'This month':
        return calc.month_of(today)
    if choice == 'Last month':
        return calc.month_of(today.replace(day=1) - timedelta(days=1))
    if choice == 'This financial year':
        return calc.fy_of(today, fy_start)
    if choice == 'Last financial year':
        return calc.fy_of(calc.fy_of(today, fy_start).start - timedelta(days=1), fy_start)
    if choice == 'Custom' and start and end:
        return calc.custom(start, end)
    return calc.all_time()


class Hero(QWidget):
    """Page heading: one accent-coloured word, the rest in the text colour, and a muted line under it."""

    def __init__(self, accent: str, rest: str, subtitle: str = ''):
        super().__init__()
        self.accent, self.rest = accent, rest
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.title = QLabel()
        self.title.setObjectName('hero')
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName('muted')
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        self.restyle()

    def restyle(self) -> None:
        self.title.setText(f'<span style="color:{tokens()["accent2"]};">{escape(self.accent)}</span> {escape(self.rest)}')

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(text)


def page_scroll():
    """A scrolling page that lets the window background show through. Returns (scroll area, body widget)."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.viewport().setAutoFillBackground(False)
    body = QWidget()
    body.setObjectName('page')
    scroll.setWidget(body)
    return scroll, body


def round_button(text: str, tip: str = '') -> QPushButton:
    button = QPushButton(text)
    button.setObjectName('round')
    if tip:
        button.setToolTip(tip)
    return button


def card(title: str | None = None, hero: bool = False):
    frame = QFrame()
    frame.setObjectName('heroCard' if hero else 'card')
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(22, 18, 22, 20)
    layout.setSpacing(12)
    if title:
        label = QLabel(title)
        label.setObjectName('cardTitle')
        layout.addWidget(label)
    return frame, layout


def label(text: str, name: str = '') -> QLabel:
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    return widget


class SortItem(QTableWidgetItem):
    """Sorts by a stored value (number or text) instead of the displayed text."""

    def __lt__(self, other):
        mine, theirs = self.data(Qt.UserRole + 1), other.data(Qt.UserRole + 1)
        if mine is None or theirs is None:
            return (mine is None, self.text().casefold()) < (theirs is None, other.text().casefold())
        try:
            return mine < theirs
        except TypeError:
            return str(mine) < str(theirs)


def make_table(headers, stretch: int = 0) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(ROW_H)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setShowGrid(False)
    table.setSortingEnabled(True)
    header = table.horizontalHeader()
    header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    header.setSectionResizeMode(QHeaderView.ResizeToContents)
    header.setSectionResizeMode(stretch, QHeaderView.Stretch)
    header.setHighlightSections(False)
    header.setFixedHeight(HEADER_H)
    header.setSortIndicator(-1, Qt.AscendingOrder)      # keep the given order until a header is clicked
    return table


def set_rows(table: QTableWidget, rows, ids) -> None:
    """rows: list of rows; a cell is text, or (text, sort value). ids: one per row, kept on column 0."""
    keep = selected_id(table)
    table.setSortingEnabled(False)
    table.setRowCount(len(rows))
    for r, (row, identifier) in enumerate(zip(rows, ids)):
        for c, cell in enumerate(row):
            text, key = cell if isinstance(cell, tuple) else (cell, None)
            item = SortItem('' if text is None else str(text))
            if key is not None:
                item.setData(Qt.UserRole + 1, key)
                if isinstance(key, (int, float)):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if c == 0:
                item.setData(Qt.UserRole, identifier)
            table.setItem(r, c, item)
    table.setSortingEnabled(True)
    if keep is not None:
        for r in range(table.rowCount()):
            if table.item(r, 0).data(Qt.UserRole) == keep:
                table.selectRow(r)
                break


def selected_id(table: QTableWidget):
    items = table.selectedItems()
    if not items:
        return None
    first = table.item(items[0].row(), 0)
    return first.data(Qt.UserRole) if first else None


def relayout(widget) -> None:
    """A widget whose fixed height changed inside a scroll area can be missed for one pass; re-run the
    layouts above it so cards never overlap their contents."""
    parent = widget.parentWidget()
    for _ in range(4):
        if parent is None:
            break
        if parent.layout() is not None:
            parent.layout().invalidate()
            parent.layout().activate()
        parent = parent.parentWidget()


def fit_rows(table: QTableWidget, minimum: int = 3, maximum: int = 12) -> None:
    rows = max(minimum, min(maximum, table.rowCount()))
    table.setFixedHeight(HEADER_H + rows * ROW_H + 6)
    relayout(table)


class ProjectCombo(QComboBox):
    """Type-to-search project picker."""

    def __init__(self, store=None, include_closed: bool = False):
        super().__init__()
        self.include_closed = include_closed
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setMinimumWidth(150)
        self.lineEdit().setPlaceholderText('Search project…')
        completer = self.completer()
        completer.setCompletionMode(QCompleter.PopupCompletion)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.activated.connect(self._show_start)
        if store is not None:
            self.reload(store)

    def reload(self, store, keep=None) -> None:
        current = keep if keep is not None else self.project_id()
        typed = self.currentText()
        self.blockSignals(True)
        self.clear()
        for project in store.live_projects():
            if project.status == 'closed' and not self.include_closed and project.id != current:
                continue
            text = f'{project.name}  ·  {project.sf_id}' if project.sf_id else project.name
            self.addItem(text, project.id)
        self.setCurrentIndex(-1)
        if current and self.findData(current) >= 0:
            self.setCurrentIndex(self.findData(current))
        else:
            self.setEditText(typed if not current else '')
        self.blockSignals(False)
        self._show_start()

    def _show_start(self, *_) -> None:
        """Long names are shown from their beginning, not their end, unless the person is typing."""
        if not self.lineEdit().hasFocus() or self.project_id():
            self.lineEdit().setCursorPosition(0)

    def project_id(self):
        index = self.findText(self.currentText().strip(), Qt.MatchFixedString)
        return self.itemData(index) if index >= 0 else None

    def set_project(self, identifier) -> None:
        index = self.findData(identifier) if identifier else -1
        self.setCurrentIndex(index)
        if index < 0:
            self.setEditText('')
        self._show_start()
