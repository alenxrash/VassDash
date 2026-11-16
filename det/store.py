"""Shared team folder: one JSON file per project and per time entry. No Qt imports.

One file per record means two people adding entries never write the same file, which is what
keeps a Dropbox-synced folder safe without a server.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from datetime import date
from pathlib import Path

from .models import Config, Entry, Project, merge_names, now_iso

MAX_MINUTES = 24 * 60


def natural_key(text: str):
    """Sort 'Project 2' before 'Project 10'."""
    return [(0, int(part), '') if part.isdigit() else (1, 0, part) for part in re.split(r'(\d+)', text.casefold())]


def validate_entry(entry: Entry) -> None:
    if not entry.project_id:
        raise ValueError('Choose a project.')
    # An opening balance is a carried-over running total, so it is not limited to one day.
    limit = MAX_MINUTES * 365 if entry.source == 'opening' else MAX_MINUTES
    if not isinstance(entry.minutes, int) or isinstance(entry.minutes, bool) or not 1 <= entry.minutes <= limit:
        raise ValueError('Hours must be more than 0 and no more than 24.')
    if entry.date:
        try:
            date.fromisoformat(entry.date)
        except (TypeError, ValueError):
            raise ValueError('Date is not valid.') from None


def _write_atomic(path: Path, payload: dict) -> None:
    """Write beside the target, then rename, so a half-written file is never synced."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix='.' + path.stem, suffix='.tmp')
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False)
        os.replace(temp, path)
    except BaseException:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise


def _write_new(path: Path, payload: dict) -> None:
    """Exclusive creation: two PCs can never claim the same id."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'x', encoding='utf-8') as stream:
        json.dump(payload, stream, indent=2, ensure_ascii=False)


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.projects: dict[str, Project] = {}
        self.entries: dict[str, Entry] = {}
        self.config = Config()
        self.warnings: list[str] = []

    @property
    def projects_dir(self) -> Path:
        return self.directory / 'Projects'

    @property
    def entries_dir(self) -> Path:
        return self.directory / 'Entries'

    @property
    def config_path(self) -> Path:
        return self.directory / 'config.json'

    def _path(self, folder: Path, identifier: str) -> Path:
        try:
            identifier = str(uuid.UUID(identifier))
        except (ValueError, TypeError, AttributeError):
            raise ValueError('Invalid record ID.') from None
        return folder / f'{identifier}.json'

    # ---- reading -------------------------------------------------------------------------
    def load(self) -> None:
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.entries_dir.mkdir(parents=True, exist_ok=True)
        warnings: list[str] = []
        self.projects = self._read_folder(self.projects_dir, Project, warnings)
        self.entries = self._read_folder(self.entries_dir, Entry, warnings)
        config = Config()
        if self.config_path.exists():
            try:
                config = Config.from_dict(json.loads(self.config_path.read_text(encoding='utf-8')))
                config.rate = float(config.rate)
                config.fy_start_month = int(config.fy_start_month)
            except (OSError, ValueError, TypeError):
                config = Config()
                warnings.append('config.json could not be read; default settings are in use.')
        self.config = config
        self.warnings = warnings

    @staticmethod
    def _read_folder(folder: Path, kind, warnings: list[str]) -> dict:
        records = {}
        for path in sorted(folder.glob('*.json')):
            if 'conflicted copy' in path.name.lower():
                warnings.append(f'Sync conflict: {folder.name}/{path.name}')
                continue
            try:
                record = kind.from_dict(json.loads(path.read_text(encoding='utf-8')))
                if str(uuid.UUID(record.id)) != path.stem:
                    raise ValueError('ID does not match file name.')
                if kind is Entry:
                    record.minutes = int(record.minutes)
                    if record.date:
                        date.fromisoformat(record.date)
                records[record.id] = record
            except (OSError, ValueError, TypeError):
                warnings.append(f'Unreadable file: {folder.name}/{path.name}')
        return records

    def signature(self) -> tuple:
        """Cheap fingerprint of the folder; differs whenever anything in it changed."""
        parts = []
        for folder in (self.projects_dir, self.entries_dir):
            count = newest = size = 0
            try:
                with os.scandir(folder) as scan:
                    for item in scan:
                        if item.name.endswith('.json'):
                            stat = item.stat()
                            count += 1
                            size += stat.st_size
                            newest = max(newest, stat.st_mtime_ns)
            except OSError:
                pass
            parts.append((count, newest, size))
        try:
            stat = self.config_path.stat()
            parts.append((stat.st_mtime_ns, stat.st_size))
        except OSError:
            parts.append(None)
        return tuple(parts)

    def live_projects(self) -> list[Project]:
        return sorted((p for p in self.projects.values() if not p.deleted), key=lambda p: natural_key(p.name))

    def live_entries(self) -> list[Entry]:
        return [e for e in self.entries.values() if not e.deleted]

    def engineers(self) -> list[str]:
        return sorted(merge_names({e.engineer: 0 for e in self.live_entries() if e.engineer}), key=str.casefold)

    # ---- writing -------------------------------------------------------------------------
    def _save(self, folder: Path, record, new: bool) -> None:
        path = self._path(folder, record.id)
        record.updated_at = now_iso()
        if new:
            _write_new(path, record.to_dict())
        else:
            _write_atomic(path, record.to_dict())

    def save_project(self, project: Project, new: bool = False) -> None:
        if not project.name.strip():
            raise ValueError('Project name is required.')
        if project.quoted_hours is not None and project.quoted_hours < 0:
            raise ValueError('Quoted hours cannot be negative.')
        if project.opening_amount is not None and project.opening_amount < 0:
            raise ValueError('Imported amount cannot be negative.')
        self._save(self.projects_dir, project, new)
        self.projects[project.id] = project

    def save_entry(self, entry: Entry, new: bool = False) -> None:
        validate_entry(entry)
        self._save(self.entries_dir, entry, new)
        self.entries[entry.id] = entry

    def delete_project(self, identifier: str) -> None:
        project = self.projects[identifier]
        project.deleted = True
        self._save(self.projects_dir, project, False)

    def delete_entry(self, identifier: str) -> None:
        entry = self.entries[identifier]
        entry.deleted = True
        self._save(self.entries_dir, entry, False)

    def save_config(self) -> None:
        _write_atomic(self.config_path, self.config.to_dict())
