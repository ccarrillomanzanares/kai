"""The main window: a slim floating capsule with the light line, docked above the taskbar.

Clicking the line unfolds a panel upwards with the transcript and a text field.
"""

from __future__ import annotations

import html

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from kai.ui.lightline import LightLine
from kai.ui.theme import BG, MUTED, TEXT

STATE_LABELS = {
    "offline": "offline",
    "connecting": "connecting…",
    "listening": "listening",
    "thinking": "thinking…",
    "speaking": "speaking",
}

WIDTH = 340
BAR_HEIGHT = 40
PANEL_HEIGHT = 300
DOCK_MARGIN = 12
DRAG_THRESHOLD = 4


class MainWindow(QWidget):
    text_submitted = Signal(str)
    mic_toggled = Signal(bool)
    change_key_requested = Signal()
    diagnostics_requested = Signal()
    settings_requested = Signal()
    quit_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("kai")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._state = "offline"
        self._speaker: str | None = None  # who the last transcript line belongs to
        self._press: QPoint | None = None
        self._drag_from: QPoint | None = None
        self._docked = False

        # ---- panel (hidden until the scanner is clicked) ----
        self.status = QLabel(objectName="muted")
        self.transcript = QTextBrowser(openExternalLinks=True)
        self.input = QLineEdit(placeholderText="Type a message…")
        self.input.returnPressed.connect(self._submit)

        self.panel = QWidget()
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(18, 16, 18, 4)
        panel_layout.setSpacing(10)
        panel_layout.addWidget(self.status)
        panel_layout.addWidget(self.transcript, 1)
        panel_layout.addWidget(self.input)
        self.panel.hide()

        # ---- bar ----
        self.mic_btn = QToolButton(text="●", checkable=True, checked=True, objectName="barButton")
        self.mic_btn.setToolTip("Microphone on/off")
        self.mic_btn.toggled.connect(self._on_mic_toggled)

        self.scanner = LightLine()
        self.scanner.setToolTip("kai — click to show the conversation")

        self.menu_btn = QToolButton(text="⋯", objectName="barButton")
        self.menu_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self)
        menu.addAction("Settings…", self.settings_requested.emit)
        menu.addAction("Change API key…", self.change_key_requested.emit)
        menu.addAction("Send diagnostics…", self.diagnostics_requested.emit)
        menu.addSeparator()
        menu.addAction("Quit kai", self.quit_requested.emit)
        self.menu_btn.setMenu(menu)

        bar = QHBoxLayout()
        bar.setContentsMargins(10, 0, 6, 0)
        bar.setSpacing(6)
        bar.addWidget(self.mic_btn)
        bar.addWidget(self.scanner, 1)
        bar.addWidget(self.menu_btn)
        self.bar = QWidget()
        self.bar.setFixedHeight(BAR_HEIGHT)
        self.bar.setLayout(bar)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.panel, 1)
        layout.addWidget(self.bar)

        self.setFixedSize(WIDTH, BAR_HEIGHT)
        self.set_state("offline")

    # ---- placement ----

    def showEvent(self, event) -> None:
        if not self._docked:
            self._docked = True
            self.dock()
        super().showEvent(event)

    def dock(self) -> None:
        """Bottom center of the screen, just above the taskbar."""
        area = (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()
        self.move(area.center().x() - self.width() // 2,
                  area.bottom() - self.height() - DOCK_MARGIN)

    def toggle_panel(self) -> None:
        self.set_panel_visible(not self.panel.isVisible())

    def set_panel_visible(self, visible: bool) -> None:
        if visible == self.panel.isVisible():
            return
        bottom = self.geometry().bottom()
        self.panel.setVisible(visible)
        height = BAR_HEIGHT + (PANEL_HEIGHT if visible else 0)
        self.setFixedSize(WIDTH, height)
        self.move(self.x(), bottom - height + 1)  # grow upwards, keep the bar in place
        if visible:
            self.input.setFocus()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        radius = BAR_HEIGHT / 2 if not self.panel.isVisible() else 18
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        bg = QColor(BG)
        bg.setAlphaF(0.88)
        p.fillPath(path, bg)
        edge = QColor(255, 255, 255, 18)
        p.setPen(edge)
        p.drawPath(path)

    # ---- updates from the agent ----

    def set_state(self, state: str) -> None:
        self._state = state
        muted = state == "listening" and not self.mic_btn.isChecked()
        self.scanner.set_state("muted" if muted else state)
        self.status.setText("muted" if muted else STATE_LABELS.get(state, state))

    def set_level(self, level: float) -> None:
        self.scanner.set_level(level)

    def append(self, who: str, text: str) -> None:
        """Append a transcript chunk, merging consecutive chunks from the same speaker."""
        cursor = self.transcript.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        if who != self._speaker and self._speaker is not None:
            cursor.insertHtml("<br><br>")
        self._speaker = who
        color = MUTED if who == "you" else TEXT
        cursor.insertHtml(f'<span style="color:{color}">{html.escape(text)}</span>')
        self.transcript.setTextCursor(cursor)
        self.transcript.ensureCursorVisible()

    def show_notice(self, text: str) -> None:
        self.status.setText(text)
        self.scanner.setToolTip(f"kai — {text}")

    # ---- user input ----

    def _submit(self) -> None:
        text = self.input.text().strip()
        if text:
            self.input.clear()
            self.append("you", text)
            self.text_submitted.emit(text)

    def _on_mic_toggled(self, on: bool) -> None:
        self.mic_btn.setText("●" if on else "○")
        self.set_state(self._state)
        self.mic_toggled.emit(on)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape and self.panel.isVisible():
            self.set_panel_visible(False)
        else:
            super().keyPressEvent(e)

    # ---- drag anywhere on the bar; a click on the scanner toggles the panel ----

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._press = e.globalPosition().toPoint()
            self._drag_from = self._press - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e) -> None:
        if self._press is None or not e.buttons() & Qt.LeftButton:
            return
        pos = e.globalPosition().toPoint()
        if (pos - self._press).manhattanLength() > DRAG_THRESHOLD:
            self.move(pos - self._drag_from)

    def mouseReleaseEvent(self, e) -> None:
        if self._press is not None:
            moved = (e.globalPosition().toPoint() - self._press).manhattanLength()
            on_scanner = self.scanner.geometry().contains(
                self.bar.mapFrom(self, e.position().toPoint()))
            if moved <= DRAG_THRESHOLD and on_scanner:
                self.toggle_panel()
        self._press = None
