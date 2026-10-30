"""Microphone capture and speaker playback in the formats Gemini Live expects.

Input: 16-bit PCM, 16 kHz, mono. Output: 16-bit PCM, 24 kHz, mono.

Both streams record when their callback last ran so the agent can detect a
stream the OS stopped (device unplugged, default device changed…) and restart it.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import Callable

import numpy as np

log = logging.getLogger(__name__)

IN_RATE = 16_000
OUT_RATE = 24_000
IN_BLOCK = 800  # 50 ms
STALL_SECONDS = 1.5  # no callback for this long means the stream is dead

_HEADPHONES = re.compile(r"headphone|headset|auricular|kopfh|casque|cuffie|airpods|buds",
                         re.IGNORECASE)


def _level(pcm: bytes) -> float:
    """RMS level of int16 PCM, roughly normalised to 0..1."""
    if not pcm:
        return 0.0
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    return min(1.0, float(np.sqrt(np.mean(samples**2))) / 6000)


def default_devices() -> tuple[str, str]:
    """Names of the default input and output devices."""
    import sounddevice as sd

    return (sd.query_devices(kind="input")["name"], sd.query_devices(kind="output")["name"])


def is_headphones(device_name: str) -> bool:
    return bool(_HEADPHONES.search(device_name))


class _Stream:
    """Shared bookkeeping: last callback time and rate-limited status logging."""

    def __init__(self):
        self._stream = None
        self.last_callback = 0.0
        self._last_status_log = 0.0

    @property
    def running(self) -> bool:
        return self._stream is not None

    def stalled(self) -> bool:
        return self.running and time.monotonic() - self.last_callback > STALL_SECONDS

    def _note(self, status) -> None:
        self.last_callback = time.monotonic()
        if status and self.last_callback - self._last_status_log > 10:
            self._last_status_log = self.last_callback
            log.warning("%s status: %s", type(self).__name__, status)

    def restart(self) -> None:
        log.warning("Restarting %s", type(self).__name__)
        self.stop()
        self.start()

    def start(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def stop(self) -> None:
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                log.warning("Closing %s failed: %s", type(self).__name__, e)
            self._stream = None


class Microphone(_Stream):
    def __init__(self, on_chunk: Callable[[bytes, float], None]):
        super().__init__()
        self._on_chunk = on_chunk

    def start(self) -> None:
        import sounddevice as sd

        if self._stream:
            return
        self._stream = sd.RawInputStream(
            samplerate=IN_RATE, channels=1, dtype="int16", blocksize=IN_BLOCK,
            callback=self._callback,
        )
        self._stream.start()
        self.last_callback = time.monotonic()

    def _callback(self, indata, frames, time_info, status) -> None:
        self._note(status)
        try:
            data = bytes(indata)
            self._on_chunk(data, _level(data))
        except Exception:
            log.exception("Microphone callback failed")


class Speaker(_Stream):
    """Buffered playback that can be flushed instantly when the user interrupts."""

    def __init__(self, on_level: Callable[[float], None] | None = None):
        super().__init__()
        self._on_level = on_level
        self._buffer = bytearray()
        self._lock = threading.Lock()

    def start(self) -> None:
        import sounddevice as sd

        if self._stream:
            return
        self._stream = sd.RawOutputStream(
            samplerate=OUT_RATE, channels=1, dtype="int16", callback=self._callback
        )
        self._stream.start()
        self.last_callback = time.monotonic()

    def stop(self) -> None:
        super().stop()
        self.clear()

    def play(self, pcm: bytes) -> None:
        with self._lock:
            self._buffer.extend(pcm)

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()

    @property
    def is_playing(self) -> bool:
        with self._lock:
            return bool(self._buffer)

    @property
    def buffered_seconds(self) -> float:
        with self._lock:
            return len(self._buffer) / (OUT_RATE * 2)

    def _callback(self, outdata, frames, time_info, status) -> None:
        self._note(status)
        n = len(outdata)
        with self._lock:
            chunk = bytes(self._buffer[:n])
            del self._buffer[:n]
        outdata[: len(chunk)] = chunk
        outdata[len(chunk) :] = b"\x00" * (n - len(chunk))
        try:
            if self._on_level:
                self._on_level(_level(chunk))
        except Exception:
            log.exception("Speaker level callback failed")
