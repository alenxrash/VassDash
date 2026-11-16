"""Zero-setup data location. No Qt imports.

The app finds the team's data folder by itself so nobody has to browse for it:

1. A folder already in use (found earlier, or chosen by hand in Settings) is kept.
2. Otherwise Dropbox's own info file says where Dropbox lives on this PC, and that Dropbox is
   searched a few levels deep for a folder named "Discounted Engineering Data".
3. If there is none, work is kept on this PC. Nothing is ever created inside Dropbox automatically:
   a private copy there would silently split the team's data. When the team folder does appear,
   what was saved on this PC is moved across.
"""
from __future__ import annotations

import getpass
import json
import os
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from .settings import APP_DIR
from .store import Store

DATA_FOLDER = 'Discounted Engineering Data'
MAX_DEPTH = 3            # the folder may sit up to this many levels below the Dropbox folder
MAX_FOLDERS = 6000       # stop looking after this many folders, so a huge Dropbox cannot stall start-up


@dataclass
class Location:
    path: Path
    shared: bool         # True: the team folder. False: this PC only.
    merged: int = 0      # records moved from this PC into the team folder on this start


def dropbox_roots(env=None) -> list[Path]:
    """Dropbox folders on this PC, business account first, read from Dropbox's info.json."""
    env = os.environ if env is None else env
    found: dict[str, list[Path]] = {'business': [], 'personal': []}
    for base in (env.get('APPDATA'), env.get('LOCALAPPDATA')):
        if not base:
            continue
        try:
            data = json.loads((Path(base) / 'Dropbox' / 'info.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        for kind in found:
            account = data.get(kind)
            path = account.get('path') if isinstance(account, dict) else None
            if isinstance(path, str) and path and Path(path).is_dir() and Path(path) not in found[kind]:
                found[kind].append(Path(path))
    return found['business'] + found['personal']


def find_shared(roots, name: str = DATA_FOLDER, max_depth: int = MAX_DEPTH) -> Path | None:
    """Shallowest folder called `name` (any letter case) under the given roots."""
    wanted = name.casefold()
    queue = deque((Path(root), 0) for root in roots)
    seen = 0
    while queue and seen < MAX_FOLDERS:
        folder, depth = queue.popleft()
        try:
            with os.scandir(folder) as scan:
                children = sorted((item for item in scan if item.is_dir(follow_symlinks=False)), key=lambda i: i.name)
        except OSError:
            continue
        for child in children:
            seen += 1
            if child.name.startswith(('.', '$')):
                continue
            if child.name.casefold() == wanted:
                return Path(child.path)
            if depth + 1 < max_depth:
                queue.append((Path(child.path), depth + 1))
    return None


RECORD_FOLDERS = ('projects', 'entries')


def data_root(path) -> Path:
    """The data folder for a picked or saved path.

    Picking the "Projects" or "Entries" folder inside a data folder is an easy slip; it used to start a new,
    empty data set inside that subfolder. When the parent holds both record folders, the parent is meant.
    """
    path = Path(path)
    parent = path.parent
    if (path.name.casefold() in RECORD_FOLDERS and parent != path
            and (parent / 'Projects').is_dir() and (parent / 'Entries').is_dir()):
        return parent
    return path


def local_dir(env=None) -> Path:
    env = os.environ if env is None else env
    base = env.get('LOCALAPPDATA')
    return (Path(base) if base else Path.home() / '.local' / 'share') / APP_DIR / 'Local data'


def merge(local, shared) -> int:
    """Move what was saved on this PC into the team folder. Safe to run again: nothing is copied twice.

    A local project with the same name as a team project is not duplicated; its time joins the team's project.
    """
    source, target = Store(local), Store(shared)
    try:
        source.load()
        target.load()
    except OSError:
        return 0
    by_name = {p.name.strip().casefold(): p.id for p in target.live_projects()}
    remap, moved = {}, 0
    for project in source.projects.values():
        if project.id in target.projects:
            continue
        twin = by_name.get(project.name.strip().casefold())
        if twin and not project.deleted:
            remap[project.id] = twin
            continue
        try:
            target.save_project(project, new=True)
            moved += 1
        except (OSError, ValueError):
            continue
    for entry in source.entries.values():
        if entry.id in target.entries:
            continue
        entry.project_id = remap.get(entry.project_id, entry.project_id)
        try:
            target.save_entry(entry, new=True)
            moved += 1
        except (OSError, ValueError):
            continue
    return moved


def resolve(settings, env=None) -> Location:
    """Decide where data lives, with no questions asked, and remember it."""
    saved, mode = settings.get('shared_dir'), settings.get('data_mode')
    if saved and mode != 'local' and Path(saved).is_dir():
        root = data_root(saved)
        if root != Path(saved):
            settings.data.update(shared_dir=str(root))
            settings.save()
        return Location(root, True)
    local = local_dir(env)
    found = find_shared(dropbox_roots(env))
    if found:
        merged = merge(local, found) if local.is_dir() else 0
        settings.data.update(shared_dir=str(found), data_mode='shared')
        settings.save()
        return Location(found, True, merged)
    local.mkdir(parents=True, exist_ok=True)
    settings.data.update(shared_dir=str(local), data_mode='local')
    settings.save()
    return Location(local, False)


def default_user_name() -> str:
    """The person's Windows display name ("Sam Taylor"), else their login name. Never blank."""
    if sys.platform == 'win32':
        try:
            import ctypes
            size = ctypes.c_ulong(0)
            ctypes.windll.secur32.GetUserNameExW(3, None, ctypes.byref(size))       # 3 = NameDisplay
            if size.value:
                buffer = ctypes.create_unicode_buffer(size.value)
                if ctypes.windll.secur32.GetUserNameExW(3, buffer, ctypes.byref(size)) and buffer.value.strip():
                    return buffer.value.strip()
        except Exception:
            pass
    try:
        return getpass.getuser().strip() or 'Unknown'
    except Exception:
        return 'Unknown'
