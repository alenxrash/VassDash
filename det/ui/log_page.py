"""Log time: start/stop timer, batch entry, and the user's own entries for a week."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QDateEdit, QDoubleSpinBox, QHBoxLayout, QHeaderView, QInputDialog,
                               QLineEdit, QMessageBox, QPushButton, QTableWidget, QVBoxLayout, QWidget)

from .. import calc
from ..models import Entry
from ..timer import TimerState
from .charts import BarList, TrendChart
from .common import (Hero, ProjectCombo, card, fit_rows, fmt_date, fmt_h, from_qdate, label, make_table, page_scroll,
                     relayout, round_button, selected_id, set_rows, to_qdate)
from .dialogs import EntryDialog, ProjectDialog
from .floating_timer import FloatingTimer


BATCH_ROW = 46
BATCH_HEADER = 38


def clock_text(seconds: float) -> str:
    seconds = int(seconds)
    return f'{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}'


class LogPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.now = datetime.now
        self.timer: TimerState | None = None
        self.batch: list[dict] = []
        self.week_anchor = date.today()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll, body = page_scroll()
        outer.addWidget(scroll)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(32, 14, 32, 28)
        layout.setSpacing(18)

        head = QHBoxLayout()
        self.hero = Hero('Log', 'time', 'Start a timer, or enter a batch of hours against a project.')
        head.addWidget(self.hero, 1)
        new_project = QPushButton('New project')
        new_project.clicked.connect(self.new_project)
        head.addWidget(new_project, 0, Qt.AlignBottom)
        layout.addLayout(head)

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

        # Timer: the lit card
        frame, box = card('Timer', hero=True)
        row = QHBoxLayout()
        self.timer_project = ProjectCombo(win.store)
        self.timer_rev = QLineEdit()
        self.timer_rev.setPlaceholderText('Rev')
        self.timer_rev.setFixedWidth(90)
        self.timer_note = QLineEdit()
        self.timer_note.setPlaceholderText('Note (optional)')
        row.addWidget(self.timer_project, 2)
        row.addWidget(self.timer_rev)
        row.addWidget(self.timer_note, 3)
        box.addLayout(row)
        row = QHBoxLayout()
        self.elapsed = label('0:00:00', 'timerValue')
        self.timer_status = label('', 'error')
        self.start_button = QPushButton('Start timer')
        self.start_button.setObjectName('primary')
        self.start_button.clicked.connect(self.start_clicked)
        self.pause_button = QPushButton('Pause')
        self.pause_button.clicked.connect(self.toggle_pause)
        self.stop_button = QPushButton('Stop && save')
        self.stop_button.setObjectName('primary')
        self.stop_button.clicked.connect(self.stop_clicked)
        self.discard_button = QPushButton('Discard')
        self.discard_button.clicked.connect(self.discard_clicked)
        pop = self.widget_button = QPushButton('Hide widget')
        pop.setToolTip('Show or hide the floating timer widget')
        pop.clicked.connect(self.pop_out)
        row.addWidget(self.elapsed)
        row.addWidget(self.timer_status, 1)
        for button in (self.start_button, self.pause_button, self.stop_button, self.discard_button, pop):
            row.addWidget(button)
        box.addLayout(row)
        left.addWidget(frame)

        # Batch
        frame, box = card('Batch entry')
        self.batch_table = QTableWidget(0, 6)
        self.batch_table.setHorizontalHeaderLabels(['Project', 'Date', 'Hours', 'Rev', 'Note', ''])
        self.batch_table.verticalHeader().setVisible(False)
        self.batch_table.verticalHeader().setDefaultSectionSize(BATCH_ROW)
        self.batch_table.setShowGrid(False)
        self.batch_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.batch_table.setFocusPolicy(Qt.NoFocus)
        header = self.batch_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Fixed)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setFixedHeight(BATCH_HEADER)
        for column, width in ((1, 150), (2, 84), (3, 70), (4, 130), (5, 92)):
            self.batch_table.setColumnWidth(column, width)
        box.addWidget(self.batch_table)
        row = QHBoxLayout()
        add = QPushButton('Add row')
        add.clicked.connect(lambda: self.add_batch_row())
        self.batch_status = label('', 'error')
        save = QPushButton('Save all')
        save.setObjectName('primary')
        save.clicked.connect(self.save_batch)
        row.addWidget(add)
        row.addWidget(self.batch_status, 1)
        row.addWidget(save)
        box.addLayout(row)
        left.addWidget(frame)

        # My entries
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
        self.mine = make_table(['Date', 'Project', 'Hours', 'Rev', 'Note', 'Source'], stretch=1)
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

        # Right rail
        frame, box = card('This week')
        self.week_hours = label('0.00 h', 'tileValue')
        self.week_sub = label('', 'faint')
        self.week_chart = TrendChart('No hours logged this week')
        self.week_chart.setMinimumHeight(150)
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

        self.mini = FloatingTimer(self, win.centralWidget())      # floats over every page; can be detached
        self.add_batch_row()
        self.ticker = QTimer(self)
        self.ticker.setInterval(1000)
        self.ticker.timeout.connect(self.update_timer_view)
        self.ticker.start()
        saved = win.settings.get('timer')
        if saved:
            self.timer = TimerState.from_dict(saved)
            if self.timer:
                self.timer_project.set_project(self.timer.project_id)
                self.timer_rev.setText(self.timer.revision)
                self.timer_note.setText(self.timer.note)
        self.refresh()

    # ---- timer -----------------------------------------------------------------------------
    def _persist(self) -> None:
        self.win.settings.set('timer', self.timer.to_dict() if self.timer else None)

    def start_timer(self, project_id, revision: str = '', note: str = '') -> None:
        if self.timer:
            return
        if not project_id or project_id not in self.win.store.projects:
            self.timer_status.setText('Choose a project first.')
            return
        self.timer = TimerState.start(project_id, revision, note, self.now())
        self.timer_project.set_project(project_id)
        self.timer_rev.setText(revision)
        self.timer_note.setText(note)
        self.timer_status.setText('')
        self._persist()
        self.update_timer_view()

    def start_clicked(self) -> None:
        self.start_timer(self.timer_project.project_id(), self.timer_rev.text().strip(), self.timer_note.text().strip())

    def toggle_pause(self) -> None:
        if not self.timer:
            return
        if self.timer.running:
            self.timer.pause(self.now())
        else:
            self.timer.resume(self.now())
        self._persist()
        self.update_timer_view()

    def stop_timer(self, hours: float | None = None) -> Entry | None:
        """Save the running timer as an entry. `hours` overrides the measured time (used after a long run)."""
        if not self.timer:
            return None
        minutes, started, ended, day = self.timer.finish(self.now())
        if hours is not None:
            minutes = max(1, round(hours * 60))
        entry = Entry(project_id=self.timer.project_id, engineer=self.win.user, date=day, minutes=min(minutes, 1440),
                      revision=self.timer_rev.text().strip() or self.timer.revision,
                      note=self.timer_note.text().strip() or self.timer.note,
                      source='timer', started_at=started, ended_at=ended)
        try:
            if entry.project_id not in self.win.store.projects:
                raise ValueError('The project for this timer no longer exists. Choose a project, or discard the timer.')
            self.win.store.save_entry(entry, new=True)
        except (ValueError, OSError) as problem:
            self.timer_status.setText(str(problem))
            return None
        self.timer = None
        self._persist()
        self.timer_rev.clear()
        self.timer_note.clear()
        self.timer_status.setText('')
        self.win.refresh_pages()
        return entry

    def stop_clicked(self) -> None:
        if not self.timer:
            return
        if self.timer.project_id not in self.win.store.projects and self.timer_project.project_id():
            self.timer.project_id = self.timer_project.project_id()
        hours = None
        if self.timer.is_long(self.now()):
            measured = self.timer.elapsed_s(self.now()) / 3600
            hours, ok = QInputDialog.getDouble(
                self, 'Long timer', f'This timer ran for {measured:.1f} hours. Was it left running?\n'
                'Hours to save:', min(measured, 24.0), 0.02, 24.0, 2)
            if not ok:
                return
        self.stop_timer(hours)

    def discard_clicked(self) -> None:
        if self.timer and QMessageBox.question(self, 'Discard timer', 'Discard this timer without saving?') == QMessageBox.Yes:
            self.timer = None
            self._persist()
            self.update_timer_view()

    def pop_out(self) -> None:
        self.mini.set_shown(not self.mini.shown)

    def update_timer_view(self) -> None:
        active = self.timer is not None
        running = bool(active and self.timer.running)
        text = clock_text(self.timer.elapsed_s(self.now())) if active else '0:00:00'
        self.elapsed.setText(text)
        self.start_button.setVisible(not active)
        self.pause_button.setVisible(active)
        self.pause_button.setText('Pause' if running else 'Resume')
        self.stop_button.setVisible(active)
        self.discard_button.setVisible(active)
        known = active and self.timer.project_id in self.win.store.projects
        self.timer_project.setEnabled(not known)
        name = self.win.store.projects[self.timer.project_id].name if known else 'Timer'
        self.mini.update_view(name, text, active, running)
        self.widget_button.setText('Hide widget' if self.mini.shown else 'Show widget')

    # ---- batch -----------------------------------------------------------------------------
    def add_batch_row(self, project_id=None, day: date | None = None, hours: float = 0.0, revision: str = '',
                      note: str = '') -> None:
        widgets = {'project': ProjectCombo(self.win.store), 'date': QDateEdit(to_qdate(day or date.today())),
                   'hours': QDoubleSpinBox(), 'rev': QLineEdit(revision), 'note': QLineEdit(note),
                   'remove': QPushButton('Remove')}
        widgets['project'].set_project(project_id)
        widgets['date'].setCalendarPopup(True)
        widgets['date'].setDisplayFormat('dd/MM/yyyy')
        widgets['hours'].setRange(0.0, 24.0)
        widgets['hours'].setDecimals(2)
        widgets['hours'].setSingleStep(0.25)
        widgets['hours'].setValue(hours)
        widgets['remove'].setObjectName('link')
        widgets['remove'].clicked.connect(lambda: self.remove_batch_row(widgets))
        index = self.batch_table.rowCount()
        self.batch_table.insertRow(index)
        for column, key in enumerate(('project', 'date', 'hours', 'rev', 'note', 'remove')):
            holder = QWidget()                      # a little air around each rounded control
            inner = QHBoxLayout(holder)
            inner.setContentsMargins(4, 4, 4, 4)
            inner.addWidget(widgets[key])
            self.batch_table.setCellWidget(index, column, holder)
        self.batch.append(widgets)
        self._size_batch()

    def remove_batch_row(self, widgets) -> None:
        index = self.batch.index(widgets)
        self.batch.pop(index)
        self.batch_table.removeRow(index)
        if not self.batch:
            self.add_batch_row()
        self._size_batch()

    def clear_batch(self) -> None:
        self.batch.clear()
        self.batch_table.setRowCount(0)
        self._size_batch()

    def _size_batch(self) -> None:
        rows = max(1, self.batch_table.rowCount())
        self.batch_table.setFixedHeight(BATCH_HEADER + rows * BATCH_ROW + 6)
        relayout(self.batch_table)

    def save_batch(self) -> int:
        """All rows are checked before any is saved, so a mistake never leaves half a batch behind."""
        entries = []
        for number, w in enumerate(self.batch, start=1):
            project_id, hours = w['project'].project_id(), w['hours'].value()
            typed = w['project'].currentText().strip()
            if not project_id and not typed and hours == 0 and not w['note'].text().strip():
                continue                                    # an untouched blank row
            if not project_id:
                self.batch_status.setText(f'Row {number}: choose a project from the list.')
                return 0
            if hours <= 0:
                self.batch_status.setText(f'Row {number}: enter the hours.')
                return 0
            entries.append(Entry(project_id=project_id, engineer=self.win.user,
                                 date=from_qdate(w['date'].date()).isoformat(), minutes=max(1, round(hours * 60)),
                                 revision=w['rev'].text().strip(), note=w['note'].text().strip(), source='batch'))
        if not entries:
            self.batch_status.setText('Nothing to save yet.')
            return 0
        try:
            for entry in entries:
                self.win.store.save_entry(entry, new=True)
        except (ValueError, OSError) as problem:
            self.batch_status.setText(str(problem))
            self.win.refresh_pages()
            return 0
        self.clear_batch()
        self.add_batch_row()
        self.batch_status.setText('')
        self.week_anchor = date.fromisoformat(entries[-1].date)
        self.win.refresh_pages()
        return len(entries)

    # ---- my entries ------------------------------------------------------------------------
    def shift_week(self, days: int) -> None:
        self.week_anchor += timedelta(days=days)
        self.refresh_mine()

    def refresh_mine(self) -> None:
        store = self.win.store
        week = calc.week_of(self.week_anchor)
        mine = sorted((e for e in store.live_entries() if e.engineer == self.win.user and week.contains(e.date)),
                      key=lambda e: (e.date, e.created_at))
        name = lambda e: store.projects[e.project_id].name if e.project_id in store.projects else 'Unknown project'
        rows = [[(fmt_date(e.date), e.date), name(e), (f'{e.hours:,.2f}', e.hours), e.revision, e.note,
                 'Timer' if e.source == 'timer' else 'Batch'] for e in mine]
        set_rows(self.mine, rows, [e.id for e in mine])
        fit_rows(self.mine, 3, 10)
        total = sum(e.hours for e in mine)
        self.week_label.setText(week.label)
        self.week_total.setText(f'{fmt_h(total)} this week')
        today = date.today().isoformat()
        by_day = {}
        for e in mine:
            by_day[e.date] = by_day.get(e.date, 0.0) + e.hours
        days = [week.start + timedelta(days=i) for i in range(7)]
        self.week_chart.set_points([(f'{d:%a}', by_day.get(d.isoformat(), 0.0)) for d in days])
        self.week_hours.setText(fmt_h(total))
        self.week_sub.setText(f'{len(mine)} entr{"y" if len(mine) == 1 else "ies"}  ·  {fmt_h(by_day.get(today, 0.0))} today')
        totals = {}
        for e in store.live_entries():
            if e.engineer == self.win.user and e.source != 'opening' and e.project_id in store.projects:
                totals[e.project_id] = totals.get(e.project_id, 0.0) + e.hours
        ranked = sorted(totals.items(), key=lambda kv: -kv[1])[:6]
        self.my_projects.set_rows([(pid, store.projects[pid].name, hours, fmt_h(hours)) for pid, hours in ranked])

    def edit_mine(self) -> None:
        entry = self.win.store.entries.get(selected_id(self.mine) or '')
        if entry and EntryDialog(self.win, entry).exec():
            self.win.refresh_pages()

    def delete_mine(self) -> None:
        identifier = selected_id(self.mine)
        if identifier and QMessageBox.question(self, 'Delete entry', 'Delete the selected entry?') == QMessageBox.Yes:
            self.win.store.delete_entry(identifier)
            self.win.refresh_pages()

    def new_project(self) -> None:
        dialog = ProjectDialog(self.win)
        if dialog.exec():
            self.win.refresh_pages()
            if not self.timer:
                self.timer_project.set_project(dialog.saved.id)

    def refresh(self) -> None:
        """Called after any change or sync. Rows being typed in the batch table are left alone."""
        self.hero.restyle()
        self.timer_project.reload(self.win.store)
        self.mini.refresh(self.win.store)
        for widgets in self.batch:
            widgets['project'].reload(self.win.store)
        self.refresh_mine()
        self.update_timer_view()
