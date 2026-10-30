"""First-run dialog: explains how to get a free Gemini API key and stores it."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from kai import config
from kai.ui.theme import ACCENT

HELP_HTML = f"""
<p style="line-height:150%">
kai talks to Google's <b>Gemini 3.8 Live</b> model. Using it is free,
you just need your own API key:</p>
<ol style="line-height:170%">
<li>Open <a style="color:{ACCENT}" href="{config.API_KEY_URL}">Google AI Studio</a> and sign in with your Google account.</li>
<li>Click <b>Create API key</b> and accept the terms.</li>
<li>Copy the key and paste it below.</li>
</ol>
<p style="line-height:150%">Your key is stored in your system's secure keychain and is only sent to Google.</p>
<p style="line-height:150%; color:#8a8a94">On the free tier Google may use your conversations to improve
its products. Enable billing on your key if you prefer they don't.</p>
"""


class _Validator(QThread):
    done = Signal(str)  # empty string means valid

    def __init__(self, key: str):
        super().__init__()
        self._key = key

    def run(self) -> None:
        self.done.emit(config.validate_api_key(self._key) or "")


class OnboardingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to kai")
        self.setMinimumWidth(460)
        self._validator: _Validator | None = None

        title = QLabel("Welcome to kai", objectName="title")
        help_text = QLabel(HELP_HTML, wordWrap=True, openExternalLinks=True)

        self.key_edit = QLineEdit(placeholderText="Paste your Gemini API key")
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.textChanged.connect(self._on_text_changed)

        self.error_label = QLabel(objectName="error", wordWrap=True)
        self.error_label.hide()

        get_key = QPushButton("Get a free key")
        get_key.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(config.API_KEY_URL)))
        self.save_btn = QPushButton("Continue", objectName="primary", enabled=False)
        self.save_btn.setDefault(True)
        self.save_btn.clicked.connect(self._save)

        buttons = QHBoxLayout()
        buttons.addWidget(get_key)
        buttons.addStretch()
        buttons.addWidget(self.save_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)
        layout.addWidget(title)
        layout.addWidget(help_text)
        layout.addWidget(self.key_edit)
        layout.addWidget(self.error_label)
        layout.addLayout(buttons)

    def _on_text_changed(self, text: str) -> None:
        self.error_label.hide()
        self.save_btn.setEnabled(config.looks_like_api_key(text))

    def _save(self) -> None:
        self.save_btn.setEnabled(False)
        self.save_btn.setText("Checking…")
        self._validator = _Validator(self.key_edit.text())
        self._validator.done.connect(self._on_validated)
        self._validator.start()

    def _on_validated(self, error: str) -> None:
        self.save_btn.setText("Continue")
        self.save_btn.setEnabled(True)
        if error:
            self.error_label.setText(error)
            self.error_label.show()
            return
        config.set_api_key(self.key_edit.text())
        self.accept()
