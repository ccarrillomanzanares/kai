"""Carries out a multi-step task on the computer with Claude.

kai's voice model (Gemini Live) is quick but loses its way in tasks that take
several steps. With an Anthropic API key, such a task is handed to this
executor instead: Claude plans, acts through kai's own tools, looks at the
result and reports back, and the voice model tells the user.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import anthropic

from kai import tools

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5-5"
MAX_STEPS = 40  # tool calls before the task is given up
MAX_TOKENS = 16000

# USD per million tokens: input, output, cache read. Cache writes cost 1.25x input.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
}
# Models whose policy declines can be re-run on another model by the API itself.
_SERVER_FALLBACK = {"claude-opus-5-5", "claude-sonnet-5-5"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"

SYSTEM = """\
You are the hands of kai, a voice assistant that helps the user manage their computer \
({os}). kai's voice model talks with the user; when a request takes several steps on the \
computer it hands the task to you. You act through the tools and report back. The user \
does not read your text: kai reads your final report and tells them by voice, so the \
report is the only thing that reaches them.

The user is sitting at this computer, watching the same screen you act on. Do what they \
asked for and nothing beyond it: leave their other windows and work alone, and only \
delete, close or overwrite something when the task calls for it. When the task names the \
app or the way to do it, that choice is part of the task: if it can't be done there, stop \
and report what blocked you instead of doing it with another app or a hidden command, so \
the user can decide how to go on. Don't type into a window that already holds the user's \
work, such as an open document: your text would land inside it.

How the tools behave:
- type_text, press_keys, click and the other input tools only tell you the input was \
sent, never what it caused. What happened is on the screen: look (look_at_screen, \
read_window, list_windows) before you rely on it or report it.
- Windows are addressed by their title, and titles change: a terminal takes the name of \
the program running in it and goes back when that program ends. A title that stopped \
matching usually means the window was renamed, not closed; list_windows shows the titles \
as they are now, minimized windows included.
- run_command runs hidden and cannot answer prompts: the user sees nothing of it. It is \
right for looking things up and for changes that need no window. When the user wants to \
see something happen, or the program is interactive, use a window on the screen (for a \
terminal: type the command into it and press enter).
- Some actions ask the user for permission first. If a result says they declined, take \
that as their answer.

When the task is done, or you cannot get further, stop calling tools and write the \
report: two or three plain sentences in the user's language saying what you did, what \
you saw on the screen that confirms it, and anything that did not work or that the user \
has to do. If you could not check the outcome, say so instead of assuming it worked.\
"""


@dataclass
class Step:
    tool: str
    args: dict[str, Any]
    ok: bool
    seconds: float
    result: str  # shortened, for logs


@dataclass
class Result:
    report: str
    finished: bool  # False when it ran out of steps, was declined by the model, or failed
    steps: list[Step] = field(default_factory=list)
    seconds: float = 0.0
    requests: int = 0
    usage: dict[str, int] = field(default_factory=lambda: {
        "input": 0, "output": 0, "cache_read": 0, "cache_write": 0})
    model: str = DEFAULT_MODEL

    @property
    def cost(self) -> float | None:
        """Estimated cost in USD, or None for a model without a known price."""
        if self.model not in PRICES:
            return None
        inp, out, read = PRICES[self.model]
        u = self.usage
        return (u["input"] * inp + u["cache_write"] * inp * 1.25 + u["cache_read"] * read
                + u["output"] * out) / 1e6


def tool_specs() -> list[dict[str, Any]]:
    """kai's tools in the shape the Messages API takes; UI-only tools stay with the voice."""
    return [{"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in tools.TOOLS.values() if not t.ui_action]


def _tool_result(block_id: str, result: dict[str, Any]) -> dict[str, Any]:
    image = result.pop(tools.IMAGE_KEY, None)
    content: list[dict[str, Any]] = [
        {"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}]
    if image:
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": "image/jpeg",
            "data": base64.standard_b64encode(image).decode()}})
    return {"type": "tool_result", "tool_use_id": block_id, "content": content,
            "is_error": "error" in result}


def run_task(goal: str, *, client: anthropic.Anthropic, model: str = DEFAULT_MODEL,
             effort: str = "medium", confirm: tools.Confirm | None = None,
             level: tools.Permission = tools.Permission.BALANCED,
             on_step: Callable[[Step], None] | None = None,
             max_steps: int = MAX_STEPS) -> Result:
    """Work on goal until Claude reports back. Blocking: call it from a worker thread."""
    out = Result(report="", finished=False, model=model)
    started = time.monotonic()
    messages: list[dict[str, Any]] = [{"role": "user", "content": goal}]
    request: dict[str, Any] = dict(
        model=model, max_tokens=MAX_TOKENS,
        system=SYSTEM.format(os=tools.OS_NAME), tools=tool_specs(),
        output_config={"effort": effort},
        cache_control={"type": "ephemeral"},  # the growing conversation is re-read each step
    )
    if model in _SERVER_FALLBACK:
        request.update(betas=[_FALLBACK_BETA], fallbacks="default")
    try:
        while True:
            response = client.beta.messages.create(messages=messages, **request)
            out.requests += 1
            u = response.usage
            out.usage["input"] += u.input_tokens or 0
            out.usage["output"] += u.output_tokens or 0
            out.usage["cache_read"] += u.cache_read_input_tokens or 0
            out.usage["cache_write"] += u.cache_creation_input_tokens or 0
            messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason == "pause_turn":
                continue
            if response.stop_reason != "tool_use":
                out.report = "".join(b.text for b in response.content if b.type == "text").strip()
                out.finished = response.stop_reason == "end_turn"
                if not out.finished:
                    log.warning("Executor stopped: %s", response.stop_reason)
                    out.report = out.report or f"The task stopped early ({response.stop_reason})."
                break
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                if len(out.steps) >= max_steps:
                    result: dict[str, Any] = {"error": "Step limit reached. Report what you "
                                                       "did and what is left."}
                    results.append(_tool_result(block.id, result))
                    continue
                args = dict(block.input or {})
                t0 = time.monotonic()
                result = tools.call(block.name, args, confirm, level)
                shown = json.dumps({k: v for k, v in result.items() if k != tools.IMAGE_KEY},
                                   ensure_ascii=False, default=str)
                step = Step(block.name, args, "error" not in result, time.monotonic() - t0,
                            shown[:400])
                out.steps.append(step)
                log.info("Executor tool %s: %s in %.2fs", block.name,
                         "ok" if step.ok else "error", step.seconds)
                if on_step:
                    on_step(step)
                results.append(_tool_result(block.id, result))
            messages.append({"role": "user", "content": results})
    except anthropic.APIStatusError as e:
        log.warning("Executor API error %s: %s", e.status_code, e.message)
        out.report = f"The task could not be completed: Claude API error {e.status_code}."
    except anthropic.APIConnectionError:
        log.warning("Executor could not reach the Claude API")
        out.report = "The task could not be completed: the Claude API could not be reached."
    out.seconds = time.monotonic() - started
    return out
