from datetime import datetime, timedelta

from det.auth import check_passcode, hash_passcode
from det.settings import Settings
from det.timer import TimerState

T0 = datetime(2026, 11, 13, 23, 50, 0)


def test_pause_excludes_time():
    t = TimerState.start('p1', now=T0)
    t.pause(T0 + timedelta(minutes=10))
    t.resume(T0 + timedelta(minutes=40))
    assert t.elapsed_s(T0 + timedelta(minutes=45)) == 15 * 60


def test_restore_running_and_paused():
    t = TimerState.start('p1', revision='B', note='frames', now=T0)
    later = T0 + timedelta(minutes=30)
    assert TimerState.from_dict(t.to_dict()).elapsed_s(later) == t.elapsed_s(later)
    t.pause(T0 + timedelta(minutes=5))
    back = TimerState.from_dict(t.to_dict())
    assert back.elapsed_s(later) == 5 * 60 and not back.running
    assert (back.revision, back.note) == ('B', 'frames')


def test_finish_minimum_and_start_date():
    t = TimerState.start('p1', now=T0)
    minutes, started, ended, day = t.finish(T0 + timedelta(seconds=20))
    assert minutes == 1
    minutes, started, ended, day = TimerState.start('p1', now=T0).finish(T0 + timedelta(minutes=90))
    assert minutes == 90 and day == '2026-11-13'      # crossed midnight, dated the start day
    assert started.startswith('2026-11-13T23:50') and ended.startswith('2026-11-14T01:20')


def test_long_run():
    t = TimerState.start('p1', now=T0)
    assert not t.is_long(T0 + timedelta(hours=11))
    assert t.is_long(T0 + timedelta(hours=13))


def test_settings_round_trip(tmp_path):
    s = Settings(tmp_path / 'deep' / 'settings.json')
    s.load()
    assert s.get('theme') == 'dark' and s.get('timer') is None
    s.set('user_name', 'Sam')
    s.set('timer', TimerState.start('p1', now=T0).to_dict())
    again = Settings(tmp_path / 'deep' / 'settings.json')
    again.load()
    assert again.get('user_name') == 'Sam' and again.get('timer')['project_id'] == 'p1'


def test_settings_corrupt_file(tmp_path):
    path = tmp_path / 'settings.json'
    path.write_text('{nope')
    s = Settings(path)
    s.load()
    assert s.get('theme') == 'dark'


def test_passcode():
    stored = hash_passcode('2468')
    assert check_passcode('2468', stored)
    assert not check_passcode('2469', stored)
    assert not check_passcode('2468', '')
    assert hash_passcode('2468') != stored
