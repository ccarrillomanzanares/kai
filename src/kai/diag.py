"""Diagnostics report: system facts and recent logs, uploaded on request.

What is sent: kai and library versions, OS details, audio devices, whether an
API key is configured (never the key), and the tail of kai's log file.
What is never sent: conversations, tool arguments, API keys.
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

from kai import __version__, config, logs

DIAG_URL = "https://ccmai.org/kai-diag/upload"
MAX_LOG_BYTES = 400_000
PACKAGES = ["google-genai", "PySide6", "sounddevice", "numpy", "keyring", "psutil"]


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


def collect() -> dict:
    return {
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
