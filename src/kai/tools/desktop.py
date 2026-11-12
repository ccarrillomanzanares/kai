"""Desktop control: windows, typing and keyboard shortcuts.

Works on Windows and Linux on X11.
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


# Invisible helper windows Windows reports as top-level windows.
_NOISE = {"CoreInput", "DesktopWindowXamlSource", "Chrome Legacy Window",
          "Default IME", "MSCTFIME UI", "Program Manager"}


def _is_real(w) -> bool:
    title = w.title.strip()
    if not title or title in _NOISE or title.startswith("&"):  # "&Save" = a control
        return False
    try:
        # A minimized window has no size of its own (Windows reports 160x28).
        return w.isVisible and (w.isMinimized or (w.width >= 80 and w.height >= 40))
    except Exception:
        return False


def _pywinctl():
    try:
        import pywinctl
    except SystemExit:
        # pymonctl exits the whole program when it cannot run xrandr (Linux).
        raise RuntimeError("Managing windows needs the xrandr command and an X11 "
                           "session. Install it (x11-xserver-utils on Debian and "
                           "Ubuntu) and restart kai.") from None
    return pywinctl


def _windows():
    pywinctl = _pywinctl()

    own = {"kai", "kai needs your permission", "Send diagnostics", "Settings"}
    return [w for w in pywinctl.getAllWindows() if w.title not in own and _is_real(w)]


MINIMIZED = " (minimized)"
_last_used: tuple[object, str] | None = None  # (handle, title) of the last window acted on


def _minimized(w) -> bool:
    try:
        return bool(w.isMinimized)
    except Exception:
        return False


def list_windows() -> list[str]:
    return [w.title + (MINIMIZED if _minimized(w) else "") for w in _windows()][:40]


def _handle(w):
    try:
        return w.getHandle()
    except Exception:
        return None


def _find_window(title: str):
    global _last_used
    title = title.removesuffix(MINIMIZED)
    found = _windows()
    windows = {}
    for w in found:
        windows.setdefault(w.title, w)  # same title twice: the one in front
    # Exactly as written first: "claude" (a terminal) and "Claude" (an app) can both be open.
    match = title if title in windows else match_app(title, {t: t for t in windows})
    if match is None:
        hint = ""
        if _last_used and _last_used[0] is not None:
            renamed = [w for w in found if _handle(w) == _last_used[0]]
            if renamed and renamed[0].title != _last_used[1]:
                hint = (f" The window you last used, '{_last_used[1]}', is still open and is "
                        f"now titled '{renamed[0].title}': windows rename themselves (a "
                        "terminal takes the name of the program it runs).")
        raise LookupError(f"No open window matches '{title}'.{hint} Open windows: "
                          + "; ".join(list(windows)[:15]))
    _last_used = (_handle(windows[match]), windows[match].title)
    return windows[match]


def focus_window(title: str) -> str:
    win = _find_window(title)
    if win.isMinimized:
        win.restore()
    try:
        active = win.isActive
    except Exception:
        active = False
    if not active:  # re-activating can move the keyboard focus out of the field in use
        win.activate(wait=True)
        time.sleep(FOCUS_DELAY)
    return f"Focused '{win.title}'"


def close_window(title: str) -> str:
    """Ask a window to close, like clicking its X: the app may ask to save first."""
    win = _find_window(title)
    name = win.title
    win.close()
    time.sleep(1.0)
    still_open = any(w.title == name for w in _windows())
    return (f"Asked '{name}' to close, but it is still open: it may be asking to save. "
            "Look at it." if still_open else f"Closed '{name}'")


def _ensure_target(window: str | None) -> str:
    """Focus the requested window, or check the active one isn't kai itself."""
    if window:
        return focus_window(window).removeprefix("Focused ")
    active = _pywinctl().getActiveWindow()
    if active is None or active.title in ("kai", "kai needs your permission"):
        raise RuntimeError("kai's own window is focused. Pass the target window's title.")
    return f"'{active.title}'"


def is_terminal(window: str | None) -> bool:
    return bool(window and _TERMINAL.search(window))


def type_text(text: str, window: str | None = None) -> str:
    from pynput.keyboard import Controller

    target = _ensure_target(window)
    Controller().type(text)
    return (f"Typed {len(text)} characters into {target}. Check it arrived where you meant "
            "before telling the user.")


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
    from kai import headset
    headset.ignore_own_press()  # don't let kai's own media keys toggle the microphone
    kb = Controller()
    for k in combo:
        kb.press(k)
    for k in reversed(combo):
        kb.release(k)
    return f"Pressed {keys} in {target}. Check the result before telling the user it worked."
