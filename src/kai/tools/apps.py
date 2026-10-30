"""Open applications, files and folders with the platform's own launcher."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


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


def open_app(name: str) -> str:
    if sys.platform == "win32":
        # `start` resolves registered apps (notepad, calc, chrome, ms-settings:, …).
        subprocess.run(["cmd", "/c", "start", "", name], check=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
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
