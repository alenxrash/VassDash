"""Dialogs: project, time entry, project detail, Excel import review, first run."""
from __future__ import annotations

import copy
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDoubleSpinBox,
                               QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QTableWidgetItem, QVBoxLayout)

from .. import calc, importer
from ..models import Entry, Project
from ..theme import tokens
from .common import (ProjectCombo, fit_rows, fmt_date, fmt_h, fmt_money, fmt_pct, from_qdate, label, make_table,
                     selected_id, set_rows, to_qdate)


def _buttons(dialog, ok_text: str = 'Save'):
    row = QHBoxLayout()
    dialog.error = label('', 'error')
    dialog.error.setWordWrap(True)
    row.addWidget(dialog.error, 1)
    cancel = QPushButton('Cancel')
    cancel.clicked.connect(dialog.reject)
    ok = QPushButton(ok_text)
    ok.setObjectName('primary')
    ok.setDefault(True)
    row.addWidget(cancel)
    row.addWidget(ok)
    return row, ok


class ProjectDialog(QDialog):
    """Every field of a project. Anyone can add or edit one."""

    def __init__(self, win, project: Project | None = None):
        super().__init__(win)
        self.win, self.original = win, project
        self.setWindowTitle('Edit project' if project else 'New project')
        self.setMinimumWidth(460)
        config = win.store.config
        p = project or Project()
        form = QFormLayout()
        self.name = QLineEdit(p.name)
        self.sf_id = QLineEdit(p.sf_id)
        self.region = QComboBox()
        self.region.setEditable(True)
        self.region.addItems([''] + list(config.regions))
        self.region.setCurrentText(p.region)
        form.addRow('Project name', self.name)
        form.addRow('SF ID', self.sf_id)
        form.addRow('Region', self.region)
        self.quoted = QLineEdit('' if p.quoted_hours is None else f'{p.quoted_hours:g}')
        self.quoted.setPlaceholderText('Leave blank if there is no quote')
        self.amount = QLineEdit('' if p.opening_amount is None else f'{p.opening_amount:,.2f}')
        self.amount.setPlaceholderText('Dollar figure carried over from the old sheet, if any')
        self.approved_by = QLineEdit(p.approved_by)
        self.lead = QLineEdit(p.lead_engineer)
        self.category = QComboBox()
        categories = list(config.reason_categories)
        if p.reason_category and p.reason_category not in categories:
            categories.append(p.reason_category)
        self.category.addItems(categories)
        self.category.setCurrentText(p.reason_category or 'Other')
        self.detail = QLineEdit(p.reason_detail)
        self.remarks = QPlainTextEdit(p.remarks)
        self.remarks.setFixedHeight(70)
        self.status = QComboBox()
        self.status.addItems(['open', 'closed'])
        self.status.setCurrentText(p.status)
        form.addRow('Quoted hours', self.quoted)
        form.addRow('Imported amount ($)', self.amount)
        form.addRow('Approved by', self.approved_by)
        form.addRow('Lead engineer', self.lead)
        form.addRow('Discount reason', self.category)
        form.addRow('Reason detail', self.detail)
        form.addRow('Remarks', self.remarks)
        form.addRow('Status', self.status)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        row, ok = _buttons(self)
        ok.clicked.connect(self._accept)
        layout.addLayout(row)
        self.saved: Project | None = None

    def save(self) -> bool:
        project = copy.copy(self.original) if self.original else Project(created_by=self.win.user)
        project.name = self.name.text().strip()
        project.sf_id = self.sf_id.text().strip()
        project.region = self.region.currentText().strip().upper()
        try:
            if not project.name:
                raise ValueError('Project name is required.')
            clash = next((p for p in self.win.store.live_projects()
                          if p.id != project.id and p.name.casefold() == project.name.casefold()
                          and p.sf_id.casefold() == project.sf_id.casefold()), None)
            if clash:
                raise ValueError('A project with this name and SF ID already exists.')
            text = self.quoted.text().strip()
            if text:
                try:
                    project.quoted_hours = float(text)
                except ValueError:
                    raise ValueError('Quoted hours must be a number.') from None
                if not 0 <= project.quoted_hours < 1e6:
                    raise ValueError('Quoted hours must be zero or more.')
            else:
                project.quoted_hours = None
            project.approved_by = self.approved_by.text().strip()
            project.lead_engineer = self.lead.text().strip()
            project.reason_category = self.category.currentText()
            project.reason_detail = self.detail.text().strip()
            project.remarks = self.remarks.toPlainText().strip()
            project.status = self.status.currentText()
            money = self.amount.text().replace(',', '').replace('$', '').strip()
            if money:
                try:
                    project.opening_amount = float(money)
                except ValueError:
                    raise ValueError('Imported amount must be a number.') from None
                if not 0 <= project.opening_amount < 1e9:
                    raise ValueError('Imported amount must be zero or more.')
            else:
                project.opening_amount = None
            self.win.store.save_project(project, new=self.original is None)
        except (ValueError, OSError) as problem:
            self.error.setText(str(problem))
            return False
        self.saved = project
        return True

    def _accept(self) -> None:
        if self.save():
            self.accept()


class EntryDialog(QDialog):
    def __init__(self, win, entry: Entry | None = None, project_id: str | None = None):
        super().__init__(win)
        self.win, self.original = win, entry
        self.setWindowTitle('Edit entry' if entry else 'Add entry')
        self.setMinimumWidth(440)
        e = entry or Entry(project_id=project_id or '', engineer=win.user, date=date.today().isoformat())
        self.opening = e.source == 'opening'
        form = QFormLayout()
        self.project = ProjectCombo(win.store, include_closed=True)
        self.project.set_project(e.project_id)
        self.day = QDateEdit(to_qdate(date.fromisoformat(e.date) if e.date else date.today()))
        self.day.setCalendarPopup(True)
        self.day.setDisplayFormat('dd/MM/yyyy')
        self.undated = QCheckBox('Undated opening balance')
        self.undated.setChecked(not e.date)
        self.undated.toggled.connect(lambda on: self.day.setEnabled(not on))
        self.day.setEnabled(bool(e.date))
        self.hours = QDoubleSpinBox()
        self.hours.setDecimals(2)
        self.hours.setSingleStep(0.25)
        self.hours.setRange(0.0, 100000.0 if self.opening else 24.0)
        self.hours.setValue(e.hours)
        self.revision = QLineEdit(e.revision)
        self.note = QLineEdit(e.note)
        self.engineer = QLineEdit(e.engineer)
        form.addRow('Project', self.project)
        form.addRow('Date', self.day)
        if self.opening:
            form.addRow('', self.undated)
        form.addRow('Hours', self.hours)
        form.addRow('Revision', self.revision)
        form.addRow('Note', self.note)
        form.addRow('Engineer', self.engineer)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        row, ok = _buttons(self)
        ok.clicked.connect(self._accept)
        layout.addLayout(row)

    def save(self) -> bool:
        entry = copy.copy(self.original) if self.original else Entry(source='batch')
        entry.project_id = self.project.project_id() or ''
        entry.date = None if (self.opening and self.undated.isChecked()) else from_qdate(self.day.date()).isoformat()
        entry.minutes = round(self.hours.value() * 60)
        entry.revision = self.revision.text().strip()
        entry.note = self.note.text().strip()
        entry.engineer = self.engineer.text().strip() or self.win.user
        try:
            self.win.store.save_entry(entry, new=self.original is None)
        except (ValueError, OSError) as problem:
            self.error.setText(str(problem))
            return False
        return True

    def _accept(self) -> None:
        if self.save():
            self.accept()


def button_at(row, index):
    return row.itemAt(index).widget()


class ProjectDetailDialog(QDialog):
    """Everything behind a project's figures: the quote, the totals and each entry."""

    def __init__(self, win, project_id: str):
        super().__init__(win)
        self.win, self.project_id = win, project_id
        self.setMinimumSize(760, 520)
        layout = QVBoxLayout(self)
        self.title = label('', 'title')
        self.meta = label('', 'muted')
        self.meta.setWordWrap(True)
        self.figures = label('', 'note')
        self.figures.setWordWrap(True)
        self.table = make_table(['Date', 'Engineer', 'Rev', 'Note', 'Hours', 'Discounted h', 'Source'], stretch=3)
        self.table.doubleClicked.connect(lambda *_: self.edit_entry())
        for widget in (self.title, self.meta, self.figures, self.table):
            layout.addWidget(widget)
        row = QHBoxLayout()
        for text, slot in (('Add entry', self.add_entry), ('Edit entry', self.edit_entry),
                           ('Delete entry', self.delete_entry), ('Edit project', self.edit_project),
                           ('Delete project', self.delete_project)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            row.addWidget(button)
        self.edit_button, self.delete_button = button_at(row, 3), button_at(row, 4)
        row.addStretch(1)
        close = QPushButton('Close')
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)
        self.refresh()

    def refresh(self) -> None:
        store = self.win.store
        project = store.projects.get(self.project_id)
        if not project:
            return
        entries = [e for e in store.live_entries() if e.project_id == project.id]
        row = calc.project_totals(project, entries, store.config.rate)
        self.setWindowTitle(project.name)
        self.title.setText(project.name)
        parts = [f'SF ID {project.sf_id}' if project.sf_id else '', project.region,
                 f'Approved by {project.approved_by}' if project.approved_by else '',
                 f'Lead {project.lead_engineer}' if project.lead_engineer else '',
                 f'{project.reason_category}: {project.reason_detail}' if project.reason_detail else project.reason_category,
                 project.remarks, 'Closed' if project.status == 'closed' else '']
        self.meta.setText('  ·  '.join(part for part in parts if part))
        quote = fmt_h(row.quoted_h) if row.quoted_h else 'no quote'
        imported = '' if project.opening_amount is None else f'   ·   Imported amount {fmt_money(project.opening_amount)}'
        self.figures.setText(f'Quoted {quote}   ·   Logged {fmt_h(row.logged_h)}   ·   Discounted '
                             f'{fmt_h(row.discounted_h)}   ·   Total {fmt_money(row.amount)}{imported}'
                             f'   ·   Over quote {fmt_pct(row.over_pct)}')
        rows = [[(fmt_date(s.entry.date), s.entry.date or ''), s.entry.engineer, s.entry.revision, s.entry.note,
                 (f'{s.entry.hours:,.2f}', s.entry.hours), (f'{s.discounted_h:,.2f}', s.discounted_h),
                 {'opening': 'Opening balance', 'timer': 'Timer', 'batch': 'Batch'}.get(s.entry.source, s.entry.source)]
                for s in row.slices]
        set_rows(self.table, rows, [s.entry.id for s in row.slices])

    def _changed(self) -> None:
        self.refresh()
        self.win.refresh_pages()

    def add_entry(self) -> None:
        if EntryDialog(self.win, project_id=self.project_id).exec():
            self._changed()

    def edit_entry(self) -> None:
        entry = self.win.store.entries.get(selected_id(self.table) or '')
        if entry and EntryDialog(self.win, entry).exec():
            self._changed()

    def delete_entry(self) -> None:
        identifier = selected_id(self.table)
        if identifier and QMessageBox.question(self, 'Delete entry', 'Delete the selected entry?') == QMessageBox.Yes:
            self.win.store.delete_entry(identifier)
            self._changed()

    def edit_project(self) -> None:
        if ProjectDialog(self.win, self.win.store.projects[self.project_id]).exec():
            self._changed()

    def delete_project(self) -> None:
        store = self.win.store
        project = store.projects[self.project_id]
        count = sum(1 for e in store.live_entries() if e.project_id == project.id)
        message = f'Delete "{project.name}"?'
        if count:
            message += f'\n\nIts {count} time entr{"y" if count == 1 else "ies"} will no longer count in any total.'
        if QMessageBox.question(self, 'Delete project', message) != QMessageBox.Yes:
            return
        try:
            store.delete_project(project.id)
        except OSError as problem:
            QMessageBox.warning(self, 'Not deleted', f'The project could not be deleted.\n\n{problem}')
            return
        self.win.refresh_pages()
        self.accept()


class ImportDialog(QDialog):
    """Review before import. Hours that were not plain numbers are marked to be typed in."""
    (COL_ROW, COL_NAME, COL_REGION, COL_HOURS, COL_AMOUNT, COL_ORIGINAL, COL_CATEGORY, COL_REASON,
     COL_CHECK) = range(9)

    def __init__(self, win, rows):
        super().__init__(win)
        self.win, self.rows = win, rows
        self.setWindowTitle('Import from Excel')
        self.setMinimumSize(1180, 600)
        layout = QVBoxLayout(self)
        flagged = sum(1 for r in rows if r.needs_review)
        intro = label(f'{len(rows)} rows found. Each becomes a project with an undated opening balance. '
                      f'{flagged} row(s) marked "Type the hours" had hours that were not a plain number: type the figure, '
                      f'or leave it blank to import the project with no hours. Name, hours and amount can be edited here. '
                      f'The amount is the sheet\'s Discounted Amount and is kept as given.', 'muted')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.table = make_table(['Row', 'Project name', 'Region', 'Hours', 'Amount $', 'Original hours cell', 'Category',
                                 'Reason', 'Check'], stretch=self.COL_REASON)
        self.table.horizontalHeader().setSectionResizeMode(self.COL_NAME, QHeaderView.Interactive)
        self.table.setColumnWidth(self.COL_NAME, 300)
        self.table.setSortingEnabled(False)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked
                                   | QAbstractItemView.EditKeyPressed | QAbstractItemView.AnyKeyPressed)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setRowCount(len(rows))
        flag = QColor(tokens()['accent2'])
        for r, row in enumerate(rows):
            cells = [str(row.row_no), row.name, row.region, '' if row.hours is None else f'{row.hours:g}',
                     '' if row.amount is None else f'{row.amount:,.2f}', row.hours_text, row.category, row.reason,
                     'Type the hours' if row.needs_review else '']
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c not in (self.COL_NAME, self.COL_HOURS, self.COL_AMOUNT):
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if row.needs_review:
                    item.setForeground(flag)        # rows to check are tinted and marked in the last column
                self.table.setItem(r, c, item)
        layout.addWidget(self.table, 1)
        buttons, ok = _buttons(self, 'Import')
        ok.clicked.connect(self._accept)
        layout.addLayout(buttons)

    def commit(self):
        """Returns (projects, entries) created, or None with the problem shown."""
        for r, row in enumerate(self.rows):
            name = self.table.item(r, self.COL_NAME).text().strip()
            text = self.table.item(r, self.COL_HOURS).text().strip().replace(',', '')
            if not name:
                self.error.setText(f'Row {row.row_no}: project name is required.')
                return None
            try:
                hours = float(text) if text else None
                if hours is not None and not 0 <= hours < 100000:
                    raise ValueError
            except ValueError:
                self.error.setText(f'Row {row.row_no}: hours must be a number, or blank.')
                return None
            money = self.table.item(r, self.COL_AMOUNT).text().replace(',', '').replace('$', '').strip()
            try:
                amount = float(money) if money else None
                if amount is not None and not 0 <= amount < 1e9:
                    raise ValueError
            except ValueError:
                self.error.setText(f'Row {row.row_no}: amount must be a number, or blank.')
                return None
            row.name, row.hours, row.amount = name, hours, amount
        try:
            return importer.commit(self.rows, self.win.store, self.win.user)
        except (ValueError, OSError) as problem:
            self.error.setText(str(problem))
            return None

    def _accept(self) -> None:
        result = self.commit()
        if result:
            self.created = result
            self.accept()
