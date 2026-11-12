"""Diagnostics report: system facts and recent logs, uploaded on request.

What is sent: kai and library versions, OS details, audio devices, whether an
API key is configured (never the key), and the tail of kai's log file.
Never sent: API keys. The conversation and tool arguments are only included
while the user leaves "Include the conversation" ticked for this report: this
run's conversation, or the whole recording when recording is turned on.
"""

from __future__ import annotations

import gzip
import json
import os
import platform
import sys
import urllib.error
import urllib.request
from importlib import metadata

from kai import __version__, config, logs, transcript

DIAG_URL = "https://ccmai.org/kai-diag/upload"
MAX_LOG_BYTES = 400_000
PACKAGES = ["google-genai", "PySide6", "sounddevice", "numpy", "keyring", "psutil", "pynput", "PyWinCtl",
            "playwright", "mss", "Pillow", "uiautomation"]


def _packages() -> dict[str, str]:
    versions = {}
    for name in PACKAGES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "missing"
    return versions


def _audio() -> dict:
    try:
        import sounddevice as sd

        devices = [
            {
                "name": d["name"],
                "inputs": d["max_input_channels"],
                "outputs": d["max_output_channels"],
            }
            for d in sd.query_devices()
        ]
        return {"portaudio": sd.get_portaudio_version()[1], "default": list(sd.default.device),
                "devices": devices}
    except Exception as e:
        return {"error": str(e)}


def _api_key_status() -> dict:
    import keyring

    if os.environ.get(config.ENV_VAR):
        source = "env"
    elif config.get_api_key():
        source = "stored"
    else:
        source = None
    return {"configured": source is not None, "source": source,
            "keyring_backend": type(keyring.get_keyring()).__name__}


def _log_tail() -> str:
    path = logs.log_file()
    chunks = []
    for p in (path.with_name(path.name + ".1"), path):
        if p.exists():
            chunks.append(p.read_bytes())
    data = b"".join(chunks)[-MAX_LOG_BYTES:]
    return logs.redact(data.decode("utf-8", errors="replace"))


def _recording_files() -> list:
    return [p for p in (transcript.path(), transcript.path().with_name(
        transcript.path().name + ".old")) if p.exists()]


def _use_recording(stored: bool) -> bool:
    """Whether the conversation comes from the recording on disk, not from this run.

    A recording left on disk while recording is off is from some earlier run: it is
    only sent when asked for from the terminal (stored), where there is no run.
    """
    if not _recording_files():
        return False
    return transcript.enabled() or (stored and not transcript.has_session())


def has_conversation(stored: bool = False) -> bool:
    return transcript.has_session() or _use_recording(stored)


def collect(include_conversation: bool = False, stored: bool = False) -> dict:
    report = {
        "kai_version": __version__,
        "system": {
            "os": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
            "session_type": os.environ.get("XDG_SESSION_TYPE"),
            "desktop": os.environ.get("XDG_CURRENT_DESKTOP"),
        },
        "packages": _packages(),
        "audio": _audio(),
        "api_key": _api_key_status(),
        "log": _log_tail(),
    }
    included = include_conversation and has_conversation(stored)
    recording = _use_recording(stored)
    report["conversation_status"] = {  # no content
        "recording": transcript.enabled(), "included": included,
        "source": ("recording" if recording else "this run") if included else None,
        "bytes_on_disk": sum(p.stat().st_size for p in _recording_files()),
    }
    if included and recording:
        report["conversation"] = transcript.read_tail()
        report["screenshots"] = transcript.read_shots()
    elif included:
        report["conversation"] = transcript.read_session()
        report["screenshots"] = transcript.read_session_shots()
    return report


def upload(report: dict) -> str:
    """Send the report and return its reference id. Raises RuntimeError on failure."""
    body = gzip.compress(json.dumps(report).encode())
    req = urllib.request.Request(
        DIAG_URL,
        data=body,
        headers={"Content-Type": "application/json", "Content-Encoding": "gzip",
                 "User-Agent": f"kai/{__version__}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)["id"]
    except urllib.error.HTTPError as e:
        try:
            reason = json.load(e)["error"]
        except Exception:
            reason = e.reason
        raise RuntimeError(f"Upload refused: {reason}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(f"Could not reach the server: {e}") from e
