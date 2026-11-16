from datetime import date, datetime, timedelta

import pytest
from PySide6.QtWidgets import QApplication

from det import calc
from det.models import Entry, Project
from det.settings import Settings
from det.store import Store
from det.timer import TimerState


@pytest.fixture(scope='session')
def app():
    from det.theme import apply_theme
    instance = QApplication.instance() or QApplication([])
    apply_theme(instance, 'light')
    return instance


def build(tmp_path, seed=False, timer=None):
    from det.ui.main_window import MainWindow
    store = Store(tmp_path / 'shared')
    store.load()
    if seed:
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
    settings.set('user_name', 'Sam')
    if timer:
        settings.set('timer', timer)
    return MainWindow(store, settings)


def test_everyone_gets_every_page(app, tmp_path):
    win = build(tmp_path)
    assert list(win.nav) == ['log', 'dashboard', 'reports', 'settings']          # no Projects tab, no manager gate
    assert not hasattr(win, 'lock') and not hasattr(win, 'manager')
    for key in win.nav:
        assert win.nav[key].isEnabled()
        win.show_page(key)
        assert win.current_page == key
    assert win.pages['settings'].shared_card.isVisibleTo(win.pages['settings'])
    win.grab()


def test_batch_save(app, tmp_path):
    win = build(tmp_path, seed=True)
    log = win.pages['log']
    a, b = [p.id for p in win.store.live_projects()][:2]
    before = len(win.store.live_entries())
    seeded = set(win.store.entries)
    log.clear_batch()
    log.add_batch_row(a, date(2026, 11, 12), 2.5, 'B', 'frame checks')
    log.add_batch_row(b, date(2026, 11, 13), 0.75)
    assert log.save_batch() == 2
    new = sorted((e for e in win.store.live_entries() if e.id not in seeded), key=lambda e: e.date)
    assert len(win.store.live_entries()) == before + 2
    assert [(e.minutes, e.engineer, e.date) for e in new] == [(150, 'Sam', '2026-11-12'), (45, 'Sam', '2026-11-13')]
    assert new[0].revision == 'B' and new[0].note == 'frame checks'


def test_batch_rejects_incomplete_row(app, tmp_path):
    win = build(tmp_path, seed=True)
    log = win.pages['log']
    before = len(win.store.live_entries())
    log.clear_batch()
    log.add_batch_row(None, date(2026, 11, 12), 2.0)
    assert log.save_batch() == 0
    assert 'Row 1' in log.batch_status.text()
    assert len(win.store.live_entries()) == before


def test_timer_creates_entry(app, tmp_path):
    win = build(tmp_path, seed=True)
    log = win.pages['log']
    clock = [datetime(2026, 11, 13, 9, 0, 0)]
    log.now = lambda: clock[0]
    project = win.store.live_projects()[0].id
    log.start_timer(project, 'C', 'cert')
    assert win.settings.get('timer')['project_id'] == project      # survives a restart
    clock[0] += timedelta(minutes=90)
    entry = log.stop_timer()
    assert (entry.minutes, entry.source, entry.date, entry.engineer) == (90, 'timer', '2026-11-13', 'Sam')
    assert entry.revision == 'C' and entry.note == 'cert'
    assert win.settings.get('timer') is None and win.store.entries[entry.id].minutes == 90


def test_timer_requires_project(app, tmp_path):
    win = build(tmp_path, seed=True)
    log = win.pages['log']
    log.start_timer(None)
    assert log.timer is None


def test_timer_restored(app, tmp_path):
    state = TimerState.start('missing-project', now=datetime(2026, 11, 13, 9, 0, 0))
    state.pause(datetime(2026, 11, 13, 9, 30, 0))
    win = build(tmp_path, seed=True, timer=state.to_dict())
    log = win.pages['log']
    assert log.timer is not None and not log.timer.running
    assert log.elapsed.text() == '0:30:00'


def test_dashboard_matches_calculation(app, tmp_path):
    from det.ui.common import fmt_h, fmt_money
    win = build(tmp_path, seed=True)
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


def test_reports_page(app, tmp_path):
    win = build(tmp_path, seed=True)
    page = win.pages['reports']
    page.set_kind('Month', date.today())
    report = page.current_report()
    assert report.headline['discounted_h'] == pytest.approx(6.0)
    assert 'Tower A' in page.preview.toPlainText()


def test_import_dialog_commits(app, tmp_path):
    from det.importer import ImportRow
    from det.ui.dialogs import ImportDialog
    win = build(tmp_path)
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


def test_project_and_entry_dialogs(app, tmp_path):
    from det.ui.dialogs import EntryDialog, ProjectDetailDialog, ProjectDialog
    win = build(tmp_path, seed=True)
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


def test_dark_theme_and_sync_reload(app, tmp_path):
    from det.theme import apply_theme
    win = build(tmp_path, seed=True)
    apply_theme(app, 'dark')
    win.grab()
    apply_theme(app, 'light')
    other = Store(win.store.directory)
    other.load()
    other.save_project(Project(name='Added elsewhere'), new=True)
    win.check_sync()
    assert any(p.name == 'Added elsewhere' for p in win.store.live_projects())


def test_batch_card_grows_with_rows(app, tmp_path):
    win = build(tmp_path, seed=True)
    win.resize(1200, 900)
    win.show()
    app.processEvents()
    log = win.pages['log']
    card_frame = log.batch_table.parentWidget()
    before = card_frame.height()
    log.add_batch_row()
    app.processEvents()
    from det.ui.log_page import BATCH_ROW
    assert card_frame.height() == before + BATCH_ROW
    win.close()


def test_shared_folder_unavailable_shows_banner(app, tmp_path):
    import shutil
    win = build(tmp_path, seed=True)
    shutil.rmtree(win.store.directory)
    blocker = win.store.directory
    blocker.write_text('not a folder')            # the folder cannot be recreated: simulates a missing drive
    win.check_sync()
    assert 'cannot be reached' in win.banner.text()
    assert len(win.store.live_projects()) == 2    # last loaded data stays on screen


# ---- floating timer widget ------------------------------------------------------------------
def shown(app, tmp_path, size=(1200, 800)):
    win = build(tmp_path, seed=True)
    win.resize(*size)
    win.show()
    app.processEvents()
    return win, win.pages['log'], win.pages['log'].mini


def mouse(widget, kind, local, offset=(0, 0)):
    """Send one left-button mouse event; `offset` shifts the global position, as a real drag would."""
    from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    kinds = {'press': QEvent.MouseButtonPress, 'move': QEvent.MouseMove, 'release': QEvent.MouseButtonRelease}
    point = QPoint(*local)
    there = widget.mapToGlobal(point) + QPoint(*offset)
    QApplication.sendEvent(widget, QMouseEvent(kinds[kind], QPointF(point), QPointF(there), Qt.LeftButton,
                                               Qt.LeftButton, Qt.NoModifier))


def test_floating_timer_is_docked_over_every_page(app, tmp_path):
    win, log, ft = shown(app, tmp_path)
    host = win.centralWidget()
    assert ft.parentWidget() is host and not ft.detached and ft.isVisible()
    assert host.rect().contains(ft.geometry())
    for key in ('dashboard', 'reports', 'settings'):
        win.show_page(key)
        app.processEvents()
        assert ft.isVisible()
    win.close()


def test_floating_timer_start_pause_resume_stop(app, tmp_path):
    win, log, ft = shown(app, tmp_path)
    clock = [datetime(2026, 11, 13, 9, 0, 0)]
    log.now = lambda: clock[0]
    ft.project.set_project(win.store.live_projects()[0].id)
    ft.start.click()
    assert log.timer and log.timer.running and ft.running_box.isVisible() and not ft.idle_box.isVisible()
    assert ft.pause.text() == 'Pause'
    clock[0] += timedelta(minutes=20)
    ft.pause.click()
    assert not log.timer.running and ft.pause.text() == 'Resume'
    clock[0] += timedelta(minutes=45)                       # paused time must not count
    ft.pause.click()
    assert log.timer.running and ft.pause.text() == 'Pause'
    clock[0] += timedelta(minutes=10)
    before = len(win.store.live_entries())
    ft.stop.click()
    assert log.timer is None and len(win.store.live_entries()) == before + 1
    newest = max(win.store.live_entries(), key=lambda e: e.created_at + e.id if e.source == 'timer' else '')
    assert (newest.source, newest.minutes) == ('timer', 30)
    assert ft.idle_box.isVisible() and not ft.running_box.isVisible()
    win.close()


def test_floating_timer_needs_a_project(app, tmp_path):
    win, log, ft = shown(app, tmp_path)
    ft.project.set_project(None)
    ft.start.click()
    assert log.timer is None and 'project' in ft.title.text().lower()
    win.close()


def test_floating_timer_detach_and_dock(app, tmp_path):
    from PySide6.QtCore import Qt
    win, log, ft = shown(app, tmp_path)
    ft.detach.click()
    app.processEvents()
    assert ft.detached and ft.isWindow() and ft.isVisible() and ft.detach.text() == 'Dock'
    assert ft.windowFlags() & Qt.WindowStaysOnTopHint and ft.windowFlags() & Qt.FramelessWindowHint
    assert win.settings.get('timer_widget')['detached'] is True
    ft.detach.click()
    app.processEvents()
    assert not ft.detached and not ft.isWindow() and ft.parentWidget() is win.centralWidget() and ft.isVisible()
    assert win.centralWidget().rect().contains(ft.geometry())
    win.close()


@pytest.mark.parametrize('detached', [False, True])
def test_floating_timer_drag_and_resize(app, tmp_path, detached):
    from det.ui.floating_timer import MIN_H, MIN_W
    win, log, ft = shown(app, tmp_path)
    ft.set_detached(detached)
    app.processEvents()
    from PySide6.QtCore import QRect
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
    from PySide6.QtGui import QFont, QFontMetrics
    font = QFont(ft.font())
    font.setWeight(QFont.DemiBold)
    font.setPixelSize(ft.elapsed_px)
    assert QFontMetrics(font).horizontalAdvance('0:00:00') <= ft.elapsed.width()     # digits are never clipped
    win.close()


def test_floating_timer_stays_inside_a_shrinking_window(app, tmp_path):
    win, log, ft = shown(app, tmp_path)
    win.resize(760, 520)
    app.processEvents()
    assert win.centralWidget().rect().contains(ft.geometry())
    win.close()


def test_floating_timer_state_is_remembered(app, tmp_path):
    from PySide6.QtCore import QRect
    from det.ui.main_window import MainWindow
    win, log, ft = shown(app, tmp_path)
    ft.set_detached(True)
    ft.place(QRect(100, 120, 400, 200))
    win.close()
    again = MainWindow(win.store, win.settings)
    restored = again.pages['log'].mini
    assert restored.detached and restored.geometry() == QRect(100, 120, 400, 200)
    again.close()


def test_floating_timer_hide_and_show(app, tmp_path):
    win, log, ft = shown(app, tmp_path)
    ft.hide_button.click()
    assert not ft.shown and not ft.isVisible() and log.widget_button.text() == 'Show widget'
    log.widget_button.click()
    assert ft.shown and ft.isVisible() and log.widget_button.text() == 'Hide widget'
    win.close()


def test_dashboard_lists_are_not_clipped(app, tmp_path):
    """Data arriving while another page is showing must not leave the dashboard lists cut short."""
    win = build(tmp_path)
    win.resize(1360, 1500)
    win.show()
    app.processEvents()
    for i in range(9):
        win.store.save_project(Project(name=f'Imported {i}', region='NSW', opening_amount=1000.0 + i), new=True)
    win.refresh_pages()
    win.show_page('dashboard')
    app.processEvents()
    top = win.pages['dashboard'].top
    card_frame = top.parentWidget()
    assert len(top.rows) == 8 and top.height() >= top.sizeHint().height()
    assert card_frame.height() >= top.geometry().bottom()            # the card is tall enough to show every row
    win.close()
