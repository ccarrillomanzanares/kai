"""System tray icon: show/hide kai, settings and quit."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from kai.ui.main_window import MainWindow


def app_icon(size: int = 64) -> QIcon:
    """A dark capsule with a glowing line: a tiny version of the light line."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#0d0d0f"))
    p.drawRoundedRect(QRectF(0, size * 0.25, size, size * 0.5), size * 0.25, size * 0.25)
    grad = QLinearGradient(size * 0.12, 0, size * 0.88, 0)
    grad.setColorAt(0.0, QColor(255, 90, 95, 0))
    grad.setColorAt(0.5, QColor("#ffd1cc"))
    grad.setColorAt(1.0, QColor(255, 90, 95, 0))
    for width, alpha in ((size * 0.18, 0.25), (size * 0.09, 1.0)):
        pen = QPen(grad, width)
        pen.setCapStyle(Qt.RoundCap)
        p.setOpacity(alpha)
        p.setPen(pen)
        p.drawLine(QPointF(size * 0.16, size / 2), QPointF(size * 0.84, size / 2))
    p.end()
    return QIcon(pixmap)


class Tray(QSystemTrayIcon):
    def __init__(self, window: MainWindow):
        super().__init__(app_icon(), window)
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
