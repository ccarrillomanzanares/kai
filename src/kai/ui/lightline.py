"""The light line: a thin line of light that shows what kai is doing.

- listening: a soft glow glides back and forth and swells with your voice
- thinking:  two glows cross each other, faster
- speaking:  the line becomes a live waveform following kai's voice
- connecting: the whole line breathes; offline: a dim still line
"""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from kai.ui.theme import LINE_COLORS

FRAME_MS = 16
WAVE_POINTS = 90
# (stroke width, alpha) passes, widest first: a cheap glow without blur filters
GLOW = [(12.0, 0.10), (7.0, 0.22), (3.5, 0.55), (1.8, 1.0)]


def _color(hex_color: str, alpha: float) -> QColor:
    c = QColor(hex_color)
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


class LightLine(QWidget):
    """Mouse events fall through to the window, which handles clicks and dragging."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(160, 24)
        self.setCursor(Qt.PointingHandCursor)
        self._state = "offline"
        self._target = 0.0  # latest voice level
        self._level = 0.0  # smoothed voice level
        self._energy = 0.0  # smoothed 0..1 "how much is happening", for transitions
        self._t0 = time.monotonic()
        self._timer = QTimer(self, interval=FRAME_MS, timeout=self._tick)
        self._timer.start()

    def set_state(self, state: str) -> None:
        self._state = state if state in LINE_COLORS else "offline"

    def set_level(self, level: float) -> None:
        self._target = max(self._target, max(0.0, min(1.0, level)))

    def _tick(self) -> None:
        self._level += (self._target - self._level) * 0.3
        self._target *= 0.82
        active = self._state not in ("offline", "muted")
        self._energy += ((1.0 if active else 0.35) - self._energy) * 0.08
        self.update()

    # ---- painting ----

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = time.monotonic() - self._t0
        colors = LINE_COLORS[self._state]
        x0, x1 = 6.0, self.width() - 6.0
        y = self.height() / 2

        # The resting line, faint, fading out at both ends.
        rest = QLinearGradient(x0, 0, x1, 0)
        rest.setColorAt(0.0, _color(colors[0], 0.0))
        rest.setColorAt(0.5, _color(colors[0], 0.22 * self._energy))
        rest.setColorAt(1.0, _color(colors[0], 0.0))
        p.setPen(QPen(rest, 1.2))
        p.drawLine(QPointF(x0, y), QPointF(x1, y))

        if self._state == "speaking":
            self._paint_wave(p, t, x0, x1, y, colors)
        elif self._state == "thinking":
            for phase in (0.0, 0.5):
                pos = (1 - math.cos((t * 0.9 + phase) * 2 * math.pi)) / 2
                self._paint_glow(p, x0, x1, y, pos, 0.16, colors, 0.9)
        elif self._state == "connecting":
            breathe = 0.35 + 0.35 * (1 + math.sin(t * 2.4)) / 2
            self._paint_glow(p, x0, x1, y, 0.5, 0.45, colors, breathe)
        elif self._state in ("listening", "muted"):
            speed = 0.28 if self._state == "listening" else 0.15
            pos = (1 - math.cos(t * speed * 2 * math.pi)) / 2
            width = 0.22 + 0.2 * self._level
            strength = (0.95 + 0.4 * self._level) if self._state == "listening" else 0.5
            self._paint_glow(p, x0, x1, y, pos, width, colors, strength,
                             thickness=1.0 + 1.6 * self._level)

    def _paint_glow(self, p: QPainter, x0: float, x1: float, y: float, pos: float,
                    width: float, colors: tuple[str, str], strength: float,
                    thickness: float = 1.0) -> None:
        """A bright spot on the line at `pos` (0..1), `width` as a fraction of the line."""
        span = x1 - x0
        center = x0 + pos * span
        half = width * span / 2
        grad = QLinearGradient(center - half, 0, center + half, 0)
        for stroke, alpha in GLOW:
            a = alpha * strength
            grad.setColorAt(0.0, _color(colors[0], 0.0))
            grad.setColorAt(0.35, _color(colors[0], a * 0.6))
            grad.setColorAt(0.5, _color(colors[1], a))
            grad.setColorAt(0.65, _color(colors[0], a * 0.6))
            grad.setColorAt(1.0, _color(colors[0], 0.0))
            pen = QPen(grad, stroke * thickness)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(max(x0, center - half), y), QPointF(min(x1, center + half), y))

    def _paint_wave(self, p: QPainter, t: float, x0: float, x1: float, y: float,
                    colors: tuple[str, str]) -> None:
        amp = (self.height() / 2 - 3) * (0.12 + 0.88 * self._level)
        path = QPainterPath()
        for i in range(WAVE_POINTS + 1):
            u = i / WAVE_POINTS
            envelope = math.sin(math.pi * u) ** 2  # pinned at both ends
            v = (math.sin(u * 11 + t * 7.0) * 0.55
                 + math.sin(u * 23 - t * 9.5) * 0.30
                 + math.sin(u * 5 + t * 3.1) * 0.25)
            point = QPointF(x0 + u * (x1 - x0), y + v * amp * envelope)
            if i:
                path.lineTo(point)
            else:
                path.moveTo(point)
        grad = QLinearGradient(x0, 0, x1, 0)
        for stroke, alpha in GLOW[1:]:
            grad.setColorAt(0.0, _color(colors[0], 0.0))
            grad.setColorAt(0.3, _color(colors[0], alpha))
            grad.setColorAt(0.7, _color(colors[1], alpha))
            grad.setColorAt(1.0, _color(colors[1], 0.0))
            pen = QPen(grad, stroke * 0.8)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            p.drawPath(path)
