"""My time: the timer, a one-line way to add hours, and this week's entries. Built for the fewest inputs."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDateEdit, QDoubleSpinBox, QHBoxLayout, QLineEdit, QMessageBox, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

from .. import calc
from ..models import Entry
from .charts import BarList, TrendChart
from .common import (Hero, ProjectCombo, card, fit_rows, fmt_date, fmt_h, from_qdate, label, make_table, page_scroll,
                     round_button, selected_id, set_rows, to_qdate)
from .dialogs import EntryDialog


class TimePage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.controller = win.controller
        self.week_anchor = date.today()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll, body = page_scroll()
        outer.addWidget(scroll)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(32, 22, 32, 28)
        layout.setSpacing(18)
        self.hero = Hero('My', 'time', 'Start the timer, or add hours in one line. Type a new name to create a project.')
        layout.addWidget(self.hero)

        columns = QHBoxLayout()
        columns.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(18)
        rail = QWidget()
        rail.setFixedWidth(292)
        right = QVBoxLayout(rail)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(18)
        columns.addLayout(left, 1)
        columns.addWidget(rail)
        layout.addLayout(columns)

        # ---- timer ----
        frame, box = card('Timer', hero=True)
        self.idle_box = QWidget()
        row = QHBoxLayout(self.idle_box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.timer_project = ProjectCombo(win.store)
        self.timer_project.lineEdit().returnPressed.connect(self.start_clicked)
        self.start_button = QPushButton('Start timer')
        self.start_button.setObjectName('primary')
        self.start_button.clicked.connect(self.start_clicked)
        row.addWidget(self.timer_project, 1)
        row.addWidget(self.start_button)
        box.addWidget(self.idle_box)
        self.running_box = QWidget()
        row = QHBoxLayout(self.running_box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.elapsed = label('0:00:00', 'timerValue')
        self.timer_name = label('', 'muted')
        self.timer_name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.pause_button = QPushButton('Pause')
        self.pause_button.clicked.connect(self.controller.toggle_pause)
        self.stop_button = QPushButton('Stop && save')
        self.stop_button.setObjectName('primary')
        self.stop_button.clicked.connect(lambda: win.widget.stop_clicked())
        self.discard_button = QPushButton('Discard')
        self.discard_button.clicked.connect(self.discard_clicked)
        row.addWidget(self.elapsed)
        row.addWidget(self.timer_name, 1)
        for button in (self.pause_button, self.stop_button, self.discard_button):
            row.addWidget(button)
        box.addWidget(self.running_box)
        row = QHBoxLayout()
        self.timer_status = label('', 'faint')
        self.widget_button = QPushButton('Hide desktop widget')
        self.widget_button.setObjectName('link')
        self.widget_button.setCursor(Qt.PointingHandCursor)
        self.widget_button.clicked.connect(lambda: win.widget.set_shown(not win.widget.shown))
        row.addWidget(self.timer_status, 1)
        row.addWidget(self.widget_button)
        box.addLayout(row)
        left.addWidget(frame)

        # ---- add hours, one line ----
        frame, box = card('Add hours')
        row = QHBoxLayout()
        row.setSpacing(10)
        self.quick_project = ProjectCombo(win.store)
        self.quick_hours = QDoubleSpinBox()
        self.quick_hours.setRange(0.0, 24.0)
        self.quick_hours.setDecimals(2)
        self.quick_hours.setSingleStep(0.25)
        self.quick_hours.setSuffix(' h')
        self.quick_hours.setFixedWidth(104)
        self.quick_date = QDateEdit(to_qdate(date.today()))
        self.quick_date.setCalendarPopup(True)
        self.quick_date.setDisplayFormat('dd/MM/yyyy')
        self.quick_date.setFixedWidth(146)
        self.quick_note = QLineEdit()
        self.quick_note.setPlaceholderText('Note (optional)')
        self.quick_note.returnPressed.connect(self.add_entry)
        add = QPushButton('Add')
        add.setObjectName('primary')
        add.clicked.connect(self.add_entry)
        row.addWidget(self.quick_project, 3)
        row.addWidget(self.quick_hours)
        row.addWidget(self.quick_date)
        row.addWidget(self.quick_note, 2)
        row.addWidget(add)
        box.addLayout(row)
        self.quick_status = label('', 'faint')
        box.addWidget(self.quick_status)
        left.addWidget(frame)

        # ---- my entries ----
        frame, box = card('My entries')
        row = QHBoxLayout()
        previous, following = round_button('‹', 'Previous week'), round_button('›', 'Next week')
        previous.clicked.connect(lambda: self.shift_week(-7))
        following.clicked.connect(lambda: self.shift_week(7))
        self.week_label = label('')
        self.week_total = label('', 'chip')
        row.addWidget(previous)
        row.addWidget(following)
        row.addWidget(self.week_label)
        row.addStretch(1)
        row.addWidget(self.week_total)
        box.addLayout(row)
        self.mine = make_table(['Date', 'Project', 'Hours', 'Note', 'Source'], stretch=1)
        self.mine.doubleClicked.connect(lambda *_: self.edit_mine())
        box.addWidget(self.mine)
        row = QHBoxLayout()
        edit, delete = QPushButton('Edit'), QPushButton('Delete')
        edit.clicked.connect(self.edit_mine)
        delete.clicked.connect(self.delete_mine)
        row.addWidget(edit)
        row.addWidget(delete)
        row.addStretch(1)
        box.addLayout(row)
        left.addWidget(frame)
        left.addStretch(1)

        # ---- right rail ----
        frame, box = card('This week')
        self.week_hours = label('0.00 h', 'tileValue')
        self.week_sub = label('', 'faint')
        self.week_chart = TrendChart('No hours logged this week')
        self.week_chart.setFixedHeight(160)
        for widget in (self.week_hours, self.week_sub, self.week_chart):
            box.addWidget(widget)
        right.addWidget(frame)
        frame, box = card('My projects')
        box.addWidget(label('Hours you have logged, all time', 'faint'))
        self.my_projects = BarList('accent', 'No hours logged yet')
        box.addWidget(self.my_projects)
        right.addWidget(frame)
        right.addStretch(1)
        layout.addStretch(1)

    # ---- timer ------------------------------------------------------------------------------
    def start_clicked(self) -> None:
        project_id = self.win.ensure_project(self.timer_project, self)
        if project_id:
            self.controller.start(project_id)
        else:
            self.controller.message = 'Choose a project first'
            self.update_timer_view()

    def discard_clicked(self) -> None:
        if self.controller.active and self.win.confirm('Discard timer', 'Discard this timer without saving?', self):
            self.controller.discard()

    def update_timer_view(self) -> None:
        c = self.controller
        self.idle_box.setVisible(not c.active)
        self.running_box.setVisible(c.active)
        self.elapsed.setText(c.elapsed_text())
        name = c.project_name if c.running else f'{c.project_name}  ·  paused' if c.active else ''
        self.timer_name.setText(self.timer_name.fontMetrics().elidedText(name, Qt.ElideRight, max(60, self.timer_name.width())))
        self.timer_name.setToolTip(name)
        self.pause_button.setText('Pause' if c.running else 'Resume')
        self.timer_status.setText(c.message)
        self.timer_status.setObjectName('error' if c.message else 'faint')
        self.widget_button.setText('Hide desktop widget' if self.win.widget.shown else 'Show desktop widget')

    # ---- add hours --------------------------------------------------------------------------
    def add_entry(self) -> Entry | None:
        hours = self.quick_hours.value()
        if not self.quick_project.currentText().strip():
            self.quick_status.setText('Choose a project.')
            return None
        if hours <= 0:
            self.quick_status.setText('Enter the hours.')
            return None
        project_id = self.win.ensure_project(self.quick_project, self)
        if not project_id:
            self.quick_status.setText('Choose a project from the list.')
            return None
        entry = Entry(project_id=project_id, engineer=self.win.user, date=from_qdate(self.quick_date.date()).isoformat(),
                      minutes=max(1, round(hours * 60)), note=self.quick_note.text().strip(), source='batch')
        try:
            self.win.store.save_entry(entry, new=True)
        except (ValueError, OSError) as problem:
            self.quick_status.setText(str(problem))
            return None
        # Keep the project and date so several days or several jobs can be added quickly.
        self.quick_hours.setValue(0.0)
        self.quick_note.clear()
        self.week_anchor = date.fromisoformat(entry.date)
        self.win.refresh_pages()
        self.quick_status.setText(f'Added {fmt_h(entry.hours)} to {self.win.store.projects[project_id].name}.')
        self.quick_hours.setFocus()
        return entry

    # ---- my entries -------------------------------------------------------------------------
    def shift_week(self, days: int) -> None:
        self.week_anchor += timedelta(days=days)
        self.refresh_mine()

    def refresh_mine(self) -> None:
        store, me = self.win.store, self.win.user.casefold()
        week = calc.week_of(self.week_anchor)
        own = [e for e in store.live_entries() if e.engineer.casefold() == me]
        mine = sorted((e for e in own if week.contains(e.date)), key=lambda e: (e.date, e.created_at))
        name = lambda e: store.projects[e.project_id].name if e.project_id in store.projects else 'Unknown project'
        rows = [[(fmt_date(e.date), e.date), name(e), (f'{e.hours:,.2f}', e.hours), e.note,
                 'Timer' if e.source == 'timer' else 'Added'] for e in mine]
        set_rows(self.mine, rows, [e.id for e in mine])
        fit_rows(self.mine, 3, 10)
        total = sum(e.hours for e in mine)
        self.week_label.setText(week.label)
        self.week_total.setText(f'{fmt_h(total)} this week')
        today = date.today().isoformat()
        by_day: dict = {}
        for e in mine:
            by_day[e.date] = by_day.get(e.date, 0.0) + e.hours
        days = [week.start + timedelta(days=i) for i in range(7)]
        self.week_chart.set_points([(f'{d:%a}', by_day.get(d.isoformat(), 0.0)) for d in days])
        self.week_hours.setText(fmt_h(total))
        self.week_sub.setText(f'{len(mine)} entr{"y" if len(mine) == 1 else "ies"}  ·  {fmt_h(by_day.get(today, 0.0))} today')
        totals: dict = {}
        for e in own:
            if e.source != 'opening' and e.project_id in store.projects:
                totals[e.project_id] = totals.get(e.project_id, 0.0) + e.hours
        ranked = sorted(totals.items(), key=lambda kv: -kv[1])[:6]
        self.my_projects.set_rows([(pid, store.projects[pid].name, hours, fmt_h(hours)) for pid, hours in ranked])

    def edit_mine(self) -> None:
        entry = self.win.store.entries.get(selected_id(self.mine) or '')
        if entry and EntryDialog(self.win, entry).exec():
            self.win.refresh_pages()

    def delete_mine(self) -> None:
        identifier = selected_id(self.mine)
        if identifier and self.win.confirm('Delete entry', 'Delete the selected entry?', self):
            try:
                self.win.store.delete_entry(identifier)
            except OSError as problem:
                QMessageBox.warning(self, 'Not deleted', f'The entry could not be deleted.\n\n{problem}')
            self.win.refresh_pages()

    def refresh(self) -> None:
        """Called after any change or sync. Text being typed in the pickers is left alone."""
        self.hero.restyle()
        self.timer_project.reload(self.win.store)
        self.quick_project.reload(self.win.store)
        self.refresh_mine()
        self.update_timer_view()
