"""File and folder tools."""

from __future__ import annotations

import fnmatch
import os
import time
from pathlib import Path

MAX_ENTRIES = 200
MAX_RESULTS = 50
SEARCH_SECONDS = 8


def _resolve(path: str | None) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(path or "~"))).resolve()


def list_directory(path: str = "~") -> dict:
    folder = _resolve(path)
    if not folder.is_dir():
        raise FileNotFoundError(f"Not a folder: {folder}")
    entries = []
    for entry in sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if len(entries) >= MAX_ENTRIES:
            break
        try:
            is_dir = entry.is_dir()
            entries.append({
                "name": entry.name,
                "type": "folder" if is_dir else "file",
                **({} if is_dir else {"size_kb": round(entry.stat().st_size / 1024, 1)}),
            })
        except OSError:
            continue
    return {"path": str(folder), "entries": entries, "truncated": len(entries) >= MAX_ENTRIES}


def search_files(pattern: str, folder: str = "~") -> dict:
    """Find files whose name matches a glob pattern (case-insensitive) under a folder."""
    root = _resolve(folder)
    pattern = pattern.lower() if any(c in pattern for c in "*?[") else f"*{pattern.lower()}*"
    deadline = time.monotonic() + SEARCH_SECONDS
    matches: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip hidden folders and heavy dependency folders.
        dirnames[:] = [d for d in dirnames if not d.startswith(".")
                       and d not in ("node_modules", "__pycache__", "AppData")]
        for name in dirnames + filenames:
            if fnmatch.fnmatch(name.lower(), pattern):
                matches.append(os.path.join(dirpath, name))
                if len(matches) >= MAX_RESULTS:
                    return {"matches": matches, "complete": False}
        if time.monotonic() > deadline:
            return {"matches": matches, "complete": False, "note": "search stopped after timeout"}
    return {"matches": matches, "complete": True}
