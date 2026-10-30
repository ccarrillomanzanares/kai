"""Send diagnostics: shows exactly what will be uploaded, then returns a reference."""

from __future__ import annotations

import json

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from kai import diag

INTRO = (
    "Send a diagnostics report to help fix problems. It includes kai's recent "
    "logs, versions, your OS and audio devices.<br><br>"
    "<b>It never includes your conversations or your API key.</b>"
)


class _Uploader(QThread):
    done = Signal(str, str)  # (report id, error)

    def __init__(self, report: dict):
        super().__init__()
        self._report = report

    def run(self) -> None:
        try:
            self.done.emit(diag.upload(self._report), "")
        except RuntimeError as e:
            self.done.emit("", str(e))


class DiagDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Send diagnostics")
        self.setMinimumWidth(460)
        self._report = diag.collect()
        self._uploader: _Uploader | None = None

        self.message = QLabel(INTRO, wordWrap=True)
        self.message.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.details = QPlainTextEdit(json.dumps(self._report, indent=2), readOnly=True)
        self.details.setMinimumHeight(260)
        self.details.hide()

        self.details_btn = QPushButton("Show report")
        self.details_btn.clicked.connect(self._toggle_details)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        self.send_btn = QPushButton("Send", objectName="primary")
        self.send_btn.setDefault(True)
        self.send_btn.clicked.connect(self._send)

        buttons = QHBoxLayout()
        buttons.addWidget(self.details_btn)
        buttons.addStretch()
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.send_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(QLabel("Send diagnostics", objectName="title"))
        layout.addWidget(self.message)
        layout.addWidget(self.details)
        layout.addLayout(buttons)

    def _toggle_details(self) -> None:
        self.details.setVisible(not self.details.isVisible())
        self.details_btn.setText("Hide report" if self.details.isVisible() else "Show report")
        self.adjustSize()

    def _send(self) -> None:
        self.send_btn.setEnabled(False)
        self.send_btn.setText("Sending…")
        self._uploader = _Uploader(self._report)
        self._uploader.done.connect(self._on_done)
        self._uploader.start()

    def _on_done(self, report_id: str, error: str) -> None:
        if error:
            self.message.setText(f'<span style="color:#f08a8a">{error}</span>')
            self.send_btn.setText("Retry")
            self.send_btn.setEnabled(True)
            return
        QApplication.clipboard().setText(report_id)
        self.message.setText(
            f"Sent. Your reference is <b>{report_id}</b> (copied to the clipboard). "
            "Share it when you report the problem."
        )
        self.details.hide()
        self.details_btn.hide()
        self.cancel_btn.hide()
        self.send_btn.setText("Done")
        self.send_btn.setEnabled(True)
        self.send_btn.clicked.disconnect()
        self.send_btn.clicked.connect(self.accept)
