"""Manager dashboard: where discounted engineering is going."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDateEdit, QHBoxLayout, QVBoxLayout, QWidget

from .. import calc
from .charts import BarList, StatTile, TrendChart
from .common import (PERIODS, Hero, card, fit_rows, fmt_h, fmt_money, fmt_pct, from_qdate, label, make_table, page_scroll,
                     period_for, set_rows, to_qdate)
from .dialogs import ProjectDetailDialog

TOP = 8


class DashboardPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll, body = page_scroll()
        outer.addWidget(scroll)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(32, 14, 32, 28)
        layout.setSpacing(18)

        head = QHBoxLayout()
        head.setSpacing(10)
        self.hero = Hero('Discounted', 'engineering')
        head.addWidget(self.hero, 1)
        self.period = QComboBox()
        self.period.addItems(PERIODS)
        self.period.setCurrentText('All time')
        self.period.setMinimumWidth(170)
        today = to_qdate(date.today())
        self.start, self.end = QDateEdit(today), QDateEdit(today)
        for edit in (self.start, self.end):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat('dd/MM/yyyy')
            edit.setVisible(False)
            edit.dateChanged.connect(self.refresh)
        self.region, self.engineer = QComboBox(), QComboBox()
        self.region.setMinimumWidth(130)
        self.engineer.setMinimumWidth(140)
        for widget in (self.period, self.start, self.end, self.region, self.engineer):
            head.addWidget(widget, 0, Qt.AlignBottom)
        layout.addLayout(head)
        self.period.currentTextChanged.connect(self._period_changed)
        self.region.currentIndexChanged.connect(self.refresh)
        self.engineer.currentIndexChanged.connect(self.refresh)

        tiles = QHBoxLayout()
        tiles.setSpacing(18)
        self.tiles = {'hours': StatTile('Discounted hours'), 'amount': StatTile('Discounted amount', hero=True),
                      'over': StatTile('Projects over quote'), 'avg': StatTile('Average over quote')}
        for tile in self.tiles.values():
            tiles.addWidget(tile)
        layout.addLayout(tiles)
        self.note = label('', 'note')
        self.note.setWordWrap(True)
        layout.addWidget(self.note)

        self.top = BarList('accent', 'Nothing discounted in this period')
        self.over = BarList('danger', 'No project is over its quote')
        self.trend = TrendChart()
        self.trend.setFixedHeight(230)
        self.by_region, self.by_engineer, self.by_reason = BarList(), BarList(), BarList()
        for bars in (self.top, self.over):
            bars.activated.connect(self.open_project)
        columns = QHBoxLayout()
        columns.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(18)
        rail = QWidget()
        rail.setFixedWidth(350)
        right = QVBoxLayout(rail)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(18)
        for target, title, widget, stretch in ((left, 'Top projects by discounted amount', self.top, 0),
                                               (left, 'Trend', self.trend, 0),
                                               (left, 'By reason', self.by_reason, 0),
                                               (right, 'Over quote', self.over, 0), (right, 'By region', self.by_region, 0),
                                               (right, 'By engineer', self.by_engineer, 0)):
            frame, box = card(title)
            box.addWidget(widget, stretch)
            if not stretch:
                box.addStretch(1)
            target.addWidget(frame, stretch)
        left.addStretch(1)
        right.addStretch(1)
        columns.addLayout(left, 1)
        columns.addWidget(rail)
        layout.addLayout(columns)

        frame, box = card('Projects')
        box.addWidget(label('Double-click a project to see its entries, edit it or delete it. New projects are added '
                            'from Log time.', 'faint'))
        self.table = make_table(['Project', 'Region', 'Quoted h', 'Logged h (total)', 'Discounted h (period)',
                                 'Discounted $ (period)', 'Over quote'])
        self.table.doubleClicked.connect(lambda index: self.open_project(self.table.item(index.row(), 0).data(Qt.UserRole)))
        box.addWidget(self.table)
        layout.addWidget(frame)
        layout.addStretch(1)
        self.refresh()

    def set_period(self, choice: str) -> None:
        self.period.setCurrentText(choice)

    def _period_changed(self, choice: str) -> None:
        for edit in (self.start, self.end):
            edit.setVisible(choice == 'Custom')
        self.refresh()

    def current_period(self) -> calc.Period:
        return period_for(self.period.currentText(), date.today(), self.win.store.config.fy_start_month,
                          from_qdate(self.start.date()), from_qdate(self.end.date()))

    def _fill_filter(self, combo: QComboBox, first: str, values) -> None:
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(first, None)
        for value in values:
            combo.addItem(value, value)
        combo.setCurrentIndex(max(0, combo.findData(current)) if current else 0)
        combo.blockSignals(False)

    def refresh(self, *_) -> None:
        store = self.win.store
        regions = sorted({p.region for p in store.live_projects() if p.region})
        self._fill_filter(self.region, 'All regions', regions)
        self._fill_filter(self.engineer, 'All engineers', store.engineers())
        period = self.current_period()
        s = calc.summarise(store.live_projects(), store.live_entries(), store.config.rate, period,
                           self.region.currentData(), self.engineer.currentData())
        self.hero.restyle()
        self.hero.set_subtitle('Every entry ever logged, including opening balances' if not period.dated else
                               f'{period.label}  ·  {period.start:%d/%m/%Y} to {period.end:%d/%m/%Y}')
        self.tiles['hours'].set(fmt_h(s.discounted_h), f'{fmt_h(s.logged_h)} logged')
        self.tiles['amount'].set(fmt_money(s.amount), f'hours at ${store.config.rate:,.0f}/h, plus imported amounts')
        self.tiles['over'].set(f'{s.over_count} of {s.quoted_count}', 'projects that have a quote')
        self.tiles['avg'].set(fmt_pct(s.avg_over_pct), 'across projects over quote')
        show_note = period.dated and s.before_tracking_h > 0
        self.note.setVisible(show_note)
        if show_note:
            self.note.setText(f'{fmt_h(s.before_tracking_h)} of undated opening balances and any imported dollar amounts '
                              f'(from Excel) are not in this period. Choose All time to include them.')
        self.top.set_rows([(r.project.id, r.project.name, r.period_amount,
                            f'{fmt_money(r.period_amount)}  ·  {r.period_discounted_h:,.1f} h')
                           for r in s.rows if r.period_amount > 0][:TOP])
        over = sorted((r for r in s.rows if r.over_pct is not None and r.over_pct > 0), key=lambda r: -r.over_pct)
        self.over.set_rows([(r.project.id, r.project.name, r.over_pct,
                             f'{fmt_pct(r.over_pct)}   {r.logged_h:,.1f} / {r.quoted_h:,.1f} h') for r in over][:TOP])
        self.trend.set_points(s.trend)
        for bars, totals in ((self.by_region, s.amount_by_region), (self.by_engineer, s.amount_by_engineer),
                             (self.by_reason, s.amount_by_reason)):
            bars.set_rows([(k, k, v, fmt_money(v)) for k, v in list(totals.items())[:TOP]])
        rows = [[r.project.name, r.project.region, ('—' if r.quoted_h is None else f'{r.quoted_h:,.2f}', r.quoted_h or 0.0),
                 (f'{r.logged_h:,.2f}', r.logged_h), (f'{r.period_discounted_h:,.2f}', r.period_discounted_h),
                 (fmt_money(r.period_amount), r.period_amount),
                 (fmt_pct(r.over_pct), r.over_pct if r.over_pct is not None else -1e9)] for r in s.rows]
        set_rows(self.table, rows, [r.project.id for r in s.rows])
        fit_rows(self.table, 3, 60)

    def open_project(self, project_id) -> None:
        if project_id in self.win.store.projects:
            ProjectDetailDialog(self.win, project_id).exec()
            self.win.refresh_pages()
