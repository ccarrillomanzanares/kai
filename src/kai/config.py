"""API key storage and app settings.

The Gemini API key lives in the OS secret store (macOS Keychain, Windows
Credential Manager, Linux Secret Service). If no secret store is available,
it falls back to a user-only readable file in the config directory.
"""

from __future__ import annotations

import json
import logging
import os
import stat
import sys
from pathlib import Path

import keyring
from keyring.errors import KeyringError

log = logging.getLogger(__name__)

SERVICE = "kai"
KEY_NAME = "gemini_api_key"
ENV_VAR = "GEMINI_API_KEY"

MODEL = "gemini-3.8-live"
API_KEY_URL = "https://aistudio.google.com/apikey"


def config_dir() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = base / "kai"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _fallback_file() -> Path:
    return config_dir() / "api_key"


def get_api_key() -> str | None:
    """Return the stored API key, preferring the environment variable."""
    if key := os.environ.get(ENV_VAR):
        return key.strip()
    try:
        if key := keyring.get_password(SERVICE, KEY_NAME):
            return key
    except KeyringError as e:
        log.warning("Secret store unavailable: %s", e)
    path = _fallback_file()
    if path.exists():
        return path.read_text().strip() or None
    return None


def set_api_key(key: str) -> None:
    key = key.strip()
    try:
        keyring.set_password(SERVICE, KEY_NAME, key)
        _fallback_file().unlink(missing_ok=True)
        return
    except KeyringError as e:
        log.warning("Secret store unavailable, using file fallback: %s", e)
    path = _fallback_file()
    path.write_text(key)
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def delete_api_key() -> None:
    try:
        keyring.delete_password(SERVICE, KEY_NAME)
    except KeyringError:
        pass
    _fallback_file().unlink(missing_ok=True)


def looks_like_api_key(key: str) -> bool:
    """Cheap sanity check before hitting the network."""
    key = key.strip()
    return len(key) >= 30 and " " not in key


def validate_api_key(key: str) -> str | None:
    """Check the key against the Gemini API. Returns an error message or None."""
    from google import genai
    from google.genai import errors

    try:
        # Keep a reference: the client closes its HTTP session when collected.
        client = genai.Client(api_key=key.strip())
        client.models.get(model=MODEL)
    except errors.ClientError as e:
        if e.code in (400, 401, 403):
            return "Google rejected this key. Check that you copied it completely."
        return f"Could not verify the key ({e.code})."
    except Exception as e:  # network errors, etc.
        return f"Could not reach Google: {e}"
    return None


# ---- settings ----

DEFAULT_SETTINGS = {
    "voice": None, "accent": "auto", "custom_accent": "", "permissions": "balanced",
    "microphone": None, "detailed_logs": True,
}


def _settings_file() -> Path:
    return config_dir() / "settings.json"


def load_settings() -> dict:
    settings = dict(DEFAULT_SETTINGS)
    try:
        settings.update(json.loads(_settings_file().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return settings


def save_settings(settings: dict) -> None:
    _settings_file().write_text(json.dumps(settings, indent=2), encoding="utf-8")
