"""The scanner: a row of LEDs with a light sweeping back and forth, leaving a trail.

States change speed and color. While kai speaks, LEDs light up from the center
outwards following the voice level.
"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from kai.ui.theme import SCANNER_COLORS

LEDS = 15
FRAME_MS = 16

# state -> (sweeps per second, trail decay per frame, brightness)
MOTION = {
    "offline": (0.0, 0.90, 0.0),
    "connecting": (0.35, 0.91, 0.55),
    "listening": (0.55, 0.88, 1.0),
    "thinking": (1.4, 0.78, 1.0),
    "speaking": (0.0, 0.80, 1.0),
    "muted": (0.25, 0.9, 0.4),
}


class Scanner(QWidget):
    """Mouse events fall through to the window, which handles clicks and dragging."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 18)
        self.setCursor(Qt.PointingHandCursor)
        self._state = "offline"
        self._leds = [0.0] * LEDS
        self._level = 0.0
        self._phase = 0.0
        self._last = time.monotonic()
        self._timer = QTimer(self, interval=FRAME_MS, timeout=self._tick)
        self._timer.start()

    def set_state(self, state: str) -> None:
        self._state = state if state in MOTION else "offline"

    def set_level(self, level: float) -> None:
        self._level = max(self._level, max(0.0, min(1.0, level)))

    def _tick(self) -> None:
        now = time.monotonic()
        dt, self._last = now - self._last, now
        speed, decay, brightness = MOTION[self._state]
        self._leds = [v * decay for v in self._leds]

        if self._state == "speaking":
            # Voice meter: light LEDs symmetrically from the center.
            center = (LEDS - 1) / 2
            reach = self._level * (center + 1)
            for i in range(LEDS):
                d = abs(i - center)
                if d < reach:
                    self._leds[i] = max(self._leds[i], min(1.0, reach - d) * brightness)
            self._level *= 0.85
        elif speed:
            # Ping-pong sweep with an eased turn at each end.
            self._phase = (self._phase + dt * speed) % 1.0
            pos = (1 - math.cos(self._phase * 2 * math.pi)) / 2 * (LEDS - 1)
            i, frac = int(pos), pos - int(pos)
            self._leds[i] = max(self._leds[i], (1 - frac) * brightness)
            if i + 1 < LEDS:
                self._leds[i + 1] = max(self._leds[i + 1], frac * brightness)
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        on, off = SCANNER_COLORS.get(self._state, SCANNER_COLORS["offline"])
        on, off = QColor(on), QColor(off)

        gap = 3.0
        w = (self.width() - gap * (LEDS - 1)) / LEDS
        h = min(self.height(), 12.0)
        y = (self.height() - h) / 2
        for i, v in enumerate(self._leds):
            rect = QRectF(i * (w + gap), y, w, h)
            p.setBrush(off)
            p.drawRoundedRect(rect, 2, 2)
            if v > 0.02:
                glow = QColor(on)
                glow.setAlphaF(min(1.0, v) * 0.35)
                p.setBrush(glow)
                p.drawRoundedRect(rect.adjusted(-2, -3, 2, 3), 4, 4)
                led = QColor(on)
                led.setAlphaF(min(1.0, v))
                p.setBrush(led)
                p.drawRoundedRect(rect, 2, 2)
