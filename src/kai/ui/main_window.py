"""The main window: an orb, a short transcript and a text field. Nothing else."""

from __future__ import annotations

import html

from PySide6.QtCore import QPoint, Qt, Signal
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

from kai.ui.orb import Orb
from kai.ui.theme import MUTED, TEXT

STATE_LABELS = {
    "offline": "offline",
    "connecting": "connecting…",
    "listening": "listening",
    "thinking": "thinking…",
    "speaking": "speaking",
}


class MainWindow(QWidget):
    text_submitted = Signal(str)
    mic_toggled = Signal(bool)
    change_key_requested = Signal()
    diagnostics_requested = Signal()
    settings_requested = Signal()

    def __init__(self):
        super().__init__(objectName="root")
        self.setWindowTitle("kai")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.resize(380, 560)
        self._drag_from: QPoint | None = None
        self._speaker: str | None = None  # who the last transcript line belongs to

        self.menu_btn = QToolButton(text="⋯")
        self.menu_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self)
        menu.addAction("Settings…", self.settings_requested.emit)
        menu.addAction("Change API key…", self.change_key_requested.emit)
        menu.addAction("Send diagnostics…", self.diagnostics_requested.emit)
        menu.addSeparator()
        menu.addAction("Quit", self.close)
        self.menu_btn.setMenu(menu)

        close_btn = QToolButton(text="✕")
        close_btn.clicked.connect(self.close)

        top = QHBoxLayout()
        top.addWidget(QLabel("kai"))
        top.addStretch()
        top.addWidget(self.menu_btn)
        top.addWidget(close_btn)

        self.orb = Orb()
        self.status = QLabel(objectName="muted", alignment=Qt.AlignCenter)

        self.transcript = QTextBrowser(openExternalLinks=True)
        self.transcript.setMinimumHeight(140)

        self.mic_btn = QToolButton(text="●", checkable=True, checked=True)
        self.mic_btn.setToolTip("Microphone on/off")
        self.mic_btn.toggled.connect(self._on_mic_toggled)

        self.input = QLineEdit(placeholderText="Type a message…")
        self.input.returnPressed.connect(self._submit)

        bottom = QHBoxLayout()
        bottom.addWidget(self.mic_btn)
        bottom.addWidget(self.input)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 20)
        layout.setSpacing(10)
        layout.addLayout(top)
        layout.addWidget(self.orb, 3)
        layout.addWidget(self.status)
        layout.addWidget(self.transcript, 2)
        layout.addLayout(bottom)

        self.set_state("offline")

    # ---- updates from the agent ----

    def set_state(self, state: str) -> None:
        self.orb.set_state(state)
        if self.mic_btn.isChecked() or state != "listening":
            self.status.setText(STATE_LABELS.get(state, state))
        else:
            self.status.setText("muted")

    def set_level(self, level: float) -> None:
        self.orb.set_level(level)

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

    # ---- user input ----

    def _submit(self) -> None:
        text = self.input.text().strip()
        if text:
            self.input.clear()
            self.append("you", text)
            self.text_submitted.emit(text)

    def _on_mic_toggled(self, on: bool) -> None:
        self.mic_btn.setText("●" if on else "○")
        self.mic_toggled.emit(on)

    # ---- frameless window dragging ----

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._drag_from = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e) -> None:
        if self._drag_from is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_from)

    def mouseReleaseEvent(self, e) -> None:
        self._drag_from = None
