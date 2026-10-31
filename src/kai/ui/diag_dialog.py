"""Send diagnostics: shows exactly what will be uploaded, then returns a reference."""

from __future__ import annotations

import json

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
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
    "<b>It never includes your API key. Your recorded conversation, if any, is "
    "included only while the box below is ticked.</b>"
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
        # Recording is opt-in for diagnostics, so a recording present is meant to be sent:
        # include it by default, and let the user untick it.
        has_conversation = diag.has_conversation()
        self._report = diag.collect(include_conversation=has_conversation)
        self._uploader: _Uploader | None = None

        self.include = QCheckBox("Include the recorded conversation")
        self.include.setToolTip("What you and kai said, and kai's actions. "
                                "Use \"Show report\" to read it before sending.")
        self.include.setChecked(has_conversation)
        self.include.toggled.connect(self._toggle_conversation)

        self.message = QLabel(INTRO, wordWrap=True)
        self.message.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.details = QPlainTextEdit(json.dumps(self._report, indent=2, ensure_ascii=False),
                                      readOnly=True)
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
        layout.addWidget(self.include)
        self.include.setVisible(has_conversation)  # after it has a parent: no stray window
        layout.addWidget(self.details)
        layout.addLayout(buttons)

    def _toggle_conversation(self, on: bool) -> None:
        self._report = diag.collect(include_conversation=on)
        self.details.setPlainText(json.dumps(self._report, indent=2, ensure_ascii=False))

    def _toggle_details(self) -> None:
        self.details.setVisible(not self.details.isVisible())
        self.details_btn.setText("Hide report" if self.details.isVisible() else "Show report")
        self.adjustSize()

    def _send(self) -> None:
        self.send_btn.setEnabled(False)
        self.include.setEnabled(False)
        self.send_btn.setText("Sending…")
        self._uploader = _Uploader(self._report)
        self._uploader.done.connect(self._on_done)
        self._uploader.start()

    def _on_done(self, report_id: str, error: str) -> None:
        if error:
            self.message.setText(f'<span style="color:#f08a8a">{error}</span>')
            self.send_btn.setText("Retry")
            self.include.setEnabled(True)
            self.send_btn.setEnabled(True)
            return
        QApplication.clipboard().setText(report_id)
        self.message.setText(
            f"Sent. Your reference is <b>{report_id}</b> (copied to the clipboard). "
            "Share it when you report the problem."
        )
        self.details.hide()
        self.include.hide()
        self.details_btn.hide()
        self.cancel_btn.hide()
        self.send_btn.setText("Done")
        self.send_btn.setEnabled(True)
        self.send_btn.clicked.disconnect()
        self.send_btn.clicked.connect(self.accept)
