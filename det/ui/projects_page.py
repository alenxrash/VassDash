"""Manager's project list: add, edit, set the quote, close, delete."""
from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QHeaderView, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget

from .. import calc
from .common import Hero, card, fmt_pct, label, make_table, selected_id, set_rows
from .dialogs import ProjectDetailDialog, ProjectDialog


class ProjectsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 14, 32, 28)
        layout.setSpacing(18)
        head = QHBoxLayout()
        head.setSpacing(12)
        self.hero = Hero('Projects', 'and quotes', 'Set the quoted hours, approval and discount reason for each project.')
        head.addWidget(self.hero, 1)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search name, SF ID, region…')
        self.search.setFixedWidth(260)
        self.search.textChanged.connect(self.refresh)
        self.show_closed = QCheckBox('Show closed')
        self.show_closed.setChecked(True)
        self.show_closed.toggled.connect(self.refresh)
        head.addWidget(self.show_closed, 0, Qt.AlignBottom)
        head.addWidget(self.search, 0, Qt.AlignBottom)
        layout.addLayout(head)
        frame, box = card()
        self.table = make_table(['Project', 'SF ID', 'Region', 'Lead', 'Approved by', 'Quoted h', 'Logged h',
                                 'Discounted h', 'Over quote', 'Reason', 'Status'])
        self.table.doubleClicked.connect(lambda *_: self.open())
        header = self.table.horizontalHeader()             # keep the name readable; let the reason take the slack
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        self.table.setColumnWidth(0, 230)
        header.setSectionResizeMode(9, QHeaderView.Stretch)
        box.addWidget(self.table, 1)
        row = QHBoxLayout()
        add = QPushButton('New project')
        add.setObjectName('primary')
        add.clicked.connect(self.add)
        row.addWidget(add)
        for text, slot in (('Open', self.open), ('Edit', self.edit), ('Close / reopen', self.toggle_closed),
                           ('Delete', self.delete)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            row.addWidget(button)
        row.addStretch(1)
        self.count = label('', 'muted')
        row.addWidget(self.count)
        box.addLayout(row)
        layout.addWidget(frame, 1)
        self.refresh()

    def refresh(self, *_) -> None:
        self.hero.restyle()
        store = self.win.store
        grouped = defaultdict(list)
        for entry in store.live_entries():
            grouped[entry.project_id].append(entry)
        needle = self.search.text().strip().casefold()
        rows, ids = [], []
        for p in store.live_projects():
            if p.status == 'closed' and not self.show_closed.isChecked():
                continue
            if needle and needle not in f'{p.name} {p.sf_id} {p.region} {p.lead_engineer}'.casefold():
                continue
            t = calc.project_totals(p, grouped.get(p.id, []), store.config.rate)
            rows.append([p.name, p.sf_id, p.region, p.lead_engineer, p.approved_by,
                         ('—' if t.quoted_h is None else f'{t.quoted_h:,.2f}', t.quoted_h or 0.0),
                         (f'{t.logged_h:,.2f}', t.logged_h), (f'{t.discounted_h:,.2f}', t.discounted_h),
                         (fmt_pct(t.over_pct), t.over_pct if t.over_pct is not None else -1e9),
                         p.reason_category, p.status.capitalize()])
            ids.append(p.id)
        set_rows(self.table, rows, ids)
        self.count.setText(f'{len(rows)} project(s)')

    def _selected(self):
        return self.win.store.projects.get(selected_id(self.table) or '')

    def add(self) -> None:
        if ProjectDialog(self.win).exec():
            self.win.refresh_pages()

    def edit(self) -> None:
        project = self._selected()
        if project and ProjectDialog(self.win, project).exec():
            self.win.refresh_pages()

    def open(self) -> None:
        project = self._selected()
        if project:
            ProjectDetailDialog(self.win, project.id).exec()
            self.win.refresh_pages()

    def toggle_closed(self) -> None:
        project = self._selected()
        if project:
            project.status = 'open' if project.status == 'closed' else 'closed'
            try:
                self.win.store.save_project(project)
            except OSError as problem:
                QMessageBox.warning(self, 'Not saved', f'The change could not be saved.\n\n{problem}')
                self.win.reload()
                return
            self.win.refresh_pages()

    def delete(self) -> None:
        project = self._selected()
        if not project:
            return
        count = sum(1 for e in self.win.store.live_entries() if e.project_id == project.id)
        message = f'Delete "{project.name}"?'
        if count:
            message += f'\n\nIts {count} time entr{"y" if count == 1 else "ies"} will no longer count in any total.'
        if QMessageBox.question(self, 'Delete project', message) == QMessageBox.Yes:
            self.win.store.delete_project(project.id)
            self.win.refresh_pages()
