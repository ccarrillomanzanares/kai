"""Entry point: wires the window, the onboarding dialog and the live agent."""

from __future__ import annotations

import argparse
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog

from kai import __version__, config, diag, logs, voices
from kai.ui.confirm_dialog import ConfirmDialog
from kai.ui.diag_dialog import DiagDialog
from kai.ui.main_window import MainWindow
from kai.ui.onboarding import OnboardingDialog
from kai.ui.theme import STYLESHEET
from kai.ui.voice_dialog import VoiceDialog


class Controller:
    def __init__(self, window: MainWindow):
        self.window = window
        self.agent = None
        window.text_submitted.connect(self._send_text)
        window.mic_toggled.connect(self._toggle_mic)
        window.change_key_requested.connect(self.change_key)
        window.diagnostics_requested.connect(self.open_diagnostics)
        window.voice_requested.connect(self.open_voice_settings)

    def start_agent(self) -> None:
        from kai.live import LiveAgent

        key = config.get_api_key()
        if not key:
            return
        self.stop_agent()
        settings = config.load_settings()
        self.agent = a = LiveAgent(
            key,
            voice=settings["voice"],
            accent_instruction=voices.accent_instruction(settings["accent"],
                                                         settings["custom_accent"]),
        )
        a.state_changed.connect(self.window.set_state)
        a.level.connect(self.window.set_level)
        a.user_said.connect(lambda t: self.window.append("you", t))
        a.kai_said.connect(lambda t: self.window.append("kai", t))
        a.error.connect(self.window.show_notice)
        a.fatal_error.connect(self._on_fatal)
        a.ui_action.connect(self._on_ui_action)
        a.confirm_requested.connect(lambda rid, title, detail: self._on_confirm_requested(a, rid, title, detail))
        a.set_mic_enabled(self.window.mic_btn.isChecked())
        a.start()

    def stop_agent(self) -> None:
        if self.agent:
            self.agent.blockSignals(True)
            self.agent.stop()
            self.agent = None

    def change_key(self) -> bool:
        if OnboardingDialog(self.window).exec() == QDialog.Accepted:
            self.start_agent()
            return True
        return False

    def open_voice_settings(self) -> None:
        if VoiceDialog(self.window).exec() == QDialog.Accepted and self.agent:
            self.start_agent()  # voice and accent are fixed per session

    def open_diagnostics(self) -> None:
        DiagDialog(self.window).exec()

    def _on_confirm_requested(self, agent, request_id: int, title: str, detail: str) -> None:
        self.window.raise_()
        self.window.activateWindow()
        approved = ConfirmDialog(title, detail, self.window).exec() == QDialog.Accepted
        agent.resolve_confirmation(request_id, approved)

    def _on_ui_action(self, name: str) -> None:
        if name == "open_diagnostics":
            # Defer so the tool response goes out before the modal dialog opens.
            QTimer.singleShot(0, self.open_diagnostics)

    def _on_fatal(self, message: str) -> None:
        self.stop_agent()
        self.window.set_state("offline")
        self.window.show_notice(message)
        self.change_key()

    def _send_text(self, text: str) -> None:
        if self.agent:
            self.agent.send_text(text)

    def _toggle_mic(self, on: bool) -> None:
        if self.agent:
            self.agent.set_mic_enabled(on)


def send_diagnostics() -> int:
    try:
        report_id = diag.upload(diag.collect())
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1
    print(f"Diagnostics sent. Reference: {report_id}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="kai", description="Voice assistant for your computer.")
    parser.add_argument("--version", action="version", version=f"kai {__version__}")
    parser.add_argument("--send-diagnostics", action="store_true",
                        help="upload logs and system info (no conversations, no API key) and exit")
    opts, qt_args = parser.parse_known_args()

    logs.setup()
    if opts.send_diagnostics:
        return send_diagnostics()

    app = QApplication(sys.argv[:1] + qt_args)
    app.setApplicationName("kai")
    app.setApplicationVersion(__version__)
    app.setStyleSheet(STYLESHEET)

    window = MainWindow()
    controller = Controller(window)
    app.aboutToQuit.connect(controller.stop_agent)
    window.show()

    if config.get_api_key():
        controller.start_agent()
    elif not controller.change_key():
        return 0
    return app.exec()
