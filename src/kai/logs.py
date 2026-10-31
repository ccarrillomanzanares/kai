"""Logging to a rotating file in the config directory.

Rule: never log what the user or kai said, nor tool arguments. Logs must be
safe to send as diagnostics. The opt-in conversation recording lives in its
own file (see transcript.py).
"""

from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from kai.config import config_dir

_SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),  # Google API keys
    re.compile(r"AQ\.[0-9A-Za-z_\-.]{20,}"),  # Google AI Studio keys
    re.compile(r"(key=)[^&\s\"']+"),  # keys in URLs
]


def redact(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda m: (m.group(1) if m.groups() else "") + "[REDACTED]", text)
    home = str(Path.home())
    return text.replace(home, "~") if home not in ("", "/") else text


class _RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def log_file() -> Path:
    path = config_dir() / "logs"
    path.mkdir(exist_ok=True)
    return path / "kai.log"


def set_detailed(detailed: bool) -> None:
    """Detailed logs add frequent events (state changes, server signals) at DEBUG level."""
    logging.getLogger("kai").setLevel(logging.DEBUG if detailed else logging.INFO)


def setup(detailed: bool = False) -> None:
    formatter = _RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(log_file(), maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    console = logging.StreamHandler()
    for h in (file_handler, console):
        h.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[file_handler, console], force=True)
    # Third-party libraries can log request bodies at DEBUG; keep them quiet.
    for name in ("httpx", "httpcore", "websockets", "google_genai"):
        logging.getLogger(name).setLevel(logging.WARNING)

    logging.getLogger().handlers[0].setLevel(logging.DEBUG)
    console.setLevel(logging.INFO)  # the terminal stays readable; details go to the file
    set_detailed(detailed)

    def excepthook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            return  # Ctrl+C in the terminal: handled as a normal quit
        logging.getLogger("kai").critical("Unhandled exception", exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = excepthook


def route_qt_messages() -> None:
    """Send Qt's own warnings to the log instead of the bare terminal."""
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    qt_log = logging.getLogger("kai.qt")
    levels = {QtMsgType.QtDebugMsg: logging.DEBUG, QtMsgType.QtInfoMsg: logging.DEBUG,
              QtMsgType.QtWarningMsg: logging.WARNING, QtMsgType.QtCriticalMsg: logging.ERROR,
              QtMsgType.QtFatalMsg: logging.CRITICAL}

    def handler(msg_type, context, message):
        level = levels.get(msg_type, logging.WARNING)
        if "setPointSize" in message:  # harmless: stylesheets size fonts in pixels
            level = logging.DEBUG
        qt_log.log(level, "%s", message)

    qInstallMessageHandler(handler)
