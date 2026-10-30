"""Entry point: wires the window, the onboarding dialog and the live agent."""

from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication, QDialog

from kai import __version__, config
from kai.ui.main_window import MainWindow
from kai.ui.onboarding import OnboardingDialog
from kai.ui.theme import STYLESHEET


class Controller:
    def __init__(self, window: MainWindow):
        self.window = window
        self.agent = None
        window.text_submitted.connect(self._send_text)
        window.mic_toggled.connect(self._toggle_mic)
        window.change_key_requested.connect(self.change_key)

    def start_agent(self) -> None:
        from kai.live import LiveAgent

        key = config.get_api_key()
        if not key:
            return
        self.stop_agent()
        self.agent = a = LiveAgent(key)
        a.state_changed.connect(self.window.set_state)
        a.level.connect(self.window.set_level)
        a.user_said.connect(lambda t: self.window.append("you", t))
        a.kai_said.connect(lambda t: self.window.append("kai", t))
        a.error.connect(self.window.show_notice)
        a.fatal_error.connect(self._on_fatal)
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


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
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
