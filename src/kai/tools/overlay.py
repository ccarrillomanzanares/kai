"""Keeps kai's own window out of the way of what it looks at and clicks.

The app registers hooks at start; without them (tests, CLI) these do nothing.
Tools call them from worker threads; the hooks run on the UI thread and return
once the window has moved or hidden.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Callable

_step_aside: Callable[[tuple[int, int] | None], None] | None = None
_set_hidden: Callable[[bool], None] | None = None


def register(step_aside: Callable[[tuple[int, int] | None], None],
             set_hidden: Callable[[bool], None]) -> None:
    global _step_aside, _set_hidden
    _step_aside, _set_hidden = step_aside, set_hidden


def step_aside(point: tuple[int, int] | None = None) -> None:
    """Fold the conversation panel; move the bar if it covers point (screen pixels)."""
    if _step_aside:
        _step_aside(point)


@contextmanager
def hidden():
    """Keep kai's window out of a screenshot taken inside this block."""
    if _set_hidden:
        _set_hidden(True)
    try:
        yield
    finally:
        if _set_hidden:
            _set_hidden(False)
