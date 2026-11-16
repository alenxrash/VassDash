"""Start the timer widget when the person signs in to Windows. No Qt imports.

Uses the per-user Run key, so it needs no administrator rights. On other systems it does nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
VALUE = 'Budget Tracker'
LEGACY_VALUES = ('VassDash',)          # names used by earlier builds


def supported() -> bool:
    return sys.platform == 'win32'


def launch_command(executable: str | None = None, script: str | None = None, frozen: bool | None = None) -> str:
    """Command that opens only the widget. Built .exe: the exe itself. From source: python plus app.py."""
    executable = executable or sys.executable
    frozen = bool(getattr(sys, 'frozen', False)) if frozen is None else frozen
    if frozen:
        return f'"{executable}" --widget'
    script = script or str(Path(sys.argv[0]).resolve())
    return f'"{executable}" "{script}" --widget'


def is_enabled() -> bool:
    if not supported():
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            for name in (VALUE,) + LEGACY_VALUES:
                try:
                    winreg.QueryValueEx(key, name)
                    return True
                except OSError:
                    pass
        return False
    except OSError:
        return False


def set_enabled(on: bool) -> bool:
    """Returns True when the change was made."""
    if not supported():
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            for name in LEGACY_VALUES:
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass
            if on:
                winreg.SetValueEx(key, VALUE, 0, winreg.REG_SZ, launch_command())
            else:
                try:
                    winreg.DeleteValue(key, VALUE)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


def migrate_legacy() -> None:
    """An earlier build registered Start with Windows under an old name and exe path: re-point it here."""
    if not supported():
        return
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            found = False
            for name in LEGACY_VALUES:
                try:
                    winreg.QueryValueEx(key, name)
                    found = True
                except OSError:
                    pass
    except OSError:
        return
    if found:
        set_enabled(True)
