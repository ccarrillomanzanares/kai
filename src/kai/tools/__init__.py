"""Local tools the model can call through Gemini function calling.

Each tool has a risk level. READ and SAFE tools run directly; SENSITIVE tools
run only after the user approves them in a confirmation dialog.
"""

from __future__ import annotations

import enum
import logging
import platform
from dataclasses import dataclass
from typing import Any, Callable

from google.genai import types

from kai.tools import apps, files, shell, system

log = logging.getLogger(__name__)

# Asks the user to approve a sensitive action: (title, detail) -> approved.
# Called from a worker thread; blocks until the user answers.
Confirm = Callable[[str, str], bool]


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
    # UI tools only describe what happened; the app performs the action on the UI thread.
    ui_action: bool = False
    # For SENSITIVE tools: builds the (title, detail) shown in the confirmation dialog.
    confirm_text: Callable[..., tuple[str, str]] | None = None

    def declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name, description=self.description, parameters=self.parameters
        )


def _params(required: list[str] | None = None, **props: tuple[str, str]) -> dict[str, Any]:
    """Build a JSON schema from name=(type, description) pairs."""
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {k: {"type": t, "description": d} for k, (t, d) in props.items()},
    }
    if required:
        schema["required"] = required
    return schema


OS_NAME = f"{platform.system()} {platform.release()}"

TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        # ---- read ----
        Tool("get_datetime", "Get the current local date, time and timezone.",
             _params(), system.get_datetime, Risk.READ),
        Tool("get_system_info",
             "Get operating system, CPU, memory, disk and battery usage of this computer.",
             _params(), system.get_system_info, Risk.READ),
        Tool("list_processes",
             "List the running programs using the most memory or CPU.",
             _params(sort_by=("string", "'memory' (default) or 'cpu'."),
                     limit=("integer", "How many to return, default 15.")),
             shell.list_processes, Risk.READ),
        Tool("list_directory",
             "List the files and folders inside a folder. Accepts ~ for the home folder.",
             _params(path=("string", "Folder path, e.g. '~/Downloads'. Default: home.")),
             files.list_directory, Risk.READ),
        Tool("search_files",
             "Find files or folders by name under a folder (default: home). "
             "Plain text matches anywhere in the name; glob patterns like '*.pdf' also work.",
             _params(["pattern"], pattern=("string", "Name or glob pattern."),
                     folder=("string", "Where to search, default '~'.")),
             files.search_files, Risk.READ),
        # ---- safe ----
        Tool("open_url", "Open a web page in the user's default browser.",
             _params(["url"], url=("string", "Absolute http(s) URL.")),
             system.open_url, Risk.SAFE),
        Tool("open_app",
             "Launch an application by name, e.g. 'notepad', 'calculator', 'firefox', 'Spotify'.",
             _params(["name"], name=("string", "Application name.")),
             apps.open_app, Risk.SAFE),
        Tool("open_path",
             "Open a file with its default application, or a folder in the file manager.",
             _params(["path"], path=("string", "File or folder path, ~ allowed.")),
             apps.open_path, Risk.SAFE),
        Tool("open_diagnostics",
             "Open kai's 'Send diagnostics' window so the user can review and send a report "
             "with kai's logs and system info (no conversations, no API key). Use it when the "
             "user reports a problem with kai or asks to send diagnostics. Nothing is sent "
             "until the user clicks Send.",
             _params(),
             lambda: "The diagnostics window is open. The user must click Send to upload it.",
             Risk.SAFE, ui_action=True),
        # ---- sensitive: the user confirms each call ----
        Tool("run_command",
             f"Run a {shell.SHELL_NAME} command on this computer ({OS_NAME}) and get its output. "
             "Use it for anything the other tools can't do: settings, files, network, installed "
             "software, etc. The user sees the exact command and must approve it, so prefer "
             "one clear, safe command. Runs in the user's home folder, non-interactively (no sudo or "
             "password prompts) with a 60 s timeout.",
             _params(["command", "reason"],
                     command=("string", f"The {shell.SHELL_NAME} command to run."),
                     reason=("string", "Short explanation for the user, in their language.")),
             shell.run_command, Risk.SENSITIVE,
             confirm_text=lambda command, reason="": (reason or "Run a command", command)),
        Tool("kill_process", "Close a running program by its process id (see list_processes).",
             _params(["pid"], pid=("integer", "Process id.")),
             shell.kill_process, Risk.SENSITIVE,
             confirm_text=lambda pid: ("Close a program", shell.describe_kill(pid))),
    ]
}


def declarations() -> list[types.Tool]:
    return [types.Tool(function_declarations=[t.declaration() for t in TOOLS.values()])]


def is_ui_action(name: str) -> bool:
    tool = TOOLS.get(name)
    return tool is not None and tool.ui_action


def call(name: str, args: dict[str, Any] | None, confirm: Confirm | None = None) -> dict[str, Any]:
    """Run a tool and wrap its outcome in a function-response payload."""
    tool = TOOLS.get(name)
    if tool is None:
        return {"error": f"Unknown tool: {name}"}
    args = args or {}
    try:
        if tool.risk is Risk.SENSITIVE:
            title, detail = tool.confirm_text(**args) if tool.confirm_text else (name, str(args))
            if confirm is None or not confirm(title, detail):
                log.info("Tool %s: declined by the user", name)
                return {"error": "The user declined this action."}
        return {"result": tool.func(**args)}
    except Exception as e:
        # Only the exception type: messages can echo the user's arguments.
        log.warning("Tool %s raised %s", name, type(e).__name__)
        return {"error": str(e)}
