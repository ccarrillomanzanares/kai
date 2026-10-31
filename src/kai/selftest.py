"""`kai --self-test`: check that a build can load everything kai needs.

Meant for the packaged app (CI runs it after each build), where a missing module
or library only shows up when a tool is first used. Results go to stdout when
there is one, and always to selftest.txt in kai's logs folder.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

from kai import __version__, logs


def _check_audio() -> str:
    import sounddevice as sd

    return sd.get_portaudio_version()[1]


def _check_browser() -> str:
    from playwright._impl._driver import compute_driver_executable

    node, cli = compute_driver_executable()
    for path in (node, cli):
        if not Path(path).exists():
            raise FileNotFoundError(path)
    return "driver present"


def _check_accessibility() -> str:
    if sys.platform == "win32":
        import uiautomation  # noqa: F401

        return "UI Automation"
    from kai.tools import uia

    return f"AT-SPI {uia._atspi().get_version()}"


def _check_input() -> str:
    import pynput.keyboard
    import pynput.mouse

    return pynput.keyboard.Controller.__module__


def _check_windows() -> str:
    import pywinctl  # noqa: F401

    return "ok"


def _check_screen() -> str:
    import mss
    from PIL import Image  # noqa: F401

    return mss.__version__


def _check_keyring() -> str:
    import keyring

    return type(keyring.get_keyring()).__name__


def _check_gemini() -> str:
    from google.genai import types  # noqa: F401

    from kai import live  # noqa: F401

    return "ok"


def _check_qt() -> str:
    from PySide6.QtCore import qVersion

    from kai.ui import main_window  # noqa: F401

    return qVersion()


CHECKS = {
    "qt": _check_qt,
    "gemini": _check_gemini,
    "audio": _check_audio,
    "browser": _check_browser,
    "accessibility": _check_accessibility,
    "input": _check_input,
    "windows": _check_windows,
    "screen": _check_screen,
    "keyring": _check_keyring,
}


def run() -> int:
    lines = [f"kai {__version__} self-test ({sys.platform}, frozen={getattr(sys, 'frozen', False)})"]
    failed = 0
    for name, check in CHECKS.items():
        try:
            lines.append(f"ok    {name}: {check()}")
        except Exception as e:  # report every failure, not just the first
            failed += 1
            lines.append(f"FAIL  {name}: {type(e).__name__}: {e}")
            lines.append("      " + traceback.format_exc().strip().splitlines()[-2].strip())
    lines.append("all checks passed" if not failed else f"{failed} check(s) failed")
    text = "\n".join(lines)
    (logs.log_file().parent / "selftest.txt").write_text(text + "\n", encoding="utf-8")
    if sys.stdout is not None:
        print(text)
    return 1 if failed else 0
