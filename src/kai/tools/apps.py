"""Open applications, files and folders with the platform's own launcher."""

from __future__ import annotations

import difflib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

START_APPS_TTL = 300  # seconds to cache the Windows Start menu app list
_start_apps: tuple[float, dict[str, str]] = (0.0, {})


def _detached(cmd: list[str]) -> None:
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)


def open_path(path: str) -> str:
    target = Path(os.path.expandvars(os.path.expanduser(path))).resolve()
    if not target.exists():
        raise FileNotFoundError(f"Not found: {target}")
    if sys.platform == "win32":
        os.startfile(target)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        _detached(["open", str(target)])
    else:
        _detached(["xdg-open", str(target)])
    return f"Opened {target}"


def _linux_desktop_entry(name: str) -> str | None:
    """Find a .desktop file whose file name or Name= matches."""
    dirs = [Path.home() / ".local/share/applications", Path("/usr/share/applications"),
            Path("/var/lib/flatpak/exports/share/applications"),
            Path.home() / ".local/share/flatpak/exports/share/applications"]
    wanted = name.lower()
    for d in dirs:
        for f in d.glob("*.desktop") if d.is_dir() else []:
            if wanted in f.stem.lower():
                return f.stem
            try:
                for line in f.read_text(errors="ignore").splitlines():
                    if line.startswith("Name=") and wanted in line[5:].lower():
                        return f.stem
            except OSError:
                continue
    return None


def match_app(name: str, apps: dict[str, str]) -> str | None:
    """Pick the best app for a spoken name: exact, then prefix, then substring, then fuzzy."""
    wanted = name.lower().strip()
    names = {n.lower(): n for n in apps}
    if wanted in names:
        return names[wanted]
    for test in (str.startswith, lambda n, w: w in n):
        hits = sorted((n for n in names if test(n, wanted)), key=len)
        if hits:
            return names[hits[0]]
    close = difflib.get_close_matches(wanted, names, n=1, cutoff=0.75)
    return names[close[0]] if close else None


def _windows_start_apps() -> dict[str, str]:
    """Name -> AppID of every app in the Start menu, desktop and Microsoft Store alike."""
    global _start_apps
    fetched, apps = _start_apps
    if apps and time.monotonic() - fetched < START_APPS_TTL:
        return apps
    script = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
              "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress")
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                         capture_output=True, text=True, encoding="utf-8", errors="replace",
                         timeout=20, creationflags=subprocess.CREATE_NO_WINDOW).stdout
    items = json.loads(out or "[]")
    if isinstance(items, dict):  # a single app is not wrapped in a list
        items = [items]
    apps = {i["Name"]: i["AppID"] for i in items if i.get("Name") and i.get("AppID")}
    _start_apps = (time.monotonic(), apps)
    return apps


def _open_windows_app(name: str) -> str:
    try:
        apps = _windows_start_apps()
    except (OSError, ValueError, subprocess.SubprocessError):
        apps = {}
    if match := match_app(name, apps):
        # shell:AppsFolder launches both classic and Microsoft Store apps by AppID.
        _detached(["explorer.exe", f"shell:AppsFolder\\{apps[match]}"])
        return f"Launched {match}"
    if shutil.which(name):
        # Not in the Start menu but on PATH (notepad, calc, …).
        subprocess.run(["cmd", "/c", "start", "", name], check=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
        return f"Launched {name}"
    similar = difflib.get_close_matches(name, list(apps), n=5, cutoff=0.4)
    hint = f" Similar apps: {', '.join(similar)}." if similar else ""
    raise FileNotFoundError(f"No application found for '{name}'.{hint}")


def open_app(name: str) -> str:
    if sys.platform == "win32":
        return _open_windows_app(name)
    elif sys.platform == "darwin":
        subprocess.run(["open", "-a", name], check=True, capture_output=True)
    else:
        if entry := _linux_desktop_entry(name):
            _detached(["gtk-launch", entry])
        elif exe := shutil.which(name.lower()):
            _detached([exe])
        else:
            raise FileNotFoundError(f"No application found for '{name}'")
    return f"Launched {name}"
