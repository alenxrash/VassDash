"""Records kept in the shared folder. No Qt imports."""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def new_id() -> str:
    return str(uuid.uuid4())


class Record:
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        """Unknown keys are ignored so an older build can read a newer build's files."""
        if not isinstance(data, dict):
            raise ValueError('Record is not an object.')
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})


@dataclass
class Project(Record):
    id: str = field(default_factory=new_id)
    name: str = ''
    sf_id: str = ''
    region: str = ''
    approved_by: str = ''
    lead_engineer: str = ''
    quoted_hours: float | None = None
    reason_category: str = 'Other'
    reason_detail: str = ''
    remarks: str = ''
    status: str = 'open'
    created_by: str = ''
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    deleted: bool = False


@dataclass
class Entry(Record):
    id: str = field(default_factory=new_id)
    project_id: str = ''
    engineer: str = ''
    date: str | None = None          # ISO local date; None for an undated opening balance
    minutes: int = 0
    revision: str = ''
    note: str = ''
    source: str = 'batch'            # timer | batch | opening
    started_at: str = ''
    ended_at: str = ''
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    deleted: bool = False

    @property
    def hours(self) -> float:
        return self.minutes / 60


@dataclass
class Config(Record):
    rate: float = 220.0
    fy_start_month: int = 7
    regions: list = field(default_factory=lambda: ['QLD', 'NSW', 'VIC', 'NZ'])
    reason_categories: list = field(default_factory=lambda: [
        'Good client', 'Change of scope', 'Revised drawings', 'Project size', 'Other'])
    passcode_hash: str = ''
