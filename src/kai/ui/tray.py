"""System tray icon: show/hide kai, settings and quit."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from kai.ui.main_window import MainWindow


def scanner_icon(size: int = 64) -> QIcon:
    """Five LEDs, the middle one lit: a tiny version of the scanner."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#0d0d0f"))
    p.drawRoundedRect(QRectF(0, size * 0.28, size, size * 0.44), size * 0.22, size * 0.22)
    alphas = [0.25, 0.6, 1.0, 0.6, 0.25]
    w, gap = size * 0.13, size * 0.04
    x = (size - (5 * w + 4 * gap)) / 2
    for a in alphas:
        c = QColor("#ff2d2d")
        c.setAlphaF(a)
        p.setBrush(c)
        p.drawRoundedRect(QRectF(x, size * 0.42, w, size * 0.16), 2, 2)
        x += w + gap
    p.end()
    return QIcon(pixmap)


class Tray(QSystemTrayIcon):
    def __init__(self, window: MainWindow):
        super().__init__(scanner_icon(), window)
        self._window = window
        self.setToolTip("kai")
        menu = QMenu()
        self._toggle = menu.addAction("Hide kai", self.toggle_window)
        menu.addAction("Settings…", window.settings_requested.emit)
        menu.addAction("Send diagnostics…", window.diagnostics_requested.emit)
        menu.addSeparator()
        menu.addAction("Quit kai", window.quit_requested.emit)
        self.setContextMenu(menu)
        self._menu = menu  # keep a reference: the tray doesn't own it
        self.activated.connect(self._on_activated)

    def toggle_window(self) -> None:
        if self._window.isVisible():
            self._window.hide()
            self._toggle.setText("Show kai")
        else:
            self._window.show()
            self._window.raise_()
            self._toggle.setText("Hide kai")

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_window()
