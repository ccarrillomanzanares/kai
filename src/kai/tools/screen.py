"""Screenshots for the model, and mouse control in screenshot coordinates.

Coordinates are normalized to 0-1000 over the last screenshot (what Gemini is
best at), and mapped back to real screen pixels when clicking. Works on
Windows and Linux on X11; Wayland blocks both capture and synthetic input.
"""

from __future__ import annotations

import io
import time
from dataclasses import dataclass

from kai.tools import desktop

MAX_SIDE = 1280  # pixels: enough to read text, light on tokens
JPEG_QUALITY = 70

# Screen region (left, top, width, height) of the last screenshot, in pixels.
_last_region: tuple[int, int, int, int] | None = None


@dataclass
class Image:
    """A tool result that carries a picture for the model."""
    jpeg: bytes
    text: str


def to_jpeg(img) -> bytes:
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


def look_at_screen(window: str | None = None) -> Image:
    import mss
    from PIL import Image as PILImage

    global _last_region
    with mss.mss() as sct:
        if window:
            win = desktop._find_window(window)
            desktop.focus_window(win.title)
            left, top, width, height = win.left, win.top, win.width, win.height
            # Keep the region on the screens (maximized windows overhang a few pixels).
            bounds = sct.monitors[0]
            right = min(left + width, bounds["left"] + bounds["width"])
            bottom = min(top + height, bounds["top"] + bounds["height"])
            left, top = max(left, bounds["left"]), max(top, bounds["top"])
            region = {"left": left, "top": top, "width": right - left, "height": bottom - top}
            what = f"the window '{win.title}'"
        else:
            region = dict(sct.monitors[1])  # the primary screen
            what = "the screen"
        shot = sct.grab(region)
    img = PILImage.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    _last_region = (region["left"], region["top"], shot.size[0], shot.size[1])
    return Image(to_jpeg(img),
                 f"Screenshot of {what} attached. To click something in it, call click with "
                 "x and y from 0 to 1000 relative to this image (0,0 is its top-left corner).")


def _to_screen(x: float, y: float) -> tuple[int, int]:
    if _last_region is None:
        raise RuntimeError("Take a screenshot with look_at_screen first.")
    if not (0 <= x <= 1000 and 0 <= y <= 1000):
        raise ValueError("x and y go from 0 to 1000.")
    left, top, width, height = _last_region
    return round(left + x / 1000 * (width - 1)), round(top + y / 1000 * (height - 1))


def click_point(px: int, py: int, button: str = "left", double: bool = False) -> None:
    from pynput.mouse import Button, Controller

    mouse = Controller()
    mouse.position = (px, py)
    time.sleep(0.05)
    mouse.click(Button.right if button == "right" else Button.left, 2 if double else 1)
    time.sleep(0.3)


def click(x: float, y: float, button: str = "left", double: bool = False) -> str:
    px, py = _to_screen(x, y)
    click_point(px, py, button, double)
    kind = ("Double-clicked" if double else "Right-clicked" if button == "right" else "Clicked")
    return f"{kind} at ({x:g}, {y:g}). Take a new screenshot to check the result."


def scroll(direction: str = "down", amount: int = 5, x: float | None = None,
           y: float | None = None) -> str:
    from pynput.mouse import Controller

    mouse = Controller()
    if x is not None and y is not None:
        mouse.position = _to_screen(x, y)
        time.sleep(0.05)
    steps = max(1, min(int(amount), 30))
    mouse.scroll(0, steps if direction.lower().startswith("u") else -steps)
    return f"Scrolled {direction} {steps} steps."
