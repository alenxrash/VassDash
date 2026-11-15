"""Start/stop timer state. Pure logic so it can be saved, restored and tested. No Qt imports."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

LONG_RUN_S = 12 * 3600


@dataclass
class TimerState:
    project_id: str
    revision: str = ''
    note: str = ''
    started_at: str = ''
    accumulated_s: float = 0.0
    running_since: str | None = None

    @classmethod
    def start(cls, project_id: str, revision: str = '', note: str = '', now: datetime | None = None) -> 'TimerState':
        stamp = (now or datetime.now()).isoformat(timespec='seconds')
        return cls(project_id, revision, note, stamp, 0.0, stamp)

    @property
    def running(self) -> bool:
        return self.running_since is not None

    def elapsed_s(self, now: datetime | None = None) -> float:
        total = self.accumulated_s
        if self.running_since:
            total += max(0.0, ((now or datetime.now()) - datetime.fromisoformat(self.running_since)).total_seconds())
        return total

    def pause(self, now: datetime | None = None) -> None:
        if self.running_since:
            self.accumulated_s = self.elapsed_s(now)
            self.running_since = None

    def resume(self, now: datetime | None = None) -> None:
        if not self.running_since:
            self.running_since = (now or datetime.now()).isoformat(timespec='seconds')

    def is_long(self, now: datetime | None = None) -> bool:
        return self.elapsed_s(now) > LONG_RUN_S

    def finish(self, now: datetime | None = None) -> tuple[int, str, str, str]:
        """(minutes, started_at, ended_at, entry date). The entry is dated the day the timer started."""
        now = now or datetime.now()
        minutes = max(1, round(self.elapsed_s(now) / 60))
        return minutes, self.started_at, now.isoformat(timespec='seconds'), self.started_at[:10]

    def to_dict(self) -> dict:
        return dict(self.__dict__)

    @classmethod
    def from_dict(cls, data) -> 'TimerState | None':
        try:
            state = cls(str(data['project_id']), str(data.get('revision', '')), str(data.get('note', '')),
                        str(data['started_at']), float(data.get('accumulated_s', 0.0)), data.get('running_since'))
            datetime.fromisoformat(state.started_at)
            if state.running_since:
                datetime.fromisoformat(state.running_since)
            return state
        except (KeyError, TypeError, ValueError):
            return None
