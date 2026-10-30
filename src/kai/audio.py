"""Microphone capture and speaker playback in the formats Gemini Live expects.

Input: 16-bit PCM, 16 kHz, mono. Output: 16-bit PCM, 24 kHz, mono.
"""

from __future__ import annotations

import threading
from typing import Callable

import numpy as np

IN_RATE = 16_000
OUT_RATE = 24_000
IN_BLOCK = 800  # 50 ms


def _level(pcm: bytes) -> float:
    """RMS level of int16 PCM, roughly normalised to 0..1."""
    if not pcm:
        return 0.0
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    return min(1.0, float(np.sqrt(np.mean(samples**2))) / 6000)


class Microphone:
    def __init__(self, on_chunk: Callable[[bytes, float], None]):
        self._on_chunk = on_chunk
        self._stream = None

    def start(self) -> None:
        import sounddevice as sd

        if self._stream:
            return
        self._stream = sd.RawInputStream(
            samplerate=IN_RATE,
            channels=1,
            dtype="int16",
            blocksize=IN_BLOCK,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _callback(self, indata, frames, time, status) -> None:
        data = bytes(indata)
        self._on_chunk(data, _level(data))


class Speaker:
    """Buffered playback that can be flushed instantly when the user interrupts."""

    def __init__(self, on_level: Callable[[float], None] | None = None):
        self._on_level = on_level
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._stream = None

    def start(self) -> None:
        import sounddevice as sd

        if self._stream:
            return
        self._stream = sd.RawOutputStream(
            samplerate=OUT_RATE, channels=1, dtype="int16", callback=self._callback
        )
        self._stream.start()

    def stop(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
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

    def _callback(self, outdata, frames, time, status) -> None:
        n = len(outdata)
        with self._lock:
            chunk = bytes(self._buffer[:n])
            del self._buffer[:n]
        outdata[: len(chunk)] = chunk
        outdata[len(chunk) :] = b"\x00" * (n - len(chunk))
        if self._on_level:
            self._on_level(_level(chunk))
