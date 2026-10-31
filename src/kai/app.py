"""Entry point: wires the window, the onboarding dialog and the live agent."""

from __future__ import annotations

import argparse
import logging
import signal
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QSystemTrayIcon

from kai import __version__, config, diag, logs, transcript, voices
from kai.tools import Permission
from kai.ui.confirm_dialog import ConfirmDialog
from kai.ui.diag_dialog import DiagDialog
from kai.ui.main_window import MainWindow
from kai.ui.onboarding import OnboardingDialog
from kai.ui.theme import STYLESHEET
from kai.ui.tray import Tray, app_icon
from kai.ui.settings_dialog import SettingsDialog


class Controller:
    def __init__(self, window: MainWindow):
        self.window = window
        self.agent = None
        window.text_submitted.connect(self._send_text)
        window.mic_toggled.connect(self._toggle_mic)
        window.change_key_requested.connect(self.change_key)
        window.diagnostics_requested.connect(self.open_diagnostics)
        window.settings_requested.connect(self.open_settings)

    def start_agent(self) -> None:
        from kai.live import LiveAgent

        key = config.get_api_key()
        if not key:
            return
        self.stop_agent()
        settings = config.load_settings()
        self.agent = a = LiveAgent(
            key,
            microphone=settings["microphone"],
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
        a.set_permission_level(Permission(settings["permissions"]))
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

    def open_settings(self) -> None:
        before = config.load_settings()
        dialog = SettingsDialog(self.window)
        if dialog.exec() != QDialog.Accepted:
            return
        after = config.load_settings()
        transcript.set_enabled(after["record_conversation"])
        if not self.agent:
            return
        changed = sorted(k for k in after if after[k] != before.get(k))
        logging.getLogger("kai").info("Settings changed: %s", ", ".join(changed) or "nothing")
        logs.set_detailed(after["detailed_logs"])
        if dialog.voice_changed(before):
            self.start_agent()  # voice, accent and microphone are fixed per session
        else:
            self.agent.set_permission_level(Permission(after["permissions"]))

    def open_diagnostics(self) -> None:
        DiagDialog(self.window).exec()

    def _on_confirm_requested(self, agent, request_id: int, title: str, detail: str) -> None:
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


def send_diagnostics(include_conversation: bool) -> int:
    try:
        report_id = diag.upload(diag.collect(include_conversation))
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1
    print(f"Diagnostics sent. Reference: {report_id}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="kai", description="Voice assistant for your computer.")
    parser.add_argument("--version", action="version", version=f"kai {__version__}")
    parser.add_argument("--debug", action="store_true", help="detailed logs for this run")
    parser.add_argument("--send-diagnostics", action="store_true",
                        help="upload logs and system info (no conversations, no API key) and exit")
    parser.add_argument("--include-conversation", action="store_true",
                        help="with --send-diagnostics: also send the recorded conversation, "
                             "if recording is on")
    opts, qt_args = parser.parse_known_args()

    settings = config.load_settings()
    logs.setup(detailed=opts.debug or settings["detailed_logs"])
    if opts.send_diagnostics:
        return send_diagnostics(opts.include_conversation)
    transcript.set_enabled(settings["record_conversation"])
    logs.route_qt_messages()
    # Let Ctrl+C in the terminal quit cleanly: Python only sees signals between Qt events.
    signal.signal(signal.SIGINT, lambda *_: QApplication.quit())

    app = QApplication(sys.argv[:1] + qt_args)
    app.setApplicationName("kai")
    app.setApplicationVersion(__version__)
    app.setStyleSheet(STYLESHEET)
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)  # dialogs closing must not quit; use "Quit kai"

    heartbeat = QTimer(interval=250)  # wakes Python up so it can handle Ctrl+C
    heartbeat.timeout.connect(lambda: None)
    heartbeat.start()

    window = MainWindow()
    controller = Controller(window)
    window.quit_requested.connect(app.quit)
    app.aboutToQuit.connect(controller.stop_agent)
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = Tray(window)
        tray.show()
    window.show()

    if config.get_api_key():
        controller.start_agent()
    elif not controller.change_key():
        return 0
    return app.exec()
