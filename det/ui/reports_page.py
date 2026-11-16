"""Reports: pick a week, month, financial year or custom range; preview; export PDF or Excel."""
from __future__ import annotations

from datetime import date, timedelta
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDateEdit, QFileDialog, QHBoxLayout, QMessageBox, QPushButton, QTextBrowser,
                               QVBoxLayout, QWidget)

from .. import calc, reports
from ..theme import tokens
from .common import Hero, fmt_date, from_qdate, round_button, to_qdate

KINDS = ['Week', 'Month', 'Financial year', 'Custom', 'All time']


def report_html(report) -> str:
    t = tokens()
    num = lambda v: '' if v is None else f'{v:,.2f}'
    cell = f'padding:5px 10px; border-bottom:1px solid {t["border"]};'
    head = f'padding:5px 10px; color:{t["text_muted"]}; border-bottom:1px solid {t["border_strong"]}; text-align:left;'

    def table(headers, rows):
        out = ['<table cellspacing="0" width="100%"><tr>'] + [f'<th style="{head}">{escape(h)}</th>' for h in headers] + ['</tr>']
        if not rows:
            out.append(f'<tr><td style="{cell}" colspan="{len(headers)}">No data for this period.</td></tr>')
        for row in rows:
            out.append('<tr>' + ''.join(f'<td style="{cell}">{escape(str(c))}</td>' for c in row) + '</tr>')
        return ''.join(out) + '</table>'

    parts = [f'<h2 style="margin-bottom:0;">{escape(report.title)}</h2>',
             f'<p style="color:{t["text_muted"]};">{escape(report.period_label)} · generated {report.generated}</p>',
             table(['Measure', 'Value'], [(k, f'{v:,.2f}' if isinstance(v, float) else v) for k, v in reports.headline_lines(report)]),
             '<h3>By project</h3>',
             table(['Project', 'SF ID', 'Region', 'Quoted h', 'Logged h', 'Discounted h', 'Discounted $', 'Over quote'],
                   [(n, sf, reg, num(q), num(lg), num(d), f'${num(a)}', '' if o is None else f'{o:+.0f}%')
                    for n, sf, reg, q, lg, d, a, o in report.project_rows])]
    for title, rows in (('By engineer', report.engineer_rows), ('By region', report.region_rows),
                        ('By reason', report.reason_rows)):
        parts += [f'<h3>{title}</h3>', table([title[3:].capitalize(), 'Discounted h', 'Discounted $'],
                                             [(l, num(h), f'${num(a)}') for l, h, a in rows])]
    parts += ['<h3>Entries</h3>',
              table(['Date', 'Project', 'Engineer', 'Rev', 'Note', 'Hours', 'Discounted h'],
                    [(fmt_date(d), p, e, rev, note, num(h), num(dh)) for d, p, e, rev, note, h, dh in report.entry_rows])]
    return ''.join(parts)


class ReportsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 22, 32, 28)
        layout.setSpacing(16)
        head = QHBoxLayout()
        head.setSpacing(10)
        self.hero = Hero('Reports', 'by period')
        head.addWidget(self.hero, 1)
        self.kind = QComboBox()
        self.kind.addItems(KINDS)
        self.kind.setCurrentText('Month')
        previous, following = round_button('‹', 'Earlier'), round_button('›', 'Later')
        for button, step in ((previous, -1), (following, 1)):
            button.clicked.connect(lambda _=False, s=step: self.shift(s))
        self.step_buttons = (previous, following)
        today = to_qdate(date.today())
        self.anchor, self.end = QDateEdit(today), QDateEdit(today)
        for edit in (self.anchor, self.end):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat('dd/MM/yyyy')
            edit.dateChanged.connect(self.refresh)
        self.kind.currentTextChanged.connect(self.refresh)
        pdf, xlsx = QPushButton('Export PDF'), QPushButton('Export Excel')
        pdf.setObjectName('primary')
        pdf.clicked.connect(lambda: self.export('pdf'))
        xlsx.clicked.connect(lambda: self.export('xlsx'))
        self.kind.setMinimumWidth(150)
        for widget in (self.kind, previous, following, self.anchor, self.end, xlsx, pdf):
            head.addWidget(widget, 0, Qt.AlignBottom)
        layout.addLayout(head)
        self.preview = QTextBrowser()
        layout.addWidget(self.preview, 1)
        self.refresh()

    def set_kind(self, kind: str, anchor: date | None = None) -> None:
        if anchor:
            self.anchor.setDate(to_qdate(anchor))
        self.kind.setCurrentText(kind)
        self.refresh()

    def shift(self, step: int) -> None:
        day, kind = from_qdate(self.anchor.date()), self.kind.currentText()
        if kind == 'Week':
            day += timedelta(days=7 * step)
        elif kind == 'Month':
            month = day.month - 1 + step
            day = date(day.year + month // 12, month % 12 + 1, 1)
        elif kind == 'Financial year':
            try:
                day = day.replace(year=day.year + step)
            except ValueError:
                day = day.replace(year=day.year + step, day=28)
        self.anchor.setDate(to_qdate(day))

    def current_period(self) -> calc.Period:
        kind, day = self.kind.currentText(), from_qdate(self.anchor.date())
        if kind == 'Week':
            return calc.week_of(day)
        if kind == 'Month':
            return calc.month_of(day)
        if kind == 'Financial year':
            return calc.fy_of(day, self.win.store.config.fy_start_month)
        if kind == 'Custom':
            return calc.custom(day, from_qdate(self.end.date()))
        return calc.all_time()

    def current_report(self):
        return reports.build_report(self.win.store, self.current_period())

    def refresh(self, *_) -> None:
        kind = self.kind.currentText()
        self.end.setVisible(kind == 'Custom')
        self.anchor.setVisible(kind != 'All time')
        for button in self.step_buttons:
            button.setVisible(kind in ('Week', 'Month', 'Financial year'))
        period = self.current_period()
        self.hero.restyle()
        self.hero.set_subtitle('Every entry ever logged' if not period.dated else
                               f'{period.label}  ·  {period.start:%d/%m/%Y} to {period.end:%d/%m/%Y}')
        self.preview.setHtml(report_html(self.current_report()))

    def export(self, kind: str) -> None:
        report = self.current_report()
        safe = ''.join(c if c.isalnum() or c in ' -' else ' ' for c in report.period_label).strip()
        name = f'Discounted Engineering - {safe}.{kind}'
        pattern = 'PDF (*.pdf)' if kind == 'pdf' else 'Excel workbook (*.xlsx)'
        path, _ = QFileDialog.getSaveFileName(self, 'Export report', name, pattern)
        if not path:
            return
        if not path.lower().endswith('.' + kind):
            path += '.' + kind
        try:
            (reports.export_pdf if kind == 'pdf' else reports.export_xlsx)(report, path)
        except OSError as problem:
            QMessageBox.warning(self, 'Export failed', f'The file could not be written. Is it open in another '
                                                       f'program?\n\n{problem}')
            return
        QMessageBox.information(self, 'Report exported', f'Saved to:\n{path}')
