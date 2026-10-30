import time

import pytest

from kai import audio


@pytest.mark.parametrize(
    "name, headphones",
    [
        ("Headphone (Realtek(R) Audio)", True),
        ("Auriculares (Bluetooth)", True),
        ("Galaxy Buds2 Pro", True),
        ("Speaker (Realtek(R) Audio)", False),
        ("MacBook Pro Speakers", False),
    ],
)
def test_is_headphones(name, headphones):
    assert audio.is_headphones(name) is headphones


def test_stalled_stream_detection():
    spk = audio.Speaker()
    assert not spk.stalled()  # not running
    spk._stream = object()  # pretend it's open
    spk.last_callback = time.monotonic()
    assert not spk.stalled()
    spk.last_callback -= audio.STALL_SECONDS + 1
    assert spk.stalled()


def test_speaker_buffer():
    spk = audio.Speaker()
    spk.play(b"\x00" * audio.OUT_RATE * 2)
    assert spk.is_playing and spk.buffered_seconds == pytest.approx(1.0)
    spk.clear()
    assert not spk.is_playing
