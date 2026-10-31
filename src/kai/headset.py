"""The headset button (play/pause media key) mutes and unmutes the microphone.

Bluetooth headsets send their main button as a global play/pause key. kai
listens for it system-wide; music players still receive the key too. Presses
that kai itself sends (press_keys "play pause") are ignored.
"""

from __future__ import annotations

import logging
import time

from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)

DEBOUNCE_S = 0.6  # a double press or key repeat counts once
_ignore_until = 0.0


def ignore_own_press(seconds: float = 1.0) -> None:
    """Call before kai presses the media key itself."""
    global _ignore_until
    _ignore_until = time.monotonic() + seconds


class HeadsetButton(QObject):
    pressed = Signal()  # emitted from the listener thread; Qt queues it to the UI

    def __init__(self) -> None:
        super().__init__()
        self._listener = None
        self._last = 0.0

    def start(self) -> None:
        if self._listener is not None:
            return
        try:
            from pynput import keyboard
        except Exception as e:
            log.warning("Headset button unavailable: %s", e)
            return

        def on_press(key) -> None:
            if key != keyboard.Key.media_play_pause:
                return
            now = time.monotonic()
            if now < _ignore_until or now - self._last < DEBOUNCE_S:
                return
            self._last = now
            log.info("Headset button pressed")
            self.pressed.emit()

        try:
            self._listener = keyboard.Listener(on_press=on_press)
            self._listener.daemon = True
            self._listener.start()
            log.info("Listening for the headset button")
        except Exception as e:  # e.g. Wayland without X access
            self._listener = None
            log.warning("Headset button unavailable: %s", e)

    def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:  # it never got going (e.g. no X display)
                pass
            self._listener = None

    def set_enabled(self, on: bool) -> None:
        self.start() if on else self.stop()
