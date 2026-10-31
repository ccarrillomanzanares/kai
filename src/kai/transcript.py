"""Optional conversation recording, for debugging only.

Off by default. When the user turns it on in Settings, what the user and kai
say and every tool call (arguments and a shortened result) go to a separate
file next to the logs. It is only uploaded if the user ticks "Include the
recorded conversation" when sending diagnostics. Turning the option off in
Settings deletes the file. API keys are redacted like in the logs.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from kai import logs

MAX_BYTES = 500_000  # keep roughly the most recent 500 KB
MAX_RESULT_CHARS = 400

_lock = threading.Lock()
_enabled = False
_pending: dict[str, list[str]] = {"user": [], "kai": []}


def path() -> Path:
    return logs.log_file().with_name("conversation.log")


def enabled() -> bool:
    return _enabled


def set_enabled(on: bool) -> None:
    """Start or stop recording. Stopping keeps the file: see delete()."""
    global _enabled
    with _lock:
        if _enabled and not on:
            _pending["user"].clear()
            _pending["kai"].clear()
        _enabled = on


def delete() -> None:
    path().unlink(missing_ok=True)
    path().with_name(path().name + ".old").unlink(missing_ok=True)


def _write(line: str) -> None:
    p = path()
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    if p.exists() and p.stat().st_size > MAX_BYTES:
        p.replace(p.with_name(p.name + ".old"))
    with p.open("a", encoding="utf-8") as f:
        f.write(logs.redact(f"{stamp} {line}") + "\n")


def _flush(who: str) -> None:
    text = "".join(_pending[who]).strip()
    _pending[who].clear()
    if text:
        _write(f"{who}: {text}")


def said(who: str, chunk: str) -> None:
    """Collect a transcription chunk; 'who' is 'user' or 'kai'."""
    if not _enabled:
        return
    with _lock:
        _flush("kai" if who == "user" else "user")  # the other side finished talking
        _pending[who].append(chunk)


def typed(text: str) -> None:
    if _enabled:
        with _lock:
            _write(f"user (typed): {text}")


def turn_done() -> None:
    if _enabled:
        with _lock:
            _flush("user")
            _flush("kai")


def tool(name: str, args: dict, result: dict) -> None:
    if not _enabled:
        return
    shown = json.dumps(result, ensure_ascii=False, default=str)
    if len(shown) > MAX_RESULT_CHARS:
        shown = shown[:MAX_RESULT_CHARS] + f"… ({len(shown)} chars)"
    with _lock:
        _flush("user")
        _flush("kai")
        _write(f"tool {name}({json.dumps(args, ensure_ascii=False, default=str)}) -> {shown}")


def note(text: str) -> None:
    """A marker such as a new connection, to line the file up with kai.log."""
    if _enabled:
        with _lock:
            _write(f"-- {text}")


def read_tail(max_bytes: int = 300_000) -> str:
    chunks = []
    for p in (path().with_name(path().name + ".old"), path()):
        if p.exists():
            chunks.append(p.read_bytes())
    data = b"".join(chunks)[-max_bytes:]
    return logs.redact(data.decode("utf-8", errors="replace"))
