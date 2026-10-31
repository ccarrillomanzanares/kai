"""Optional conversation recording, for debugging only.

Off by default. When the user turns it on in Settings, what the user and kai
say and every tool call (arguments and a shortened result) go to a separate
file next to the logs, plus the last few screenshots kai took (already sent to
Gemini), with its clicks marked. It is only uploaded if the user ticks "Include the
recorded conversation" when sending diagnostics. Turning the option off in
Settings deletes the file. API keys are redacted like in the logs.
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
MAX_SHOTS = 12  # most recent screenshots kept
SHOT_SIDE = 800

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


def shots_dir() -> Path:
    return logs.log_file().with_name("conversation_shots")


def delete() -> None:
    path().unlink(missing_ok=True)
    path().with_name(path().name + ".old").unlink(missing_ok=True)
    for f in shots_dir().glob("*.jpg") if shots_dir().exists() else []:
        f.unlink(missing_ok=True)


def shot(jpeg: bytes, label: str, point: tuple[float, float] | None = None) -> None:
    """Keep a copy of a screenshot kai took; point (0-1000 coords) marks a click."""
    if not _enabled or not jpeg:
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
    folder = shots_dir()
    folder.mkdir(exist_ok=True)
    name = f"{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}-{label}.jpg"
    img.save(folder / name, "JPEG", quality=55)
    for old in sorted(folder.glob("*.jpg"))[:-MAX_SHOTS]:
        old.unlink(missing_ok=True)
    with _lock:
        _write(f"-- screenshot {name}")


def read_shots() -> dict[str, str]:
    """Kept screenshots as base64 JPEGs, by file name."""
    if not shots_dir().exists():
        return {}
    return {f.name: base64.b64encode(f.read_bytes()).decode()
            for f in sorted(shots_dir().glob("*.jpg"))}


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
