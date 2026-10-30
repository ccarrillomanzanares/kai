"""Logging to a rotating file in the config directory.

Rule: never log what the user or kai said, nor tool arguments. Logs must be
safe to send as diagnostics.
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


def setup() -> None:
    formatter = _RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler = RotatingFileHandler(log_file(), maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    console = logging.StreamHandler()
    for h in (file_handler, console):
        h.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[file_handler, console], force=True)
    # Third-party libraries can log request bodies at DEBUG; keep them quiet.
    for name in ("httpx", "httpcore", "websockets", "google_genai"):
        logging.getLogger(name).setLevel(logging.WARNING)

    def excepthook(exc_type, exc, tb):
        logging.getLogger("kai").critical("Unhandled exception", exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = excepthook
