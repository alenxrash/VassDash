"""Personal settings on this PC (not shared). No Qt imports."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

APP_DIR = 'DiscountedEngineeringTracker'
DEFAULTS = {'shared_dir': '', 'data_mode': '', 'user_name': '', 'theme': 'dark', 'timer': None, 'geometry': ''}


def default_path() -> Path:
    base = os.environ.get('LOCALAPPDATA')
    root = Path(base) if base else Path.home() / '.local' / 'share'
    return root / APP_DIR / 'settings.json'


class Settings:
    def __init__(self, path):
        self.path = Path(path)
        self.data = dict(DEFAULTS)

    def load(self) -> None:
        self.data = dict(DEFAULTS)
        try:
            stored = json.loads(self.path.read_text(encoding='utf-8'))
            if isinstance(stored, dict):
                self.data.update(stored)
        except (OSError, ValueError):
            pass

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value) -> None:
        self.data[key] = value
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temp = tempfile.mkstemp(dir=self.path.parent, suffix='.tmp')
        try:
            with os.fdopen(handle, 'w', encoding='utf-8') as stream:
                json.dump(self.data, stream, indent=2)
            os.replace(temp, self.path)
        except BaseException:
            try:
                os.unlink(temp)
            except OSError:
                pass
            raise
