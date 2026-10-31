"""Read an app's window through the system accessibility tree, and click its parts.

Screen readers use the same information: every button, field, menu, link and
label with its name and position. That lets kai find "the Save button"
exactly, without a screenshot.

- Windows: UI Automation (the `uiautomation` package).
- Linux: AT-SPI, through PyGObject (`gi`). Needs the system packages
  python3-gi and gir1.2-atspi-2.0, visible to kai's Python.

Some apps (games, custom-drawn UIs) expose little or nothing; then the model
falls back to look_at_screen.
"""

from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from kai.tools import desktop
from kai.tools.apps import match_app

MAX_ELEMENTS = 150
MAX_DEPTH = 30
TIME_BUDGET = 4.0  # seconds; huge apps are cut short rather than hanging
NAME_CHARS = 80


@dataclass
class Element:
    role: str
    name: str
    rect: tuple[int, int, int, int]  # left, top, width, height in screen pixels
    value: str = ""
    enabled: bool = True

    def describe(self) -> str:
        text = self.role + (f' "{self.name}"' if self.name else "")
        if self.value and self.value != self.name:
            text += f" = {self.value!r}"
        return text + ("" if self.enabled else " [disabled]")


_last: dict[int, Element] = {}
_last_window = ""


def _clip(text: str | None) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= NAME_CHARS else text[:NAME_CHARS] + "…"


# ---- Windows: UI Automation ----

_WIN_ROLES = {
    "ButtonControl": "button", "SplitButtonControl": "button", "EditControl": "field",
    "HyperlinkControl": "link", "MenuItemControl": "menu item", "TabItemControl": "tab",
    "ListItemControl": "list item", "CheckBoxControl": "checkbox",
    "RadioButtonControl": "radio", "ComboBoxControl": "dropdown", "TreeItemControl": "tree item",
    "DataItemControl": "row", "TextControl": "text", "DocumentControl": "document",
    "MenuBarControl": None, "ToolBarControl": None,
}

_uia_executor: ThreadPoolExecutor | None = None


def _uia_init() -> None:
    import uiautomation as auto

    # COM must be initialized in this thread and stay so; keep the initializer alive.
    globals()["_uia_initializer"] = auto.UIAutomationInitializerInThread()


def _windows_elements(win) -> list[Element]:
    import uiautomation as auto

    root = auto.ControlFromHandle(win.getHandle())
    if root is None:
        raise LookupError(f"Can't read the window '{win.title}'.")
    found, started = [], time.monotonic()
    for ctrl, _depth in auto.WalkControl(root, includeTop=False, maxDepth=MAX_DEPTH):
        if len(found) >= MAX_ELEMENTS or time.monotonic() - started > TIME_BUDGET:
            break
        role = _WIN_ROLES.get(ctrl.ControlTypeName)
        if role is None:
            continue
        try:
            if ctrl.IsOffscreen:
                continue
            r = ctrl.BoundingRectangle
            if r.width() < 2 or r.height() < 2:
                continue
            name = _clip(ctrl.Name)
            value = ""
            if role in ("field", "dropdown", "document"):
                try:
                    value = _clip(ctrl.GetValuePattern().Value)
                except Exception:
                    pass
            if role in ("text", "document") and not (name or value):
                continue
            found.append(Element(role, name, (r.left, r.top, r.width(), r.height()), value,
                                 bool(ctrl.IsEnabled)))
        except Exception:  # elements can vanish while we walk
            continue
    return found


# ---- Linux: AT-SPI ----

_ATSPI_ROLES = {
    "push button": "button", "button": "button", "toggle button": "button", "text": "field", "entry": "field",
    "password text": "password field", "link": "link", "menu item": "menu item",
    "menu": "menu", "page tab": "tab", "list item": "list item", "check box": "checkbox",
    "radio button": "radio", "combo box": "dropdown", "tree item": "tree item",
    "table cell": "cell", "label": "text", "heading": "heading", "paragraph": "text",
    "spin button": "number field", "slider": "slider", "check menu item": "menu item",
    "radio menu item": "menu item", "icon": "icon",
}


def _atspi():
    import gi

    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi

    return Atspi


def _atspi_window(title: str):
    Atspi = _atspi()
    desktop_ = Atspi.get_desktop(0)
    windows = {}
    for i in range(desktop_.get_child_count()):
        app = desktop_.get_child_at_index(i)
        if app is None:
            continue
        for j in range(app.get_child_count()):
            w = app.get_child_at_index(j)
            if w is not None and w.get_name():
                windows.setdefault(w.get_name(), w)
    match = match_app(title, {t: t for t in windows})
    if match is None:
        raise LookupError(f"No accessible window matches '{title}'. Accessible windows: "
                          + "; ".join(list(windows)[:15]))
    return windows[match]


def _linux_elements(title: str) -> tuple[str, list[Element]]:
    Atspi = _atspi()
    root = _atspi_window(title)
    found, started = [], time.monotonic()

    def walk(acc, depth: int) -> None:
        if (depth > MAX_DEPTH or len(found) >= MAX_ELEMENTS
                or time.monotonic() - started > TIME_BUDGET):
            return
        try:
            states = acc.get_state_set()
            if not states.contains(Atspi.StateType.SHOWING):
                return
            role = _ATSPI_ROLES.get(acc.get_role_name())
            if role:
                e = acc.get_extents(Atspi.CoordType.SCREEN)
                name = _clip(acc.get_name())
                value = ""
                if role.endswith("field"):
                    try:
                        count = Atspi.Text.get_character_count(acc)
                        value = _clip(Atspi.Text.get_text(acc, 0, min(count, 200)))
                    except Exception:
                        pass
                if e.width >= 2 and e.height >= 2 and (name or value or role != "text"):
                    found.append(Element(role, name, (e.x, e.y, e.width, e.height), value,
                                         states.contains(Atspi.StateType.SENSITIVE)))
            for i in range(acc.get_child_count()):
                child = acc.get_child_at_index(i)
                if child is not None:
                    walk(child, depth + 1)
        except Exception:  # elements can vanish while we walk
            return

    walk(root, 0)
    return root.get_name(), found


# ---- tools ----

def _collect(window: str) -> tuple[str, list[Element]]:
    if sys.platform == "win32":
        global _uia_executor
        win = desktop._find_window(window)
        if _uia_executor is None:
            _uia_executor = ThreadPoolExecutor(1, "kai-uia", initializer=_uia_init)
        return win.title, _uia_executor.submit(_windows_elements, win).result(timeout=30)
    if sys.platform.startswith("linux"):
        try:
            _atspi()
        except (ImportError, ValueError) as e:
            raise RuntimeError("Reading windows needs AT-SPI: install python3-gi and "
                               "gir1.2-atspi-2.0. Use look_at_screen meanwhile.") from e
        return _linux_elements(window)
    raise RuntimeError("Reading windows is supported on Windows and Linux. "
                       "Use look_at_screen instead.")


def read_window(window: str) -> str:
    global _last_window
    title, elements = _collect(window)
    _last.clear()
    _last.update(enumerate(elements, start=1))
    _last_window = title
    if not elements:
        return (f"'{title}' exposes no readable elements (some apps don't). "
                "Use look_at_screen and click instead.")
    lines = [f"{n} {e.describe()}" for n, e in _last.items()]
    more = " (list cut short: the window has more)" if len(elements) >= MAX_ELEMENTS else ""
    return f"Elements of '{title}'{more}; use their numbers with click_element:\n" + "\n".join(lines)


def describe(number: int) -> str:
    element = _last.get(int(number))
    return f"{element.describe()} in '{_last_window}'" if element else f"element {number}"


def click_element(number: int, double: bool = False, button: str = "left") -> str:
    from kai.tools import screen

    element = _last.get(int(number))
    if element is None:
        raise LookupError(f"No element {number}. Call read_window first.")
    try:
        desktop.focus_window(_last_window)
    except LookupError:
        pass  # not listed by the window manager; the element is visible, click anyway
    left, top, width, height = element.rect
    screen.click_point(left + width // 2, top + height // 2, button, double)
    return (f"Clicked {element.describe()} in '{_last_window}'. "
            "Read the window again to see the result; numbers may change.")
