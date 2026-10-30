"""Asks the user to approve a sensitive action, showing exactly what will run."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout

from kai.ui.theme import MUTED


class ConfirmDialog(QDialog):
    def __init__(self, title: str, detail: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("kai needs your permission")
        self.setMinimumWidth(440)
        self.setWindowFlag(Qt.WindowStaysOnTopHint)

        heading = QLabel("kai wants to do this", objectName="title")
        reason = QLabel(title, wordWrap=True)

        command = QPlainTextEdit(detail, readOnly=True)
        command.setStyleSheet('font-family: "JetBrains Mono", "Cascadia Mono", Consolas, monospace;')
        lines = detail.count("\n") + 1
        command.setFixedHeight(min(220, 28 + 20 * lines))

        hint = QLabel("Only allow it if you understand and trust it.", objectName="muted")
        hint.setStyleSheet(f"color: {MUTED}; font-size: 12px;")

        deny = QPushButton("Deny")
        deny.clicked.connect(self.reject)
        allow = QPushButton("Allow", objectName="primary")
        allow.clicked.connect(self.accept)
        deny.setDefault(True)  # Enter never approves by accident

        buttons = QHBoxLayout()
        buttons.addWidget(hint)
        buttons.addStretch()
        buttons.addWidget(deny)
        buttons.addWidget(allow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)
        layout.addWidget(heading)
        layout.addWidget(reason)
        layout.addWidget(command)
        layout.addLayout(buttons)
