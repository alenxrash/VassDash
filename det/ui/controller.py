"""The one running timer, shared by the desktop widget and the main window.

It belongs to neither window, so the timer keeps running when the main window is closed.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal

from ..models import Entry
from ..timer import TimerState


def clock_text(seconds: float) -> str:
    seconds = int(seconds)
    return f'{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}'


class TimerController(QObject):
    changed = Signal()            # state changed, or one second passed while a timer exists
    saved = Signal(object)        # an Entry was written

    def __init__(self, context):
        """`context` supplies .store, .settings and .user (the main window)."""
        super().__init__(context)
        self.context = context
        self.now = datetime.now
        self.message = ''
        saved = context.settings.get('timer')
        self.timer: TimerState | None = TimerState.from_dict(saved) if saved else None
        self.ticker = QTimer(self)
        self.ticker.setInterval(1000)
        self.ticker.timeout.connect(self._tick)
        self.ticker.start()

    # ---- state ------------------------------------------------------------------------------
    @property
    def active(self) -> bool:
        return self.timer is not None

    @property
    def running(self) -> bool:
        return bool(self.timer and self.timer.running)

    @property
    def project_name(self) -> str:
        if not self.timer:
            return ''
        project = self.context.store.projects.get(self.timer.project_id)
        return project.name if project else 'Unknown project'

    def elapsed_text(self) -> str:
        return clock_text(self.timer.elapsed_s(self.now())) if self.timer else '0:00:00'

    def is_long(self) -> bool:
        return bool(self.timer and self.timer.is_long(self.now()))

    def hours(self) -> float:
        return self.timer.elapsed_s(self.now()) / 3600 if self.timer else 0.0

    def _tick(self) -> None:
        if self.timer:
            self.changed.emit()

    def _persist(self) -> None:
        self.context.settings.set('timer', self.timer.to_dict() if self.timer else None)
        self.changed.emit()

    # ---- actions ----------------------------------------------------------------------------
    def start(self, project_id) -> bool:
        if self.timer:
            return False
        if not project_id or project_id not in self.context.store.projects:
            self.message = 'Choose a project first'
            self.changed.emit()
            return False
        self.message = ''
        self.timer = TimerState.start(project_id, now=self.now())
        self._persist()
        return True

    def toggle_pause(self) -> None:
        if not self.timer:
            return
        if self.timer.running:
            self.timer.pause(self.now())
        else:
            self.timer.resume(self.now())
        self._persist()

    def stop(self, hours: float | None = None, note: str = '') -> Entry | None:
        """Save the timer as an entry. `hours` overrides the measured time (used after a very long run)."""
        if not self.timer:
            return None
        minutes, started, ended, day = self.timer.finish(self.now())
        if hours is not None:
            minutes = max(1, round(hours * 60))
        entry = Entry(project_id=self.timer.project_id, engineer=self.context.user, date=day,
                      minutes=min(minutes, 1440), note=note or self.timer.note, revision=self.timer.revision,
                      source='timer', started_at=started, ended_at=ended)
        try:
            if entry.project_id not in self.context.store.projects:
                raise ValueError('The project for this timer no longer exists. Discard the timer.')
            self.context.store.save_entry(entry, new=True)
        except (ValueError, OSError) as problem:
            self.message = str(problem)
            self.changed.emit()
            return None
        self.message = ''
        self.timer = None
        self._persist()
        self.saved.emit(entry)
        return entry

    def discard(self) -> None:
        if self.timer:
            self.timer = None
            self.message = ''
            self._persist()
