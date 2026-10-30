"""Local tools the model can call through Gemini function calling.

Each tool has a risk level. Only READ and SAFE tools run without asking;
SENSITIVE tools (added in later milestones) will require user confirmation.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from typing import Any, Callable

from google.genai import types

from kai.tools import system

log = logging.getLogger(__name__)


class Risk(enum.Enum):
    READ = "read"
    SAFE = "safe"
    SENSITIVE = "sensitive"


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    func: Callable[..., Any]
    risk: Risk

    def declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name, description=self.description, parameters=self.parameters
        )


_NO_PARAMS: dict[str, Any] = {"type": "object", "properties": {}}

TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool(
            "get_datetime",
            "Get the current local date, time and timezone.",
            _NO_PARAMS,
            system.get_datetime,
            Risk.READ,
        ),
        Tool(
            "get_system_info",
            "Get operating system, CPU, memory, disk and battery usage of this computer.",
            _NO_PARAMS,
            system.get_system_info,
            Risk.READ,
        ),
        Tool(
            "open_url",
            "Open a web page in the user's default browser.",
            {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "Absolute http(s) URL."}},
                "required": ["url"],
            },
            system.open_url,
            Risk.SAFE,
        ),
    ]
}


def declarations() -> list[types.Tool]:
    return [types.Tool(function_declarations=[t.declaration() for t in TOOLS.values()])]


def call(name: str, args: dict[str, Any] | None) -> dict[str, Any]:
    """Run a tool and wrap its outcome in a function-response payload."""
    tool = TOOLS.get(name)
    if tool is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return {"result": tool.func(**(args or {}))}
    except Exception as e:
        # Only the exception type: messages can echo the user's arguments.
        log.warning("Tool %s raised %s", name, type(e).__name__)
        return {"error": str(e)}
