"""The conversation, kept for diagnostics only.

What the user and kai say, every tool call (arguments and a shortened result)
and the last few screenshots kai took (already sent to Gemini), with its clicks
marked. The current run is always kept in memory and is gone when kai closes.
Recording to disk is off by default: when the user turns it on in Settings, the
same lines also go to a file next to the logs, so earlier runs can be sent too.
Turning the option off in Settings deletes the file. Nothing is uploaded unless
the user leaves "Include the conversation" ticked when sending diagnostics.
API keys are redacted like in the logs.
"""

from __future__ import annotations

import base64
import io
import json
import threading
import time
from pathlib import Path

from kai import logs

MAX_BYTES = 500_000  # keep roughly the most recent 500 KB
MAX_RESULT_CHARS = 400
MAX_SESSION_CHARS = 300_000  # this run's conversation, in memory
MAX_SHOTS = 12  # most recent screenshots kept
SHOT_SIDE = 800

_lock = threading.Lock()
_enabled = False
_pending: dict[str, list[str]] = {"user": [], "kai": []}
_session: list[str] = []  # this run's lines, whether or not recording to disk is on
_session_chars = 0
_session_shots: dict[str, bytes] = {}


def path() -> Path:
    return logs.log_file().with_name("conversation.log")


def enabled() -> bool:
    return _enabled


def set_enabled(on: bool) -> None:
    """Start or stop recording to disk. Stopping keeps the file: see delete()."""
    global _enabled
    with _lock:
        _enabled = on


def shots_dir() -> Path:
    return logs.log_file().with_name("conversation_shots")


def delete() -> None:
    """Remove the recording on disk. This run's conversation stays in memory."""
    path().unlink(missing_ok=True)
    path().with_name(path().name + ".old").unlink(missing_ok=True)
    for f in shots_dir().glob("*.jpg") if shots_dir().exists() else []:
        f.unlink(missing_ok=True)


def shot(jpeg: bytes, label: str, point: tuple[float, float] | None = None) -> None:
    """Keep a copy of a screenshot kai took; point (0-1000 coords) marks a click."""
    if not jpeg:
        return
    from PIL import Image, ImageDraw

    img = Image.open(io.BytesIO(jpeg)).convert("RGB")
    img.thumbnail((SHOT_SIDE, SHOT_SIDE))
    if point is not None:
        x, y = point[0] / 1000 * (img.width - 1), point[1] / 1000 * (img.height - 1)
        draw = ImageDraw.Draw(img)
        for r, color in ((9, "white"), (7, "red")):
            draw.ellipse((x - r, y - r, x + r, y + r), outline=color, width=2)
        draw.line((x - 12, y, x + 12, y), fill="red")
        draw.line((x, y - 12, x, y + 12), fill="red")
    name = f"{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}-{label}.jpg"
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=55)
    with _lock:
        _session_shots[name] = buf.getvalue()
        for old in list(_session_shots)[:-MAX_SHOTS]:
            del _session_shots[old]
        if _enabled:
            folder = shots_dir()
            folder.mkdir(exist_ok=True)
            (folder / name).write_bytes(buf.getvalue())
            for old in sorted(folder.glob("*.jpg"))[:-MAX_SHOTS]:
                old.unlink(missing_ok=True)
        _write(f"-- screenshot {name}")


def has_session() -> bool:
    return bool(_session)


def read_session() -> str:
    """This run's conversation, from memory."""
    with _lock:
        return "".join(line + "\n" for line in _session)


def read_session_shots() -> dict[str, str]:
    """This run's last screenshots as base64 JPEGs, by file name."""
    with _lock:
        return {name: base64.b64encode(data).decode() for name, data in _session_shots.items()}


def clear_session() -> None:
    global _session_chars
    with _lock:
        _session.clear()
        _session_shots.clear()
        _session_chars = 0
        _pending["user"].clear()
        _pending["kai"].clear()


def read_shots() -> dict[str, str]:
    """Screenshots recorded on disk as base64 JPEGs, by file name."""
    if not shots_dir().exists():
        return {}
    return {f.name: base64.b64encode(f.read_bytes()).decode()
            for f in sorted(shots_dir().glob("*.jpg"))}


def _write(line: str) -> None:
    global _session_chars
    line = logs.redact(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {line}")
    _session.append(line)
    _session_chars += len(line)
    while _session_chars > MAX_SESSION_CHARS and len(_session) > 1:
        _session_chars -= len(_session.pop(0))
    if not _enabled:
        return
    p = path()
    if p.exists() and p.stat().st_size > MAX_BYTES:
        p.replace(p.with_name(p.name + ".old"))
    with p.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _flush(who: str) -> None:
    text = "".join(_pending[who]).strip()
    _pending[who].clear()
    if text:
        _write(f"{who}: {text}")


def said(who: str, chunk: str) -> None:
    """Collect a transcription chunk; 'who' is 'user' or 'kai'."""
    with _lock:
        _flush("kai" if who == "user" else "user")  # the other side finished talking
        _pending[who].append(chunk)


def typed(text: str) -> None:
    with _lock:
        _flush("user")
        _flush("kai")
        _write(f"user (typed): {text}")


def turn_done() -> None:
    with _lock:
        _flush("user")
        _flush("kai")


def tool(name: str, args: dict, result: dict) -> None:
    shown = json.dumps(result, ensure_ascii=False, default=str)
    if len(shown) > MAX_RESULT_CHARS:
        shown = shown[:MAX_RESULT_CHARS] + f"… ({len(shown)} chars)"
    with _lock:
        _flush("user")
        _flush("kai")
        _write(f"tool {name}({json.dumps(args, ensure_ascii=False, default=str)}) -> {shown}")


def note(text: str) -> None:
    """A marker such as a new connection, to line the file up with kai.log."""
    with _lock:
        _write(f"-- {text}")


def read_tail(max_bytes: int = 300_000) -> str:
    chunks = []
    for p in (path().with_name(path().name + ".old"), path()):
        if p.exists():
            chunks.append(p.read_bytes())
    data = b"".join(chunks)[-max_bytes:]
    return logs.redact(data.decode("utf-8", errors="replace"))
