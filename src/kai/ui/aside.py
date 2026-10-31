"""Moves kai's window out of the way while kai works in other apps.

While kai looks at the screen or clicks, its conversation panel folds so it
doesn't cover the app, and screenshots leave kai's window out (on Windows the
system does it; elsewhere the window turns transparent for the capture). If a
click falls on kai's bar, the bar moves to the other end of the screen. The
panel comes back when kai talks.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import time

from PySide6.QtCore import QObject, QPoint, Qt, QThread, Signal
from PySide6.QtGui import QGuiApplication

from kai.tools import overlay

log = logging.getLogger(__name__)

WDA_EXCLUDEFROMCAPTURE = 0x11  # Windows 10 2004 and later


class Aside(QObject):
    _step = Signal(object)
    _hide = Signal(bool)

    def __init__(self, window) -> None:
        super().__init__()
        self.window = window
        self._folded = False  # the panel was open and kai folded it
        self._moved_from: QPoint | None = None
        self._excluded = False  # Windows leaves the window out of captures
        self._step.connect(self._do_step, Qt.BlockingQueuedConnection)
        self._hide.connect(self._do_hide, Qt.BlockingQueuedConnection)
        overlay.register(self.step_aside, self.set_hidden)

    def exclude_from_capture(self) -> None:
        """Call once the window exists."""
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.window.winId())
            self._excluded = bool(ctypes.windll.user32.SetWindowDisplayAffinity(
                hwnd, WDA_EXCLUDEFROMCAPTURE))
        except Exception as e:
            log.debug("Can't exclude the window from captures: %s", e)
        log.info("Window left out of screenshots: %s", self._excluded)

    # ---- called from tool threads ----

    def _on_ui_thread(self) -> bool:
        return QThread.currentThread() is self.thread()

    def step_aside(self, point: tuple[int, int] | None) -> None:
        if self._on_ui_thread():
            self._do_step(point)
        else:
            self._step.emit(point)
            if point is not None:
                time.sleep(0.1)  # let the window manager finish a move before the click

    def set_hidden(self, hidden: bool) -> None:
        if self._excluded or not self.window.isVisible():
            return
        if self._on_ui_thread():
            self._do_hide(hidden)
        else:
            self._hide.emit(hidden)
            if hidden:
                time.sleep(0.15)  # let the compositor repaint without kai

    # ---- UI thread ----

    def _do_step(self, point) -> None:
        w = self.window
        if w.panel.isVisible():
            w.set_panel_visible(False)
            self._folded = True
        if point is not None and w.isVisible() and self._covers(point):
            area = (w.screen() or QGuiApplication.primaryScreen()).availableGeometry()
            if self._moved_from is None:
                self._moved_from = w.pos()
            to_top = w.geometry().center().y() > area.center().y()
            y = area.top() + 12 if to_top else area.bottom() - w.height() - 12
            w.move(w.x(), y)
            log.info("Moved out of the way of a click")

    def _covers(self, point: tuple[int, int]) -> bool:
        w = self.window
        ratio = (w.screen() or QGuiApplication.primaryScreen()).devicePixelRatio()
        g = w.frameGeometry().adjusted(-8, -8, 8, 8)
        return g.contains(round(point[0] / ratio), round(point[1] / ratio))

    def _do_hide(self, hidden: bool) -> None:
        self.window.setWindowOpacity(0.0 if hidden else 1.0)

    def on_state(self, state: str) -> None:
        if state == "speaking":
            self.restore()

    def restore(self) -> None:
        """kai is talking to the user again: put things back."""
        w = self.window
        if self._moved_from is not None:
            w.move(self._moved_from)
            self._moved_from = None
        if self._folded:
            self._folded = False
            w.set_panel_visible(True, focus=False)
