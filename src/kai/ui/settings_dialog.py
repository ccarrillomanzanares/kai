"""Settings: voice, accent and permission level."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QMessageBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from kai import audio, config
from kai.tools import PERMISSION_LABELS, Permission
from kai.voices import ACCENTS, AUTO, CUSTOM, VOICES

PERMISSION_HINTS = {
    Permission.STRICT: "kai asks before opening, typing or running anything.",
    Permission.BALANCED: "kai asks before running commands, closing programs or typing "
                         "in a terminal.",
    Permission.TRUSTED: "kai acts on its own. It still asks before deleting, uninstalling "
                        "or shutting down.",
}


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(440)
        self._settings = config.load_settings()

        self.voice = QComboBox()
        self.voice.addItem("Default", None)
        for name, style in VOICES:
            self.voice.addItem(f"{name} · {style}", name)
        self.voice.setCurrentIndex(max(0, self.voice.findData(self._settings["voice"])))

        self.accent = QComboBox()
        self.accent.addItem("Automatic (follow the conversation)", AUTO)
        for key, (label, _, _) in ACCENTS.items():
            self.accent.addItem(label, key)
        self.accent.addItem("Custom…", CUSTOM)
        self.accent.setCurrentIndex(max(0, self.accent.findData(self._settings["accent"])))

        self.custom = QLineEdit(self._settings["custom_accent"],
                                placeholderText="e.g. Spanish with a soft Galician accent")
        self.accent.currentIndexChanged.connect(self._sync)

        self.permissions = QComboBox()
        for level, label in PERMISSION_LABELS.items():
            self.permissions.addItem(label, level.value)
        self.permissions.setCurrentIndex(
            max(0, self.permissions.findData(self._settings["permissions"])))
        self.permissions.currentIndexChanged.connect(self._sync)
        self.permission_hint = QLabel(objectName="muted", wordWrap=True)

        self.microphone = QComboBox()
        self.microphone.addItem("System default", None)
        try:
            for name in audio.input_devices():
                self.microphone.addItem(name, name)
        except Exception:  # no audio system: keep just the default
            pass
        self.microphone.setCurrentIndex(
            max(0, self.microphone.findData(self._settings["microphone"])))

        self.detailed_logs = QCheckBox("Detailed logs (to help fix problems)")
        self.detailed_logs.setChecked(self._settings["detailed_logs"])

        self.record = QCheckBox("Record conversations for diagnostics")
        self.record.setToolTip("Saves what you and kai say, kai's actions and its last "
                               "screenshots on this computer. Sent only if you choose it when "
                               "sending diagnostics.")
        self.record.setChecked(self._settings["record_conversation"])
        self.record.toggled.connect(self._confirm_record)

        form = QFormLayout()
        form.setSpacing(12)
        form.addRow("Microphone", self.microphone)
        form.addRow("Voice", self.voice)
        form.addRow("Accent", self.accent)
        form.addRow("", self.custom)
        form.addRow("Permissions", self.permissions)
        form.addRow("", self.permission_hint)
        form.addRow("", self.detailed_logs)
        form.addRow("", self.record)

        hint = QLabel("You can listen to every voice in Google AI Studio. Changing the "
                      "microphone, voice or accent starts a new conversation.",
                      objectName="muted", wordWrap=True)

        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save", objectName="primary")
        save.setDefault(True)
        save.clicked.connect(self._save)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(save)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(QLabel("Settings", objectName="title"))
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addLayout(buttons)
        self._sync()

    def _sync(self) -> None:
        self.custom.setVisible(self.accent.currentData() == CUSTOM)
        self.permission_hint.setText(PERMISSION_HINTS[Permission(self.permissions.currentData())])

    def _confirm_record(self, on: bool) -> None:
        if not on:
            return
        answer = QMessageBox.question(
            self, "Record conversations",
            "kai will save what you and kai say, every action it takes (including what it "
            "types and the web addresses it opens) and its last screenshots, on this "
            "computer.\n\n"
            "It is only sent if you tick \"Include the recorded conversation\" when sending "
            "diagnostics. Turning this option off deletes the recording.\n\n"
            "Turn on recording?",
        )
        if answer != QMessageBox.Yes:
            self.record.blockSignals(True)
            self.record.setChecked(False)
            self.record.blockSignals(False)

    def voice_changed(self, before: dict) -> bool:
        keys = ("voice", "accent", "custom_accent", "microphone")
        return any(before[k] != self._settings[k] for k in keys)

    def _save(self) -> None:
        self._settings.update(
            voice=self.voice.currentData(),
            accent=self.accent.currentData(),
            custom_accent=self.custom.text().strip(),
            permissions=self.permissions.currentData(),
            microphone=self.microphone.currentData(),
            detailed_logs=self.detailed_logs.isChecked(),
            record_conversation=self.record.isChecked(),
        )
        config.save_settings(self._settings)
        self.accept()
