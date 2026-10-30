"""Desktop control: windows, typing and keyboard shortcuts.

Works on Windows, macOS (needs the Accessibility permission) and Linux on X11.
Wayland sessions block synthetic input and window control by design.
"""

from __future__ import annotations

import re
import time

from kai.tools.apps import match_app

FOCUS_DELAY = 0.4  # seconds for the OS to finish switching windows

_TERMINAL = re.compile(
    r"terminal|powershell|cmd\.exe|command prompt|s[ií]mbolo del sistema|bash|zsh|konsole|iterm",
    re.IGNORECASE,
)

# Spoken/common key names -> pynput Key attribute names.
_KEY_ALIASES = {
    "control": "ctrl", "ctl": "ctrl", "option": "alt", "opt": "alt", "win": "cmd",
    "windows": "cmd", "super": "cmd", "meta": "cmd", "command": "cmd", "escape": "esc",
    "return": "enter", "del": "delete", "pgup": "page_up", "pageup": "page_up",
    "pgdn": "page_down", "pagedown": "page_down", "spacebar": "space", "ins": "insert",
}


def _windows():
    import pywinctl

    own = {"kai", "kai needs your permission", "Send diagnostics", "Settings"}
    return [w for w in pywinctl.getAllWindows()
            if w.title.strip() and w.title not in own and w.isVisible]


def list_windows() -> list[str]:
    return [w.title for w in _windows()][:40]


def _find_window(title: str):
    windows = {w.title: w for w in _windows()}
    match = match_app(title, {t: t for t in windows})
    if match is None:
        raise LookupError(f"No open window matches '{title}'. Open windows: "
                          + "; ".join(list(windows)[:15]))
    return windows[match]


def focus_window(title: str) -> str:
    win = _find_window(title)
    if win.isMinimized:
        win.restore()
    win.activate(wait=True)
    time.sleep(FOCUS_DELAY)
    return f"Focused '{win.title}'"


def _ensure_target(window: str | None) -> str:
    """Focus the requested window, or check the active one isn't kai itself."""
    if window:
        return focus_window(window).removeprefix("Focused ")
    import pywinctl

    active = pywinctl.getActiveWindow()
    if active is None or active.title in ("kai", "kai needs your permission"):
        raise RuntimeError("kai's own window is focused. Pass the target window's title.")
    return f"'{active.title}'"


def is_terminal(window: str | None) -> bool:
    return bool(window and _TERMINAL.search(window))


def type_text(text: str, window: str | None = None) -> str:
    from pynput.keyboard import Controller

    target = _ensure_target(window)
    Controller().type(text)
    return f"Typed {len(text)} characters into {target}"


def _parse_keys(keys: str):
    from pynput.keyboard import Key, KeyCode

    parsed = []
    for raw in re.split(r"\s*\+\s*", keys.strip().lower()):
        name = _KEY_ALIASES.get(raw, raw)
        if hasattr(Key, name):
            parsed.append(getattr(Key, name))
        elif len(name) == 1:
            parsed.append(KeyCode.from_char(name))
        else:
            raise ValueError(f"Unknown key '{raw}'")
    return parsed


def press_keys(keys: str, window: str | None = None) -> str:
    """Press a shortcut like 'ctrl+t', 'alt+f4' or 'enter'."""
    from pynput.keyboard import Controller

    combo = _parse_keys(keys)
    target = _ensure_target(window)
    kb = Controller()
    for k in combo:
        kb.press(k)
    for k in reversed(combo):
        kb.release(k)
    return f"Pressed {keys} in {target}"
