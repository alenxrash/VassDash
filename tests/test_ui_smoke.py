from datetime import date, datetime, timedelta

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QFont, QFontMetrics, QMouseEvent
from PySide6.QtWidgets import QApplication

from det import calc, locate
from det.models import Entry, Project
from det.settings import Settings
from det.store import Store
from det.timer import TimerState


@pytest.fixture(scope='session')
def app():
    from det.theme import apply_theme
    instance = QApplication.instance() or QApplication([])
    apply_theme(instance, 'dark')
    return instance


@pytest.fixture
def make(app, tmp_path):
    """Build main windows on a throwaway data folder; everything is shut down after the test."""
    from det.ui.main_window import MainWindow
    made = []

    def build(seed=False, timer=None, name='Sam', shared=True, show=False):
        store = Store(tmp_path / 'shared')
        store.load()
        if seed and not store.projects:
            a = Project(name='Tower A', region='QLD', quoted_hours=10, reason_category='Good client')
            b = Project(name='Mezzanine', region='NSW')
            for p in (a, b):
                store.save_project(p, new=True)
            today = date.today().isoformat()
            for p, d, h, who in [(a, today, 8, 'Sam'), (a, today, 6, 'Lee'), (b, today, 2, 'Sam'), (b, None, 3, 'Sam')]:
                store.save_entry(Entry(project_id=p.id, engineer=who, date=d, minutes=h * 60,
                                       source='opening' if d is None else 'batch'), new=True)
        settings = Settings(tmp_path / 'local' / 'settings.json')
        settings.load()
        if name:
            settings.set('user_name', name)
        if timer:
            settings.set('timer', timer)
        win = MainWindow(store, settings, locate.Location(store.directory, shared))
        win.confirm = lambda title, text, parent=None: True          # say yes to every question
        made.append(win)
        if show:
            win.resize(1240, 820)
            win.show()
            app.processEvents()
        return win

    yield build
    for win in made:
        win.shutdown()


def mouse(widget, kind, local, offset=(0, 0)):
    """Send one left-button mouse event; `offset` shifts the global position, as a real drag would."""
    kinds = {'press': QEvent.MouseButtonPress, 'move': QEvent.MouseMove, 'release': QEvent.MouseButtonRelease}
    point = QPoint(*local)
    there = widget.mapToGlobal(point) + QPoint(*offset)
    QApplication.sendEvent(widget, QMouseEvent(kinds[kind], QPointF(point), QPointF(there), Qt.LeftButton,
                                               Qt.LeftButton, Qt.NoModifier))


# ---- no setup, one view ---------------------------------------------------------------------
def test_opens_ready_to_use_with_no_setup(app, make):
    win = make(name='')                                   # nothing was ever typed in
    assert win.user.strip()                               # name comes from the computer
    assert list(win.nav) == ['time', 'dashboard', 'reports']
    assert not hasattr(win, 'lock') and not hasattr(win, 'manager')
    for key in win.nav:
        win.show_page(key)
        assert win.current_page == key
    assert not win.local_box.isVisibleTo(win)             # team folder in use: no notice
    win.grab()


def test_settings_are_optional_and_open_to_everyone(app, make):
    from det.ui.settings_page import SettingsPage
    win = make()
    page = SettingsPage(win)
    assert page.shared_card.isVisibleTo(page) and page.name.text() == 'Sam'
    assert 'team folder' in page.folder.text()
    page.rate.setValue(240.0)
    page.save_shared()
    assert win.store.config.rate == 240.0


def test_notice_when_team_folder_is_missing_and_connecting_moves_local_work(app, make, tmp_path):
    win = make(shared=False, show=True)
    assert win.local_box.isVisible() and win.connect_button.isVisible()
    assert 'saved here only' in win.local_note.text()
    project = Project(name='Local job')
    win.store.save_project(project, new=True)
    win.store.save_entry(Entry(project_id=project.id, engineer='Sam', date='2026-11-16', minutes=45), new=True)
    team = tmp_path / 'Team' / locate.DATA_FOLDER
    team.mkdir(parents=True)
    win.use_folder(str(team))
    assert win.location.shared and win.location.merged == 2 and win.store.directory == team
    assert [p.name for p in win.store.live_projects()] == ['Local job'] and len(win.store.live_entries()) == 1
    assert not win.connect_button.isVisible() and 'moved' in win.local_note.text()
    assert win.settings.get('data_mode') == 'shared'


# ---- adding hours with the fewest inputs ------------------------------------------------------
def test_add_hours_in_one_line(app, make):
    win = make(seed=True)
    page = win.pages['time']
    project = win.store.live_projects()[0]
    before = set(win.store.entries)
    page.quick_project.set_project(project.id)
    page.quick_hours.setValue(2.5)
    entry = page.add_entry()
    assert entry and set(win.store.entries) - before == {entry.id}
    assert (entry.minutes, entry.engineer, entry.date, entry.source) == (150, 'Sam', date.today().isoformat(), 'batch')
    # ready for the next line: project and date kept, hours cleared
    assert page.quick_project.project_id() == project.id and page.quick_hours.value() == 0
    assert 'Added 2.50 h' in page.quick_status.text()


def test_add_hours_needs_a_project_and_hours(app, make):
    win = make(seed=True)
    page = win.pages['time']
    before = len(win.store.entries)
    page.quick_hours.setValue(1.0)
    assert page.add_entry() is None and 'project' in page.quick_status.text().lower()
    page.quick_project.set_project(win.store.live_projects()[0].id)
    page.quick_hours.setValue(0.0)
    assert page.add_entry() is None and 'hours' in page.quick_status.text().lower()
    assert len(win.store.entries) == before


def test_typing_a_new_name_creates_the_project(app, make):
    win = make(seed=True)
    page = win.pages['time']
    page.quick_project.setEditText('Brand new job')
    page.quick_hours.setValue(1.0)
    win.confirm = lambda *a, **k: False                   # person says no: nothing is created
    assert page.add_entry() is None and all(p.name != 'Brand new job' for p in win.store.live_projects())
    win.confirm = lambda *a, **k: True
    entry = page.add_entry()
    created = next(p for p in win.store.live_projects() if p.name == 'Brand new job')
    assert entry.project_id == created.id and created.lead_engineer == 'Sam' and created.created_by == 'Sam'


# ---- timer ------------------------------------------------------------------------------------
def test_timer_from_the_window(app, make):
    win = make(seed=True)
    page, c = win.pages['time'], win.controller
    clock = [datetime(2026, 11, 13, 9, 0, 0)]
    c.now = lambda: clock[0]
    page.start_button.click()                             # no project picked
    assert not c.active and 'project' in page.timer_status.text().lower()
    project = win.store.live_projects()[0].id
    page.timer_project.set_project(project)
    page.start_button.click()
    assert c.running and win.settings.get('timer')['project_id'] == project      # survives a restart
    clock[0] += timedelta(minutes=90)
    c.changed.emit()
    assert page.elapsed.text() == '1:30:00' and win.timer_button.text().endswith('1:30:00')
    page.stop_button.click()
    entry = max((e for e in win.store.live_entries() if e.source == 'timer'), key=lambda e: e.created_at)
    assert (entry.minutes, entry.date, entry.engineer) == (90, '2026-11-13', 'Sam')
    assert not c.active and win.settings.get('timer') is None and win.timer_button.text() == 'Timer'


def test_timer_is_restored_after_restart(app, make):
    state = TimerState.start('missing-project', now=datetime(2026, 11, 13, 9, 0, 0))
    state.pause(datetime(2026, 11, 13, 9, 30, 0))
    win = make(seed=True, timer=state.to_dict())
    assert win.controller.active and not win.controller.running
    assert win.pages['time'].elapsed.text() == '0:30:00' and win.widget.elapsed.text() == '0:30:00'
    win.widget.stop.click()                               # its project is gone: nothing saved, message shown
    assert win.controller.active and 'no longer exists' in win.controller.message


def test_widget_start_pause_resume_stop(app, make):
    win = make(seed=True, show=True)
    ft, c = win.widget, win.controller
    clock = [datetime(2026, 11, 13, 9, 0, 0)]
    c.now = lambda: clock[0]
    ft.start.click()                                      # nothing picked yet
    assert not c.active and 'project' in ft.title.text().lower()
    ft.project.set_project(win.store.live_projects()[0].id)
    ft.start.click()
    assert c.running and ft.running_box.isVisible() and not ft.idle_box.isVisible() and ft.pause.text() == 'Pause'
    clock[0] += timedelta(minutes=20)
    ft.pause.click()
    assert not c.running and ft.pause.text() == 'Resume'
    clock[0] += timedelta(minutes=45)                     # paused time must not count
    ft.pause.click()
    assert c.running and ft.pause.text() == 'Pause'
    clock[0] += timedelta(minutes=10)
    before = len(win.store.live_entries())
    ft.stop.click()
    assert not c.active and len(win.store.live_entries()) == before + 1
    newest = max((e for e in win.store.live_entries() if e.source == 'timer'), key=lambda e: e.created_at)
    assert newest.minutes == 30
    assert ft.idle_box.isVisible() and not ft.running_box.isVisible()


def test_widget_can_create_a_project_by_name(app, make):
    win = make(seed=True)
    win.widget.project.setEditText('Site visit job')
    win.widget.start.click()
    assert win.controller.running and win.controller.project_name == 'Site visit job'


# ---- the widget is its own window ---------------------------------------------------------------
def test_widget_is_a_separate_always_on_top_window(app, make):
    win = make(seed=True, show=True)
    ft = win.widget
    assert ft.isWindow() and ft.parentWidget() is None and ft.isVisible()
    assert ft.windowFlags() & Qt.WindowStaysOnTopHint and ft.windowFlags() & Qt.FramelessWindowHint
    ft.set_on_top(False)
    assert not (ft.windowFlags() & Qt.WindowStaysOnTopHint) and ft.isVisible()
    assert win.settings.get('timer_widget')['on_top'] is False


def test_timer_keeps_running_when_the_main_window_is_closed(app, make):
    win = make(seed=True, show=True)
    ft, c = win.widget, win.controller
    clock = [datetime(2026, 11, 13, 9, 0, 0)]
    c.now = lambda: clock[0]
    ft.project.set_project(win.store.live_projects()[0].id)
    ft.start.click()
    win.close()
    app.processEvents()
    assert not win.isVisible() and ft.isVisible() and c.running
    clock[0] += timedelta(minutes=15)
    before = len(win.store.live_entries())
    ft.stop.click()
    assert len(win.store.live_entries()) == before + 1
    ft.open_button.click()                                # and the window can be brought back
    assert win.isVisible()


def test_app_is_never_left_running_out_of_reach(app, make):
    win = make(seed=True, show=True)
    assert win.tray is None                               # no system tray in the test environment
    win.close()
    app.processEvents()
    win.widget.hide_button.click()                        # hiding the last thing on screen reopens the window
    assert win.isVisible() and not win.widget.isVisible()
    win.close()                                           # now nothing else is showing: closing really quits
    assert win._quitting


def test_widget_drag_and_resize(app, make):
    from det.ui.timer_widget import MIN_H, MIN_W
    win = make(seed=True, show=True)
    ft = win.widget
    ft.place(QRect(100, 100, 360, 140))
    start = ft.geometry()
    mouse(ft, 'press', (start.width() // 2, 14))
    mouse(ft, 'move', (start.width() // 2, 14), offset=(-40, -30))
    mouse(ft, 'release', (start.width() // 2, 14))
    moved = ft.geometry()
    assert (moved.x() - start.x(), moved.y() - start.y()) == (-40, -30) and moved.size() == start.size()
    small = ft.elapsed_px
    corner = (moved.width() - 2, moved.height() - 2)
    mouse(ft, 'press', corner)
    mouse(ft, 'move', corner, offset=(120, 90))
    mouse(ft, 'release', corner)
    grown = ft.geometry()
    assert (grown.width(), grown.height()) == (moved.width() + 120, moved.height() + 90)
    assert grown.topLeft() == moved.topLeft() and ft.elapsed_px > small
    corner = (grown.width() - 2, grown.height() - 2)
    mouse(ft, 'press', corner)
    mouse(ft, 'move', corner, offset=(-2000, -2000))
    mouse(ft, 'release', corner)
    assert (ft.width(), ft.height()) == (MIN_W, MIN_H)
    font = QFont(ft.font())
    font.setWeight(QFont.DemiBold)
    font.setPixelSize(ft.elapsed_px)
    assert QFontMetrics(font).horizontalAdvance('0:00:00') <= ft.elapsed.width()     # digits are never clipped


def test_widget_starts_in_the_screen_corner_and_remembers_where_it_was_put(app, make):
    win = make(seed=True, show=True)
    ft = win.widget
    screen = app.primaryScreen().availableGeometry()
    assert screen.contains(ft.geometry()) and ft.geometry().right() > screen.center().x()
    ft.place(QRect(100, 120, 400, 200))
    ft.set_shown(False)
    win.shutdown()
    again = make(seed=True)
    assert again.widget.geometry() == QRect(100, 120, 400, 200) and not again.widget.shown
    assert again.pages['time'].widget_button.text() == 'Show desktop widget'
    again.pages['time'].widget_button.click()
    assert again.widget.shown and again.widget.isVisible()


# ---- dashboard, reports, dialogs ----------------------------------------------------------------
def test_dashboard_matches_calculation(app, make):
    from det.ui.common import fmt_h, fmt_money
    win = make(seed=True)
    dash = win.pages['dashboard']
    dash.set_period('All time')
    s = calc.summarise(win.store.live_projects(), win.store.live_entries(), 220.0, calc.all_time())
    assert dash.tiles['hours'].value.text() == fmt_h(s.discounted_h) == '9.00 h'
    assert dash.tiles['amount'].value.text() == fmt_money(s.amount) == '$1,980'
    assert dash.tiles['over'].value.text() == '1 of 1'
    assert dash.table.rowCount() == 2
    dash.set_period('This month')
    assert dash.tiles['hours'].value.text() == '6.00 h'
    big = Project(name='Amount only', region='VIC', opening_amount=20750.0)
    win.store.save_project(big, new=True)
    dash.set_period('All time')
    assert dash.tiles['amount'].value.text() == '$22,730'
    assert dash.top.rows[0][1] == 'Amount only' and '$20,750' in dash.top.rows[0][3]      # ranked by dollars
    assert dash.by_region.rows[0][:2] == ('VIC', 'VIC')
    win.show_page('dashboard')
    win.grab()


def test_dashboard_lists_are_not_clipped(app, make):
    """Data arriving while another page is showing must not leave the dashboard lists cut short."""
    win = make(show=True)
    for i in range(9):
        win.store.save_project(Project(name=f'Imported {i}', region='NSW', opening_amount=1000.0 + i), new=True)
    win.refresh_pages()
    win.show_page('dashboard')
    app.processEvents()
    top = win.pages['dashboard'].top
    assert len(top.rows) == 8 and top.height() >= top.sizeHint().height()
    assert top.parentWidget().height() >= top.geometry().bottom()


def test_charts_paint(app):
    from det.ui.charts import BarList, TrendChart
    bars, trend = BarList(), TrendChart()
    for widget in (bars, trend):
        widget.resize(400, 200)
        widget.grab()
    bars.set_rows([('a', 'Tower A', 14.0, '14.00 h'), ('b', 'A very long project name that must be elided', 0.0, '0 h')])
    trend.set_points([('2 Nov', 3.0), ('9 Nov', 0.0), ('16 Nov', 7.5)])
    bars.grab()
    trend.grab()


def test_reports_page(app, make):
    win = make(seed=True)
    page = win.pages['reports']
    page.set_kind('Month', date.today())
    report = page.current_report()
    assert report.headline['discounted_h'] == pytest.approx(6.0)
    assert 'Tower A' in page.preview.toPlainText()


def test_import_dialog_commits(app, make):
    from det.importer import ImportRow
    from det.ui.dialogs import ImportDialog
    win = make()
    rows = [ImportRow(3, name='Project 1', region='QLD', hours=3.0, amount=660.0),
            ImportRow(4, name='Project 2', region='VIC', hours=None, hours_text='15 & counting', needs_review=True)]
    dialog = ImportDialog(win, rows)
    dialog.table.item(1, dialog.COL_HOURS).setText('15')
    dialog.table.item(1, dialog.COL_AMOUNT).setText('$18,050')
    assert dialog.commit() == (2, 2)
    assert sorted(e.minutes for e in win.store.live_entries()) == [180, 900]
    assert sorted(p.opening_amount for p in win.store.live_projects()) == [660, 18050]
    dialog = ImportDialog(win, [ImportRow(5, name='Project 3', hours=None, hours_text='soon', needs_review=True)])
    dialog.table.item(0, dialog.COL_HOURS).setText('abc')
    assert dialog.commit() is None and 'Row 5' in dialog.error.text()


def test_project_and_entry_dialogs(app, make):
    from det.ui.dialogs import EntryDialog, ProjectDetailDialog, ProjectDialog
    win = make(seed=True)
    dialog = ProjectDialog(win)
    dialog.name.setText('New job')
    dialog.quoted.setText('12.5')
    assert dialog.save()
    created = next(p for p in win.store.live_projects() if p.name == 'New job')
    assert created.quoted_hours == 12.5 and created.created_by == 'Sam'
    edit = ProjectDialog(win, created)
    edit.amount.setText('1,800')
    assert edit.save() and win.store.projects[created.id].opening_amount == 1800
    edit = ProjectDialog(win, win.store.projects[created.id])
    edit.amount.setText('lots')
    assert not edit.save() and 'amount' in edit.error.text().lower()
    dialog = ProjectDialog(win)
    assert not dialog.save() and dialog.error.text()
    entry_dialog = EntryDialog(win, project_id=created.id)
    entry_dialog.hours.setValue(1.5)
    assert entry_dialog.save()
    assert any(e.project_id == created.id and e.minutes == 90 for e in win.store.live_entries())
    detail = ProjectDetailDialog(win, created.id)
    detail.grab()
    assert detail.delete_button.isVisibleTo(detail) and detail.edit_button.isVisibleTo(detail)


def test_themes_and_sync_reload(app, make):
    from det.theme import apply_theme
    win = make(seed=True)
    apply_theme(app, 'light')
    win.refresh_pages()
    win.grab()
    apply_theme(app, 'dark')
    other = Store(win.store.directory)
    other.load()
    other.save_project(Project(name='Added elsewhere'), new=True)
    win.check_sync()
    assert any(p.name == 'Added elsewhere' for p in win.store.live_projects())
    assert win.widget.project.findText('Added elsewhere') >= 0          # the widget's picker follows too


def test_data_folder_unavailable_shows_banner(app, make):
    import shutil
    win = make(seed=True)
    shutil.rmtree(win.store.directory)
    win.store.directory.write_text('not a folder')        # the folder cannot be recreated: simulates a missing drive
    win.check_sync()
    assert 'cannot be reached' in win.banner.text()
    assert len(win.store.live_projects()) == 2            # last loaded data stays on screen


def test_windows_sign_out_is_not_blocked(app, make):
    win = make(seed=True, show=True)
    win.close()
    assert not win._quitting and not win.isVisible()      # a normal close only hides
    win.show()
    win._session_ending()                                 # Windows is signing out or shutting down
    assert win.close() and win._quitting                  # the close is accepted this time
