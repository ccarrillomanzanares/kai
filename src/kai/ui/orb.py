"""The orb: a soft glowing circle that breathes and reacts to the voice level."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QWidget

from kai.ui.theme import STATE_COLORS


class Orb(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(180, 180)
        self._state = "offline"
        self._color = QColor(STATE_COLORS["offline"])
        self._target_level = 0.0
        self._level = 0.0
        self._t0 = time.monotonic()
        self._timer = QTimer(self, interval=16, timeout=self._tick)
        self._timer.start()

    def set_state(self, state: str) -> None:
        self._state = state
        self._color = QColor(STATE_COLORS.get(state, STATE_COLORS["offline"]))
        if state not in ("listening", "speaking"):
            self._target_level = 0.0

    def set_level(self, level: float) -> None:
        self._target_level = max(0.0, min(1.0, level))

    def _tick(self) -> None:
        # Ease toward the target so the orb never jitters.
        self._level += (self._target_level - self._level) * 0.25
        self._target_level *= 0.9
        self.update()

    def paintEvent(self, event) -> None:
        t = time.monotonic() - self._t0
        speed = 3.0 if self._state in ("thinking", "connecting") else 1.2
        breathe = 0.04 * math.sin(t * speed)
        scale = 0.55 + breathe + 0.3 * self._level

        side = min(self.width(), self.height())
        r = side / 2 * scale
        c = QPointF(self.width() / 2, self.height() / 2)

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)

        glow = QRadialGradient(c, r * 1.6)
        g = QColor(self._color)
        g.setAlpha(70)
        glow.setColorAt(0.0, g)
        g.setAlpha(0)
        glow.setColorAt(1.0, g)
        p.setBrush(glow)
        p.drawEllipse(c, r * 1.6, r * 1.6)

        body = QRadialGradient(QPointF(c.x() - r * 0.3, c.y() - r * 0.3), r * 1.4)
        body.setColorAt(0.0, self._color.lighter(130))
        body.setColorAt(1.0, self._color.darker(260))
        p.setBrush(body)
        p.drawEllipse(c, r, r)
